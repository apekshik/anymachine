"""AnyMachine spider: pure kinematics (no bpy). Leg layout, analytic 3-DOF leg IK, gait / idle / crouch trajectories.

Frame: Blender Z up, forward = -Y, metres. Body rest frame = the armature at rest (body bone head at (0, 0, hip_z)).

Leg chain (per leg, 8 legs L1..L4 / R1..R4, front to back):
    body --hip_yaw (axis Z, at the yaw axis Y0)--> coxa --hip_pitch (axis a, at P1)--> femur --knee (axis a, at K)--> tibia(+foot)
with u0 = horizontal rest direction of the leg, a = u x z (pitch axis; +rotation raises the distal end) and
w = z x u (+yaw turns u towards w). The three parts sit in DIFFERENT axial slabs along a (coxa and tibia on one side,
femur on the other, split by `gap`), so adjacent segments cannot intersect at any joint angle: their half-barrels are
coaxial cylinders of equal radius separated by the gap. The foot centre is therefore offset by c along a.
"""
import math

LEGS = ["L1", "L2", "L3", "L4", "R1", "R2", "R3", "R4"]

DEFAULTS = {
    # dimensions (m); measured where noted in build_report, otherwise design values
    "body_len": 0.40,
    "hip_z": 0.100,          # hip-pitch axis height when standing (= `body_height` param)
    "L1": 0.045,             # yaw axis -> pitch axis (coxa)
    "L2": 0.130,             # pitch axis -> knee axis (femur)
    "L3": 0.170,             # knee axis -> foot centre (tibia)
    "foot_r": 0.013,
    "gap": 0.0015,           # axial gap between coaxial half-barrels
    "wC": 0.024, "wF": 0.024, "wT": 0.020,   # axial widths of coxa / femur / tibia
    "rY": 0.019, "rP": 0.019, "rK": 0.016,   # barrel radii: hip yaw / hip pitch / knee
    "hip_y": [-0.105, -0.035, 0.035, 0.105], # yaw-axis Y per leg pair, front to back
    "hip_az": [52.0, 17.0, -17.0, -50.0],    # rest leg direction, degrees forward of lateral
    "reach": 0.225,          # yaw axis -> foot centre, horizontal, at rest
    # gait
    "step_length": 0.12,     # stride: body travel per gait cycle (m)
    "step_height": 0.035,    # swing apex above ground (m)
    "speed": 0.12,           # m/s (cycle period = step_length / speed, rounded to whole frames)
    "duty": 0.60,            # stance fraction per leg (>0.5: two tetrapods overlap, 8 feet down at transitions)
    "bob": 0.003,            # body bob amplitude (m), 2 bobs per cycle
    "crouch_drop": 0.045,    # body lowering at crouch = 1 (m)
    "fps": 24,
    # joint limits (deg). Coxa about Z (relative to rest); femur ABSOLUTE elevation; knee = tibia angle relative to femur
    "lim_yaw": 22.0,          # sweep: first contact at 27.5 deg (leg-2 femur vs leg-1 coxa), 0.13 mm at 25 -> 22
    "lim_femur_elev": [-35.0, 80.0],
    "lim_knee_rel": [-165.0, -25.0],
}

GROUP_A = {"L1", "R2", "L3", "R4"}   # alternating tetrapod


def side(leg):
    return -1.0 if leg[0] == "L" else 1.0


def v_add(a, b):
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def v_sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def v_mul(a, s):
    return [a[0] * s, a[1] * s, a[2] * s]


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def layout(P, chassis_hw):
    """Per-leg rest geometry in the body REST frame (armature space). chassis_hw(y) -> chassis half-width at y."""
    out = {}
    for leg in LEGS:
        s = side(leg)
        k = int(leg[1]) - 1
        hy = P["hip_y"][k]
        hx = s * (chassis_hw(hy) + 0.006 + P["rY"])
        az = math.radians(P["hip_az"][k])
        u = [s * math.cos(az), -math.sin(az), 0.0]          # forward = -Y
        z = [0.0, 0.0, 1.0]
        a = cross(u, z)
        w = cross(z, u)
        m = s  # mirror the slab assignment so left and right legs are true mirror images
        c_fem = m * (P["gap"] / 2 + P["wF"] / 2)              # femur axial centre (+m side)
        c_cox = -m * (P["gap"] / 2 + P["wC"] / 2)             # coxa  (-m side)
        c_tib = -m * (P["gap"] / 2 + P["wT"] / 2)             # tibia (-m side)
        Y0 = [hx, hy, P["hip_z"]]
        P1 = v_add(Y0, v_mul(u, P["L1"]))
        Fn = v_add(v_add(Y0, v_mul(u, P["reach"])), v_mul(a, c_tib))
        Fn[2] = P["foot_r"]
        out[leg] = {"side": s, "Y0": Y0, "u": u, "a": a, "w": w, "c_fem": c_fem, "c_cox": c_cox, "c_tib": c_tib,
                    "P1": P1, "foot_rest": Fn}
    # rest angles = IK of the rest foot from the rest body
    for leg, L in out.items():
        ik = leg_ik(P, L, L["foot_rest"])
        L["e0"], L["k0"] = ik["elev"], ik["knee_rel"]
        e, kr = L["e0"], L["k0"]
        f = v_add(v_mul(L["u"], math.cos(e)), [0, 0, math.sin(e)])
        t = v_add(v_mul(L["u"], math.cos(e + kr)), [0, 0, math.sin(e + kr)])
        L["f0"], L["t0"] = f, t
        L["K"] = v_add(L["P1"], v_mul(f, P["L2"]))
        L["Fp"] = v_add(L["K"], v_mul(t, P["L3"]))          # foot centre projected to the a = 0 plane
    return out


def leg_ik(P, L, F):
    """Analytic IK. F = foot-centre target in the body REST frame. Returns yaw/elev/knee_rel (rad) and local angles."""
    d = v_sub(F, L["Y0"])
    du, dw = dot(d, L["u"]), dot(d, L["w"])
    c = L["c_tib"]
    r2 = du * du + dw * dw - c * c
    rho = math.sqrt(max(r2, 1e-9))
    # foot in the yawed frame sits at (rho along u, c along a = -w)  ->  angle of (rho, -c) in (u, w)
    psi = math.atan2(dw, du) - math.atan2(-c, rho)
    x, zz = rho - P["L1"], d[2]
    D = math.hypot(x, zz)
    # A foot centre closer to the yaw axis than its slab offset cannot reach that target.
    # Keep the projected pose finite so callers can still report the failed target.
    reach_ok = r2 >= 0 and abs(P["L2"] - P["L3"]) + 1e-4 <= D <= P["L2"] + P["L3"] - 1e-4
    D = min(max(D, abs(P["L2"] - P["L3"]) + 1e-4), P["L2"] + P["L3"] - 1e-4)
    g = math.atan2(zz, x)
    b = math.acos(max(-1.0, min(1.0, (P["L2"] ** 2 + D * D - P["L3"] ** 2) / (2 * P["L2"] * D))))
    e = g + b                                               # knee-up solution
    kx, kz = P["L2"] * math.cos(e), P["L2"] * math.sin(e)
    tau = math.atan2(zz - kz, x - kx)
    res = {"yaw": psi, "elev": e, "knee_rel": tau - e, "reach_ok": reach_ok}
    if "e0" in L:
        res["q"] = (psi, e - L["e0"], (tau - e) - L["k0"])   # local bone rotations: coxa Z, femur X, tibia X
    return res


def limits_local(P, L):
    """Local (bone-space) limits in radians for coxa Z, femur X, tibia X."""
    y = math.radians(P["lim_yaw"])
    fe = [math.radians(v) - L["e0"] for v in P["lim_femur_elev"]]
    kn = [math.radians(v) - L["k0"] for v in P["lim_knee_rel"]]
    return {"coxa": (-y, y), "femur": tuple(fe), "tibia": tuple(kn)}


def frames_per_cycle(P):
    return max(8, int(round(P["step_length"] / P["speed"] * P["fps"])))


# ------------------------------------------------------------------ trajectories
# Each returns a dict: root (xyz, world), body_loc (xyz offset from rest, body/root frame), body_rot (euler xyz, rad),
# feet {leg: world xyz}, stance {leg: bool}.

def _smooth(s):
    return s - math.sin(2 * math.pi * s) / (2 * math.pi)


def walk_state(P, L, t):
    n_f = frames_per_cycle(P)
    T = n_f / P["fps"]
    v = P["step_length"] / T
    root = [0.0, -v * t, 0.0]
    duty = P["duty"]
    feet, stance = {}, {}
    for leg in LEGS:
        ph = 0.0 if leg in GROUP_A else 0.5
        cyc = t / T + ph
        n = math.floor(cyc)
        p = cyc - n
        Fn = L[leg]["foot_rest"]

        def hold(nn):
            tm = (nn + duty / 2 - ph) * T
            return [Fn[0], Fn[1] - v * tm, P["foot_r"]]

        if p < duty:
            feet[leg], stance[leg] = hold(n), True
        else:
            s = (p - duty) / (1 - duty)
            a0, a1 = hold(n), hold(n + 1)
            sh = _smooth(s)
            feet[leg] = [a0[0] + (a1[0] - a0[0]) * sh, a0[1] + (a1[1] - a0[1]) * sh,
                         P["foot_r"] + P["step_height"] * 0.5 * (1 - math.cos(2 * math.pi * s))]
            stance[leg] = False
    # body bob: highest at each tetrapod's mid-stance (2 per cycle), lowest at the 8-foot transitions
    bob = P["bob"] * math.cos(4 * math.pi * (t / T - duty / 2))
    # a little roll towards the side carrying more stance load would be biological; a machine stays level
    return {"root": root, "body_loc": [0.0, 0.0, bob], "body_rot": [0.0, 0.0, 0.0], "feet": feet, "stance": stance,
            "T": T, "v": v}


def idle_state(P, L, t, period=3.0):
    w = 2 * math.pi * t / period
    feet = {leg: list(L[leg]["foot_rest"]) for leg in LEGS}
    return {"root": [0.0, 0.0, 0.0],
            "body_loc": [0.006 * math.sin(w), 0.004 * math.sin(2 * w), 0.004 * math.sin(w + 1.2) - 0.002],
            "body_rot": [math.radians(1.2) * math.sin(w + 0.5), math.radians(1.5) * math.sin(w), math.radians(3.0) * math.sin(w + 2.0)],
            "feet": feet, "stance": {leg: True for leg in LEGS}}


def crouch_state(P, L, c):
    feet = {leg: list(L[leg]["foot_rest"]) for leg in LEGS}
    return {"root": [0.0, 0.0, 0.0], "body_loc": [0.0, 0.0, -P["crouch_drop"] * c], "body_rot": [0.0, 0.0, 0.0],
            "feet": feet, "stance": {leg: True for leg in LEGS}}


def euler_matrix(r):
    """3x3 rotation for Blender XYZ euler (applied X then Y then Z)."""
    cx, sx, cy, sy, cz, sz = math.cos(r[0]), math.sin(r[0]), math.cos(r[1]), math.sin(r[1]), math.cos(r[2]), math.sin(r[2])
    Rx = [[1, 0, 0], [0, cx, -sx], [0, sx, cx]]
    Ry = [[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]]
    Rz = [[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]

    def mm(A, B):
        return [[sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    return mm(Rz, mm(Ry, Rx))


def solve_state(P, L, st):
    """World foot targets -> per-leg IK in the body rest frame. Body world = root + (0,0,hip_z) + body_loc, rotated."""
    R = euler_matrix(st["body_rot"])
    org = v_add(v_add(st["root"], [0, 0, P["hip_z"]]), st["body_loc"])
    out = {}
    for leg in LEGS:
        d = v_sub(st["feet"][leg], org)
        loc = [R[0][i] * d[0] + R[1][i] * d[1] + R[2][i] * d[2] for i in range(3)]   # R^T d
        F_rest = v_add(loc, [0, 0, P["hip_z"]])
        out[leg] = leg_ik(P, L[leg], F_rest)
    return out
