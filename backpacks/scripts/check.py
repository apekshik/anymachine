"""Soft-goods rig check: sweep every control (and listed pairs), measure how far moving parts push into the body,
count triangle overlaps, and confirm out-of-range values are held at the limits.

blender -b --python check.py -- --blend out/x/x.blend --out out/x/check.json [--step 0.05] [--tol 4]

Penetration = signed distance of each moving-part vertex to the nearest body triangle (negative = inside, along the
body's outward normal). Soft goods touch by design (straps lie on fabric), so the pass rule is depth <= tol mm, not
zero contact; triangle overlap counts are reported alongside.
"""
import bpy, sys, os, json, math
sys.path.insert(0, os.path.dirname(__file__))
from softlib import set_controls
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:]
opt = lambda k, d=None, c=str: c(argv[argv.index(k) + 1]) if k in argv else d
bpy.ops.wm.open_mainfile(filepath=os.path.abspath(opt("--blend")))
OUT = os.path.abspath(opt("--out"))
STEP = opt("--step", 0.05, float)
TOL = opt("--tol", 4.0, float)
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
if arm.animation_data:
    arm.animation_data.action = None
spec = json.loads(arm["anymachine"])
ctl = {c["param"]: c for c in spec["controls"]}
defaults = {k: c["default"] for k, c in ctl.items()}
chk = spec["check"]


def group_mask(ob, groups, thresh=0.5):
    if not groups:
        return None
    missing = [name for name in groups if name not in ob.vertex_groups]
    if missing:
        raise ValueError(f"{ob.name}: unknown vertex groups for collision check: {', '.join(missing)}")
    indices = {ob.vertex_groups[name].index for name in groups}
    mask = [sum(g.weight for g in v.groups if g.group in indices) > thresh for v in ob.data.vertices]
    if not any(mask):
        raise ValueError(f"{ob.name}: collision check groups select no vertices: {', '.join(groups)}")
    return mask


def evaluated(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    oe = ob.evaluated_get(dg)
    m = oe.to_mesh()
    mw = oe.matrix_world
    vs = [mw @ v.co for v in m.vertices]
    m.calc_loop_triangles()
    tris = [tuple(t.vertices) for t in m.loop_triangles]
    oe.to_mesh_clear()
    return vs, tris


body_ob = bpy.data.objects[chk["body"]]
body_excl = group_mask(body_ob, chk.get("body_exclude_groups"))
movers = []
for m in chk["moving"]:
    o = bpy.data.objects[m["object"]]
    movers.append(dict(m, ob=o, mask=group_mask(o, m.get("groups"))))


RAYS = [Vector(d).normalized() for d in ((0.31, 0.12, 0.94), (-0.7, 0.2, -0.68), (0.15, -0.95, 0.27), (0.9, 0.35, -0.2), (-0.2, 0.8, 0.55))]


def inside(bvh, p):
    """Majority vote of ray-parity tests: robust on generated skins with holes (a hole flips one ray, not most)."""
    votes = 0
    for d in RAYS:
        o, hits = p.copy(), 0
        for _ in range(64):
            loc, nrm, fi, dist = bvh.ray_cast(o, d)
            if loc is None:
                break
            hits += 1
            o = loc + d * 1e-5
        votes += hits % 2
    return votes >= 3


def measure():
    bv, bt = evaluated(body_ob)
    if body_excl:
        bt = [t for t in bt if not any(body_excl[i] for i in t)]
    bvh = BVHTree.FromPolygons(bv, bt)
    res = {}
    for m in movers:
        mv, mt = evaluated(m["ob"])
        if m["mask"]:
            idx = [i for i, k in enumerate(m["mask"]) if k]
            mt = [t for t in mt if all(m["mask"][i] for i in t)]
        else:
            idx = range(len(mv))
        ex = [(Vector(p), r) for p, r in m.get("exclude_near", [])]
        exv = set(m.get("exclude_verts", []))
        if exv:
            idx = [i for i in idx if i not in exv]
        worst, n_in = 0.0, 0
        for i in idx:
            p = mv[i]
            if any((p - c).length < r for c, r in ex):
                continue
            loc, nrm, fi, d = bvh.find_nearest(p)
            if loc is None:
                continue
            s = (p - loc).dot(nrm)
            if s < 0 and d < 0.08 and inside(bvh, p):
                depth = -s
                if depth > TOL / 1000:
                    n_in += 1
                worst = max(worst, depth)
        mbvh = BVHTree.FromPolygons(mv, mt)
        ov = len(bvh.overlap(mbvh))
        res[m["name"]] = {"max_pen_mm": round(worst * 1000, 2), "verts_over_tol": n_in, "tri_overlaps": ov}
        if m["name"] in chk.get("floor", []):
            res[m["name"]]["min_z_mm"] = round(min(p.z for p in mv) * 1000, 2)
    return res


SELF = [(bpy.data.objects[s["object"]], s["ring"], s["min_level_gap"]) for s in chk.get("self", [])]


def self_hits():
    out = {}
    for o, ring, gap in SELF:
        v, t = evaluated(o)
        bv = BVHTree.FromPolygons(v, t)
        n = 0
        for a, b in bv.overlap(bv):
            la = min(t[a]) // ring
            lb = min(t[b]) // ring
            if abs(la - lb) >= gap:
                n += 1
        out[o.name] = n
    return out


def snapshot():
    out = []
    for o in bpy.data.objects:
        if o.type == "MESH" and (o.parent == arm or any(md.type == "ARMATURE" for md in o.modifiers)):
            out += evaluated(o)[0]
    return out


rows = []


def run(vals, tag):
    v = dict(defaults)
    v.update(vals)
    set_controls(arm, v)
    r = measure()
    if SELF:
        r["_self"] = self_hits()
    rows.append({"tag": tag, "vals": {k: round(x, 3) for k, x in vals.items()}, "parts": r})
    return r


n = int(round(1 / STEP))
for k in ctl:
    for i in range(n + 1):
        run({k: i / n}, f"sweep:{k}")
for a, b in chk.get("pairs", []):
    for i in range(5):
        for j in range(5):
            run({a: i / 4, b: j / 4}, f"pair:{a}x{b}")
# limits: out-of-range values must equal the clamped end poses
clamp = {}
for k in ctl:
    for bad, good in ((-0.3, 0.0), (1.4, 1.0)):
        set_controls(arm, dict(defaults, **{k: good}))
        A = snapshot()
        set_controls(arm, dict(defaults, **{k: bad}))
        Bs = snapshot()
        clamp[f"{k}={bad}"] = round(max((a - b).length for a, b in zip(A, Bs)) * 1000, 4)
set_controls(arm, defaults)
worst = {}
for r in rows:
    for p, m in r["parts"].items():
        if p == "_self":
            for on, nh in m.items():
                ws = worst.setdefault("self:" + on, {"max_pen_mm": 0, "at": None, "max_tri_overlaps": 0})
                if nh > ws["max_tri_overlaps"]:
                    ws["max_tri_overlaps"], ws["at"] = nh, {"tag": r["tag"], **r["vals"]}
            continue
        w = worst.setdefault(p, {"max_pen_mm": 0, "at": None, "max_tri_overlaps": 0})
        if m["max_pen_mm"] > w["max_pen_mm"]:
            w["max_pen_mm"], w["at"] = m["max_pen_mm"], {"tag": r["tag"], **r["vals"]}
        w["max_tri_overlaps"] = max(w["max_tri_overlaps"], m["tri_overlaps"])
        if "min_z_mm" in m:
            w["min_z_mm"] = min(w.get("min_z_mm", 1e9), m["min_z_mm"])
fails = {p: w for p, w in worst.items() if w["max_pen_mm"] > TOL or w.get("min_z_mm", 0) < -0.5 or (p.startswith("self:") and w["max_tri_overlaps"] > 0)}
res = {"bag": spec.get("bag"), "tol_mm": TOL, "states": len(rows), "pass": not fails and all(v < 0.01 for v in clamp.values()),
       "clamp_max_dev_mm": clamp, "worst_by_part": worst, "fails": list(fails), "rows": rows}
json.dump(res, open(OUT, "w"), indent=1)
print("CHECK", json.dumps({k: v for k, v in res.items() if k != "rows"}), flush=True)
