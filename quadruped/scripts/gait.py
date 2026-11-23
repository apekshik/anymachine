"""Quadruped kinematics + procedural gaits (trot, idle, sit, stand) baked to linear FK keys.

Pure-math part (no bpy): leg FK / analytic IK in the rig's own conventions, so what we key is exactly what Blender
evaluates. The bake part writes one action per gait onto the armature (and keeps them on NLA tracks for glTF export).

Conventions (Blender world, Z up, robot faces -Y; legs FL FR HL HR, s = -1 left / +1 right):
  body bone   head at (0, y_c, z_hip): loc = (0, dy, dz), euler XYZ = (pitch, roll, 0); nose-up = NEGATIVE pitch.
  <leg>_haa   abduction about the body's Y axis through the HAA pivot (s*x_haa, y_hip, z_hip). Bone-local Y rotation;
              right bones point -Y, left bones +Y, so POSITIVE = foot moves OUTWARD on both sides.
  <leg>_hfe   hip flexion about +X through the HFE axis; positive = foot swings BACKWARD (right-hand rule about +X).
  <leg>_kfe   knee about +X through the knee axis; positive = knee opens (straightens) for these backward knees.
All joint angles are relative to the bind pose (the measured, symmetrised generated pose).

When this file is run from the .blend's Text editor (it is embedded as text "gait.py"), it re-reads the gait
parameters from the armature's custom props (step_length, step_height, body_height, speed, duty, ...) and re-bakes.
"""
import math
from mathutils import Matrix, Vector, Euler

LEGS = ("FL", "FR", "HL", "HR")
DIAG = {"FL": 0.0, "HR": 0.0, "FR": 0.5, "HL": 0.5}  # trot: diagonal pairs share a phase


def Rx(a):
    return Matrix.Rotation(a, 3, "X")


def Ry(a):
    return Matrix.Rotation(a, 3, "Y")


class Leg:
    def __init__(self, name, spec, geo):
        self.name, self.s = name, spec["s"]
        self.P = Vector(spec["haa_pivot"])  # HAA pivot (rest, world)
        self.H = Vector(spec["hfe"])  # HFE axis point in the leg plane
        self.t0 = Vector((0, geo["t0"][0], geo["t0"][1]))  # rest thigh vector (y, z)
        self.s0 = Vector((0, geo["s0"][0], geo["s0"][1]))  # rest shin vector
        self.L1, self.L2 = self.t0.length, self.s0.length
        self.psi0 = math.atan2(self.s0.z, self.s0.y) - math.atan2(self.t0.z, self.t0.y)
        self.d = self.s * (self.H.x - self.P.x)  # lateral offset of the leg plane from the HAA pivot (>0)
        self.lim = geo["limits_rad"]

    def haa_R(self, a):
        # right: about -Y by a; left: about +Y by a  (positive = outward)
        return Ry(-a) if self.s > 0 else Ry(a)

    def fk_local(self, a, f1, f2):
        """Body-frame (rest coords) knee, foot centre and foot rotation."""
        K = self.H + Rx(f1) @ self.t0
        F = K + Rx(f1 + f2) @ self.s0
        R = self.haa_R(a)
        return self.P + R @ (K - self.P), self.P + R @ (F - self.P), R @ Rx(f1 + f2)

    def ik_local(self, p):
        """Body-frame target foot centre -> (a, f1, f2), unclamped, plus a reach flag."""
        u = self.s * (p.x - self.P.x)
        v = p.y - self.P.y
        w = p.z - self.P.z
        planar_depth_sq = u * u + w * w - self.d ** 2
        wp = -math.sqrt(max(planar_depth_sq, 1e-9))
        a = math.atan2(w, u) - math.atan2(wp, self.d)
        q2 = v * v + wp * wp
        c = (q2 - self.L1 ** 2 - self.L2 ** 2) / (2 * self.L1 * self.L2)
        # The HAA pivot-to-leg offset also limits reach, independent of the two links.
        ok = planar_depth_sq >= 0 and -1 <= c <= 1
        psi = math.copysign(math.acos(max(-1, min(1, c))), self.psi0)
        f2 = psi - self.psi0
        ang_q = math.atan2(wp, v)
        ang_t = ang_q - math.atan2(self.L2 * math.sin(psi), self.L1 + self.L2 * math.cos(psi))
        f1 = ang_t - math.atan2(self.t0.z, self.t0.y)
        f1 = (f1 + math.pi) % (2 * math.pi) - math.pi
        return (a, f1, f2), ok


class Body:
    def __init__(self, head):
        self.head = Vector(head)

    def matrix(self, root, loc, pitch, roll):
        """4x4 world matrix taking rest-world coords of body-attached points to posed world."""
        R = Euler((pitch, roll, 0), "XYZ").to_matrix().to_4x4()
        return Matrix.Translation(Vector(root) + self.head + Vector(loc)) @ R @ Matrix.Translation(-self.head)


def smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


class Gaits:
    def __init__(self, spec):
        self.spec = spec
        geo = spec["geometry"]
        self.legs = {n: Leg(n, spec["legs"][n], geo) for n in LEGS}
        self.body = Body(spec["body_head"])
        self.r = geo["foot_r"]
        self.z_hip0 = spec["body_head"][2]

    # neutral foot centre (rest-world xy) under each hip
    def neutral(self, n, dy=0.0):
        L = self.legs[n]
        return Vector((L.H.x, L.H.y + dy, self.r))

    def solve(self, frames):
        """frames: list of dict(root, loc, pitch, roll, feet{n: world foot centre}) -> per-frame joint angles.
        Contact feet roll without slipping: the foot centre is shifted by r * (foot rotation increment), iterated."""
        out = []
        for fr in frames:
            M = self.body.matrix(fr["root"], fr["loc"], fr["pitch"], fr["roll"])
            Mi = M.inverted()
            ang, Rw, reach = {}, {}, True
            for n, L in self.legs.items():
                p = Mi @ fr["feet"][n]
                q, ok = L.ik_local(p)
                reach &= ok
                ang[n] = q
                Rw[n] = M.to_3x3() @ L.fk_local(*q)[2]
            out.append({"ang": ang, "Rw": Rw, "M": M, "reach": reach})
        return out

    # ------------------------------------------------------------------ gaits
    def trot(self, p, cycles=1, root_motion=False, fps=30):
        """Trot. p: step_length (world stride per cycle, m), step_height, body_height (hip height), speed (m/s),
        duty (stance fraction), pitch_deg, roll_deg, bob (m). Period T = step_length / speed."""
        T = p["step_length"] / p["speed"]
        nf = round(T * fps)
        T = nf / fps  # snap to whole frames so the loop closes exactly
        v = p["step_length"] / T
        duty = p["duty"]
        stroke = v * duty * T
        frames, contact = [], []
        N = nf * cycles
        # foot plans: stance foot world y fixed at root_y(t_td) + y_n - stroke/2
        for i in range(N + 1):
            t = i / fps
            ph = (t / T) % 1.0
            ry = -v * t
            fr = {"root": (0, ry if root_motion else 0, 0),
                  "loc": (0, 0, p["body_height"] - self.z_hip0 - p["bob"] * 0.5 * (1 - math.cos(4 * math.pi * ph))),
                  "pitch": math.radians(p["pitch_deg"]) * math.sin(4 * math.pi * ph),
                  "roll": math.radians(p["roll_deg"]) * math.sin(2 * math.pi * ph), "feet": {}}
            ct = {}
            for n in LEGS:
                lp = (ph - DIAG[n]) % 1.0
                k = math.floor(t / T - DIAG[n])
                t_td = (k + DIAG[n]) * T  # touch-down time of the current cycle for this leg
                nb = self.neutral(n)
                y_td = -v * t_td + nb.y - stroke / 2
                if lp < duty:
                    pos = Vector((nb.x, y_td, self.r))
                    ct[n] = True
                else:
                    sw = (lp - duty) / (1 - duty)
                    y_lo = y_td  # lift-off point (stance drift added later)
                    y_next = -v * (t_td + T) + nb.y - stroke / 2
                    c = sw - math.sin(2 * math.pi * sw) / (2 * math.pi)
                    pos = Vector((nb.x, y_lo + (y_next - y_lo) * c, self.r + p["step_height"] * 0.5 * (1 - math.cos(2 * math.pi * sw))))
                    ct[n] = False
                if not root_motion:
                    pos.y -= ry
                fr["feet"][n] = pos
            frames.append(fr)
            contact.append(ct)
        return frames, contact, nf

    def idle(self, p, fps=30, seconds=4.0):
        nf = round(seconds * fps)
        frames, contact = [], []
        for i in range(nf + 1):
            x = 2 * math.pi * i / nf
            frames.append({"root": (0, 0, 0),
                           "loc": (0.014 * math.sin(x), 0.006 * math.sin(2 * x), p["body_height"] - self.z_hip0 - 0.004 * (1 - math.cos(2 * x)) * 0.5),
                           "pitch": math.radians(0.8) * math.sin(2 * x + 0.6), "roll": math.radians(1.6) * math.sin(x),
                           "feet": {n: self.neutral(n) for n in LEGS}})
            contact.append({n: True for n in LEGS})
        return frames, contact, nf

    def sit_pose(self, p):
        return {"loc": (0, p.get("sit_dy", 0.03), p.get("sit_z", 0.25) - self.z_hip0), "pitch": math.radians(p.get("sit_pitch_deg", -22.0)), "roll": 0.0}

    def sit(self, p, fps=30, seconds=1.6, reverse=False):
        nf = round(seconds * fps)
        sp = self.sit_pose(p)
        st = {"loc": (0, 0, p["body_height"] - self.z_hip0), "pitch": 0.0, "roll": 0.0}
        frames, contact = [], []
        for i in range(nf + 1):
            k = smooth(i / nf)
            if reverse:
                k = 1 - k
            lerp = lambda a, b: a + (b - a) * k
            frames.append({"root": (0, 0, 0), "loc": tuple(lerp(a, b) for a, b in zip(st["loc"], sp["loc"])),
                           "pitch": lerp(st["pitch"], sp["pitch"]), "roll": 0.0,
                           "feet": {n: self.neutral(n, p.get("sit_hind_foot_dy", -0.02) * k if n[0] == "H" else 0.0) for n in LEGS}})
            contact.append({n: True for n in LEGS})
        # hind feet slide forward slightly as the robot sits: mark the move as a (tiny) re-placement, not contact,
        # only if it is non-zero; keep contact so rolling compensation still applies.
        return frames, contact, nf


def trot_with_drift(g, p, cycles, root_motion, fps=30):
    """Trot with rolling contact: stance drift carried into the following swing so lift-off is continuous."""
    frames, contact, nf = g.trot(p, cycles + 2, root_motion, fps)  # 1 cycle of warm-up each side
    base = [{n: fr["feet"][n].copy() for n in LEGS} for fr in frames]
    sol = g.solve(frames)
    for _ in range(3):
        drift = {n: Vector((0, 0, 0)) for n in LEGS}
        last = {n: Vector((0, 0, 0)) for n in LEGS}
        offs = [{} for _ in frames]
        for i in range(len(frames)):
            for n in LEGS:
                if contact[i][n]:
                    if i > 0 and contact[i - 1][n]:
                        dR = sol[i]["Rw"][n] @ sol[i - 1]["Rw"][n].inverted()
                        ax, an = dR.to_quaternion().to_axis_angle()
                        w = ax * an
                        drift[n] = drift[n] + Vector((g.r * w.y, -g.r * w.x, 0))
                    else:
                        drift[n] = Vector((0, 0, 0))
                    last[n] = drift[n].copy()
                    offs[i][n] = drift[n].copy()
                else:
                    offs[i][n] = None
        # swing: fade the last stance drift to zero over the swing
        for n in LEGS:
            i = 0
            while i < len(frames):
                if not contact[i][n]:
                    j = i
                    while j < len(frames) and not contact[j][n]:
                        j += 1
                    d0 = offs[i - 1][n] if i > 0 and offs[i - 1][n] is not None else Vector((0, 0, 0))
                    for k in range(i, j):
                        sw = (k - i + 1) / (j - i + 1)
                        c = sw - math.sin(2 * math.pi * sw) / (2 * math.pi)
                        offs[k][n] = d0 * (1 - c)
                    i = j
                else:
                    i += 1
        for i, fr in enumerate(frames):
            for n in LEGS:
                fr["feet"][n] = base[i][n] + offs[i][n]
        sol = g.solve(frames)
    # drop the warm-up cycle at the start and the spare at the end
    a, b = nf, nf * (cycles + 1) + 1
    frames, contact, sol = frames[a:b], contact[a:b], sol[a:b]
    if root_motion:
        y0 = frames[0]["root"][1]
        for fr in frames:
            fr["root"] = (0, fr["root"][1] - y0, 0)
            for n in LEGS:
                fr["feet"][n].y -= y0
        sol = g.solve(frames)
    return frames, contact, sol, nf


def planted_with_rolling(g, frames, contact):
    """All-feet-planted actions (idle/sit/stand): rolling-contact drift accumulates over the whole action."""
    base = [{n: fr["feet"][n].copy() for n in LEGS} for fr in frames]
    sol = g.solve(frames)
    for _ in range(3):
        drift = {n: Vector((0, 0, 0)) for n in LEGS}
        for i, fr in enumerate(frames):
            for n in LEGS:
                if i > 0:
                    dR = sol[i]["Rw"][n] @ sol[i - 1]["Rw"][n].inverted()
                    ax, an = dR.to_quaternion().to_axis_angle()
                    w = ax * an
                    drift[n] = drift[n] + Vector((g.r * w.y, -g.r * w.x, 0))
                fr["feet"][n] = base[i][n] + drift[n]
        sol = g.solve(frames)
    return sol


DEFAULTS = {"step_length": 0.24, "step_height": 0.07, "body_height": 0.32, "speed": 0.40, "duty": 0.55,
            "pitch_deg": 1.2, "roll_deg": 1.5, "bob": 0.006, "fps": 30, "forward_cycles": 4,
            "sit_z": 0.235, "sit_pitch_deg": -25.0, "sit_dy": 0.04, "sit_hind_foot_dy": 0.0}


def build_all(spec, p):
    """-> {action_name: (frames, contact, sol)}"""
    g = Gaits(spec)
    fps = p["fps"]
    acts = {}
    fr, ct, sol, nf = trot_with_drift(g, p, 1, False, fps)
    acts["trot"] = (fr, ct, sol)
    fr, ct, sol, nf = trot_with_drift(g, p, p["forward_cycles"], True, fps)
    acts["trot_forward"] = (fr, ct, sol)
    fr, ct, nf = g.idle(p, fps)
    acts["idle"] = (fr, ct, planted_with_rolling(g, fr, ct))
    fr, ct, nf = g.sit(p, fps)
    acts["sit"] = (fr, ct, planted_with_rolling(g, fr, ct))
    # stand-up = sit played backwards: rolling contact is reversible, so it stays slip-free and starts exactly
    # where sit ends (re-solving the reverse path would accumulate a different rolling drift)
    acts["stand"] = tuple(list(reversed(x)) for x in acts["sit"])
    return g, acts


# ------------------------------------------------------------------ bake (bpy)
def bake(arm, acts, clamp=True):
    """Write linear keys: root loc, body loc/rot, per-leg haa/hfe/kfe rotations. One action + NLA track each."""
    import bpy
    pb = arm.pose.bones
    if arm.animation_data is None:
        arm.animation_data_create()
    ad = arm.animation_data
    for t in list(ad.nla_tracks):
        ad.nla_tracks.remove(t)
    spec = __import__("json").loads(arm["anymachine"])
    lim = spec["geometry"]["limits_rad"]
    clamped = {}
    for name, (frames, contact, sol) in acts.items():
        old = bpy.data.actions.get(name)
        if old:
            bpy.data.actions.remove(old)
        act = bpy.data.actions.new(name)
        ad.action = act
        nclamp = 0
        for i, (fr, so) in enumerate(zip(frames, sol)):
            f = i + 1
            pb["root"].location = fr["root"]
            pb["root"].keyframe_insert("location", frame=f)
            pb["body"].location = fr["loc"]
            pb["body"].rotation_euler = (fr["pitch"], fr["roll"], 0)
            pb["body"].keyframe_insert("location", frame=f)
            pb["body"].keyframe_insert("rotation_euler", frame=f)
            for n in LEGS:
                a, f1, f2 = so["ang"][n]
                if clamp:
                    c = (max(lim["haa"][0], min(lim["haa"][1], a)), max(lim["hfe"][0], min(lim["hfe"][1], f1)),
                         max(lim["kfe"][0], min(lim["kfe"][1], f2)))
                    nclamp += c != (a, f1, f2)
                    a, f1, f2 = c
                pb[n + "_haa"].rotation_euler = (0, a, 0)
                pb[n + "_hfe"].rotation_euler = (f1, 0, 0)
                pb[n + "_kfe"].rotation_euler = (f2, 0, 0)
                for b in ("_haa", "_hfe", "_kfe"):
                    pb[n + b].keyframe_insert("rotation_euler", frame=f)
        for fc in _fcurves(act):
            for k in fc.keyframe_points:
                k.interpolation = "LINEAR"
        act.use_fake_user = True
        trk = ad.nla_tracks.new()
        trk.name = name
        st = trk.strips.new(name, 1, act)
        trk.mute = True
        ad.action = None
        clamped[name] = nclamp
    return clamped


def _fcurves(act):
    try:
        return list(act.fcurves)
    except AttributeError:  # Blender 5 layered actions
        out = []
        for layer in act.layers:
            for strip in layer.strips:
                for cb in strip.channelbags:
                    out += list(cb.fcurves)
        return out


if __name__ == "__main__":
    # run from the .blend Text editor: re-bake with the rig's current custom props
    import bpy, json
    arm = bpy.data.objects["quadruped_rig"]
    spec = json.loads(arm["anymachine"])
    p = dict(DEFAULTS)
    for k in p:
        if k in arm.keys():
            p[k] = arm[k]
    g, acts = build_all(spec, p)
    print("rebaked", bake(arm, acts))
