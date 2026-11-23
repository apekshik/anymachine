"""Automatic mechanism check for the rigged spider.

blender -b --factory-startup --python check.py -- --blend out/spider.blend --out out/check.json [--step 2.5]

1. Joint sweeps: every one of the 24 joints alone through its full limit range (others at rest): triangle overlaps
   between ALL parts (body skin + chassis + 24 leg parts), min clearance, and that the evaluated angle tracks the command.
2. Limit clamping: command each joint 20 deg past each limit; the evaluated angle must stop at the limit.
3. Motions (walk_demo = 4 cycles, idle, crouch), every frame: overlaps, clearances, ground penetration, joint-angle
   tracking, foot-target error and FOOT SLIP during stance (stance taken from the gait schedule, feet = tibia tails).
4. IK mode: ik_blend = 1 on walk_demo (Blender's IK solver drives the legs from the keyed foot targets): foot error.
"""
import bpy, sys, os, json, math
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import spider_lib as SL

argv = sys.argv[sys.argv.index("--") + 1:]


def opt(k, d=None, cast=str):
    return cast(argv[argv.index(k) + 1]) if k in argv else d


bpy.ops.wm.open_mainfile(filepath=os.path.abspath(opt("--blend")))
OUT = os.path.abspath(opt("--out"))
STEP = math.radians(opt("--step", 2.5, float))
sc = bpy.context.scene
dg = bpy.context.evaluated_depsgraph_get()
arm = bpy.data.objects["spider_rig"]
P = json.loads(arm["anymachine_params"])
hwj = json.loads(arm["anymachine_chassis_hw"])
L = SL.layout(P, lambda y: float(np.interp(y, hwj["y"], hwj["hw"])))
for t in arm.animation_data.nla_tracks:
    t.mute = True

BODY = ["chassis", "shell"]
LEGP = [f"{p}_{leg}" for leg in SL.LEGS for p in ("coxa", "femur", "tibia")]
ALL = BODY + LEGP
ADJ = set()
for leg in SL.LEGS:
    ADJ |= {frozenset(("chassis", f"coxa_{leg}")), frozenset(("shell", f"coxa_{leg}")),
            frozenset((f"coxa_{leg}", f"femur_{leg}")), frozenset((f"femur_{leg}", f"tibia_{leg}"))}

# local geometry once
GEO = {}
for n in ALL:
    me = bpy.data.objects[n].data
    me.calc_loop_triangles()
    V = np.array([v.co[:] for v in me.vertices])
    T = [tuple(t.vertices) for t in me.loop_triangles]
    GEO[n] = (np.c_[V, np.ones(len(V))], T)


def update():
    bpy.context.view_layer.update()


def world_verts(n):
    M = np.array(bpy.data.objects[n].matrix_world)
    return (GEO[n][0] @ M.T)[:, :3]


def bvh_of(n, W):
    return BVHTree.FromPolygons([Vector(p) for p in W], GEO[n][1])


def scene_state(parts=None, cache=None):
    """world verts, aabb and BVH per part (reuse `cache` for parts not listed in `parts`)."""
    out = dict(cache or {})
    for n in (parts or ALL):
        W = world_verts(n)
        out[n] = (W, W.min(0), W.max(0), bvh_of(n, W))
    return out


def collide(S, movers=None, margin=0.03):
    """overlap tri-pairs and min clearance for every part pair (or pairs touching `movers`)."""
    names = list(S)
    hits, clear_adj, clear_non, worst = [], 1e9, 1e9, None
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if a in BODY and b in BODY:
                continue
            if movers and a not in movers and b not in movers:
                continue
            Wa, la, ha, Ba = S[a]
            Wb, lb, hb, Bb = S[b]
            if np.any(la > hb + margin) or np.any(lb > ha + margin):
                continue
            ov = Ba.overlap(Bb)
            if ov:
                hits.append((a, b, len(ov)))
            # clearance: vertices of the smaller part against the larger one's BVH (+ the reverse for leg pairs)
            sa, sb = (Wa, Bb) if len(Wa) <= len(Wb) else (Wb, Ba)
            lo_b = np.maximum(la, lb) - margin
            hi_b = np.minimum(ha, hb) + margin
            m = np.all((sa >= lo_b) & (sa <= hi_b), axis=1)
            d = min((sb.find_nearest(Vector(p))[3] for p in sa[m]), default=1e9)
            if a not in BODY and b not in BODY:
                o = (Wb, Ba) if sa is Wa else (Wa, Bb)
                m2 = np.all((o[0] >= lo_b) & (o[0] <= hi_b), axis=1)
                d = min(d, min((o[1].find_nearest(Vector(p))[3] for p in o[0][m2]), default=1e9))
            if frozenset((a, b)) in ADJ:
                clear_adj = min(clear_adj, d)
            elif d < clear_non:
                clear_non, worst = d, (a, b)
    return hits, clear_adj, clear_non, worst


def joint_actual(name):
    """evaluated (post-constraint) local rotation of a pose bone relative to its rest, as euler XYZ."""
    pb = arm.pose.bones[name]
    b = pb.bone
    par = pb.parent
    rest_rel = b.parent.matrix_local.inverted() @ b.matrix_local
    loc = rest_rel.inverted() @ par.matrix.inverted() @ pb.matrix
    return loc.to_3x3().to_euler("XYZ")


AX = {"coxa": 2, "femur": 0, "tibia": 0}
res = {"params": {k: P[k] for k in ("hip_z", "L1", "L2", "L3", "step_length", "step_height", "speed", "duty", "gap")}}

# ---------------------------------------------------------------- 1+2: joint sweeps + clamping (rest pose elsewhere)
arm.animation_data.action = None
for pb in arm.pose.bones:
    pb.location = (0, 0, 0)
    pb.rotation_euler = (0, 0, 0)
arm["ik_blend"] = 0.0
update()
REST = scene_state()
sweep, clamp_err, track_err = {}, 0.0, 0.0
for leg in SL.LEGS:
    lim = SL.limits_local(P, L[leg])
    movers = [f"{p}_{leg}" for p in ("coxa", "femur", "tibia")]
    for part in ("coxa", "femur", "tibia"):
        name = f"{part}_{leg}"
        pb = arm.pose.bones[name]
        lo, hi = lim[part]
        n = max(2, int(math.ceil((hi - lo) / STEP)))
        rows, bad = [], []
        for i in range(n + 1):
            q = lo + (hi - lo) * i / n
            e = [0, 0, 0]
            e[AX[part]] = q
            pb.rotation_euler = e
            update()
            S = scene_state(movers, REST)
            hits, ca, cn, worst = collide(S, movers)
            act = joint_actual(name)[AX[part]]
            track_err = max(track_err, abs(act - q))
            rows.append((q, cn, ca))
            if hits:
                bad.append({"deg": round(math.degrees(q), 1), "hits": hits})
        # clamp test
        for q, want in ((lo - math.radians(20), lo), (hi + math.radians(20), hi)):
            e = [0, 0, 0]
            e[AX[part]] = q
            pb.rotation_euler = e
            update()
            clamp_err = max(clamp_err, abs(joint_actual(name)[AX[part]] - want))
        pb.rotation_euler = (0, 0, 0)
        update()
        sweep[name] = {"range_deg": [round(math.degrees(lo), 1), round(math.degrees(hi), 1)], "steps": n + 1,
                       "overlap_steps": bad, "min_clearance_mm": round(min(r[1] for r in rows) * 1000, 2),
                       "min_adjacent_gap_mm": round(min(r[2] for r in rows) * 1000, 2)}
res["sweeps"] = {"joints": 24, "steps_total": sum(v["steps"] for v in sweep.values()),
                 "joints_with_overlap": [k for k, v in sweep.items() if v["overlap_steps"]],
                 "min_clearance_mm": min(v["min_clearance_mm"] for v in sweep.values()),
                 "min_adjacent_gap_mm": min(v["min_adjacent_gap_mm"] for v in sweep.values()),
                 "max_tracking_error_deg": round(math.degrees(track_err), 4),
                 "max_clamp_error_deg": round(math.degrees(clamp_err), 4), "per_joint": sweep}
print("SWEEP", json.dumps({k: v for k, v in res["sweeps"].items() if k != "per_joint"}), flush=True)


# ---------------------------------------------------------------- 3: motions
def foot_world(leg):
    return arm.matrix_world @ arm.pose.bones[f"tibia_{leg}"].tail


def stance_of(motion, f):
    if motion.startswith("walk"):
        return SL.walk_state(P, L, (f - 1) / P["fps"])["stance"]
    return {leg: True for leg in SL.LEGS}


def target_of(motion, f):
    if motion.startswith("walk"):
        return SL.walk_state(P, L, (f - 1) / P["fps"])["feet"]
    if motion == "idle":
        return SL.idle_state(P, L, (f - 1) / P["fps"])["feet"]
    return SL.crouch_state(P, L, (f - 1) / P["fps"])["feet"]


def run_motion(motion, ik=False, geometry=True, sub=1):
    act = bpy.data.actions[motion]
    arm.animation_data.action = act
    arm["ik_blend"] = 1.0 if ik else 0.0
    f0, f1 = [int(x) for x in act.frame_range]
    feet_hist = {leg: [] for leg in SL.LEGS}
    r = {"frames": f1 - f0 + 1, "overlap_frames": [], "min_clearance_mm": 1e9, "worst_pair": None,
         "min_adjacent_gap_mm": 1e9, "min_part_z_mm": 1e9, "min_foot_z_mm": 1e9, "max_target_err_mm": 0.0,
         "max_track_err_deg": 0.0}
    fr = f0
    while fr <= f1 + 1e-9:
        sc.frame_set(int(fr), subframe=fr - int(fr))
        if ik:  # start the solver from the REST pose, so it must find the leg angles from the foot targets alone
            for leg in SL.LEGS:
                for part in ("coxa", "femur", "tibia"):
                    arm.pose.bones[f"{part}_{leg}"].rotation_euler = (0, 0, 0)
        update()
        st = stance_of(motion, fr)
        tg = target_of(motion, fr)
        for leg in SL.LEGS:
            p = foot_world(leg)
            feet_hist[leg].append((fr, st[leg], p.copy()))
            r["max_target_err_mm"] = max(r["max_target_err_mm"], (p - Vector(tg[leg])).length * 1000)
            r["min_foot_z_mm"] = min(r["min_foot_z_mm"], (p.z - P["foot_r"]) * 1000)
            if not ik:
                for part in ("coxa", "femur", "tibia"):
                    nm = f"{part}_{leg}"
                    cmd = arm.pose.bones[nm].rotation_euler[AX[part]]
                    r["max_track_err_deg"] = max(r["max_track_err_deg"], abs(math.degrees(joint_actual(nm)[AX[part]] - cmd)))
        if geometry:
            S = scene_state()
            hits, ca, cn, worst = collide(S)
            if hits:
                r["overlap_frames"].append({"frame": fr, "hits": hits})
            r["min_adjacent_gap_mm"] = min(r["min_adjacent_gap_mm"], ca * 1000)
            if cn * 1000 < r["min_clearance_mm"]:
                r["min_clearance_mm"], r["worst_pair"] = cn * 1000, [worst, fr]
            for n in LEGP:
                if n.startswith("tibia"):
                    continue  # tibia carries the foot ball: judged by min_foot_z
                r["min_part_z_mm"] = min(r["min_part_z_mm"], S[n][1][2] * 1000)
            for n in BODY:
                r["min_part_z_mm"] = min(r["min_part_z_mm"], S[n][1][2] * 1000)
        fr += sub
    # foot slip: within each contiguous stance run, max displacement from the run's first sample
    slip, slip_xy, n_runs = 0.0, 0.0, 0
    for leg, h in feet_hist.items():
        run0 = None
        for fr_, s, p in h:
            if s:
                if run0 is None:
                    run0, n_runs = p, n_runs + 1
                d = p - run0
                slip = max(slip, d.length)
                slip_xy = max(slip_xy, math.hypot(d.x, d.y))
            else:
                run0 = None
    r.update({"stance_runs": n_runs, "max_foot_slip_mm": round(slip * 1000, 4), "max_foot_slip_xy_mm": round(slip_xy * 1000, 4)})
    for k in ("min_clearance_mm", "min_adjacent_gap_mm", "min_part_z_mm", "min_foot_z_mm", "max_target_err_mm", "max_track_err_deg"):
        r[k] = round(r[k], 3)
    if not geometry:
        # These passes only measure foot motion, so no geometry verdict exists.
        for key in ("overlap_frames", "min_clearance_mm", "min_adjacent_gap_mm", "min_part_z_mm"):
            r[key] = None
    r["any_overlap"] = bool(r["overlap_frames"]) if geometry else None
    return r


res["motions"] = {}
for m in ("walk_demo", "walk", "idle", "crouch"):
    res["motions"][m] = run_motion(m)
    print("MOTION", m, json.dumps({k: v for k, v in res["motions"][m].items() if k != "overlap_frames"}), flush=True)
# sub-frame sampling of the baked linear keys (what a glTF player interpolates)
res["motions"]["walk_halfframes"] = run_motion("walk", geometry=False, sub=0.5)
res["ik_mode"] = run_motion("walk_demo", ik=True, geometry=False)
print("IK", json.dumps({k: v for k, v in res["ik_mode"].items() if k != "overlap_frames"}), flush=True)
arm["ik_blend"] = 0.0
arm.animation_data.action = bpy.data.actions["walk_demo"]

geometry_motions = [motion for motion in res["motions"].values() if motion["overlap_frames"] is not None]
res["summary"] = {
    "overlaps_sweeps": len(res["sweeps"]["joints_with_overlap"]),
    "overlaps_motion_frames": sum(len(v["overlap_frames"]) for v in geometry_motions),
    "min_clearance_mm": min([res["sweeps"]["min_clearance_mm"]] + [v["min_clearance_mm"] for v in geometry_motions]),
    "min_adjacent_gap_mm": min([res["sweeps"]["min_adjacent_gap_mm"]] + [v["min_adjacent_gap_mm"] for v in geometry_motions]),
    "max_foot_slip_mm_frames": res["motions"]["walk_demo"]["max_foot_slip_mm"],
    "max_foot_slip_mm_halfframes": res["motions"]["walk_halfframes"]["max_foot_slip_mm"],
    "limits_clamp_err_deg": res["sweeps"]["max_clamp_error_deg"],
    "max_tracking_error_deg": max(res["sweeps"]["max_tracking_error_deg"], *[v["max_track_err_deg"] for v in res["motions"].values()]),
    "min_ground_clearance_parts_mm": min(v["min_part_z_mm"] for v in geometry_motions),
    "min_foot_z_mm": min(v["min_foot_z_mm"] for v in res["motions"].values()),
    "ik_mode_max_foot_err_mm": res["ik_mode"]["max_target_err_mm"],
}
json.dump(res, open(OUT, "w"), indent=1)
print("CHECK", json.dumps(res["summary"]), flush=True)
