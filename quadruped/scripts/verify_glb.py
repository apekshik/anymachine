"""Re-import the GLB and confirm it: nodes, actions, extras, and that each action reproduces the planner's foot
centres (the same targets the .blend was checked against). Writes a JSON report.

blender -b --factory-startup --python verify_glb.py -- --glb out/quadruped.glb --out out/verify_glb.json
"""
import bpy, sys, os, json, math
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gait

argv = sys.argv[sys.argv.index("--") + 1:]
GLB, OUT = os.path.abspath(argv[argv.index("--glb") + 1]), os.path.abspath(argv[argv.index("--out") + 1])
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.fps = 30  # glTF times are seconds; import at the gait's fps so frames line up 1:1
bpy.ops.import_scene.gltf(filepath=GLB)
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
spec = json.loads(arm["anymachine"])
p = dict(gait.DEFAULTS)
for k in p:
    if k in arm.keys():
        p[k] = arm[k]
_, plan = gait.build_all(spec, p)
foot_rest = {n: Vector(spec["legs"][n]["foot"]) for n in gait.LEGS}
rep = {"objects": len(bpy.data.objects), "meshes": sorted(o.name for o in bpy.data.objects if o.type == "MESH"),
       "bones": [b.name for b in arm.data.bones], "extras": sorted(arm.keys()),
       "actions": {a.name: [round(x, 2) for x in a.frame_range] for a in bpy.data.actions}, "per_action": {}}
ad = arm.animation_data
for t in list(ad.nla_tracks):
    t.mute = True
missing_actions = []
for name in ("trot", "trot_forward", "idle", "sit", "stand"):
    cands = [a for a in bpy.data.actions if a.name == name or (a.name.startswith(name + "_") and not
             (name == "trot" and a.name.startswith("trot_forward")))]
    act = cands[0] if cands else None
    if act is None:
        rep["per_action"][name] = "MISSING"
        missing_actions.append(name)
        continue
    ad.action = act
    if getattr(ad, "action_slot", None) is None and len(getattr(act, "slots", [])):
        ad.action_slot = act.slots[0]
    frames = plan[name][0]
    f0 = int(round(act.frame_range[0]))
    err = 0.0
    for i, fr in enumerate(frames):
        sc.frame_set(f0 + i)
        for n in gait.LEGS:
            o = bpy.data.objects[f"{n}_foot"]
            # foot centre = centroid of the sphere mesh, posed
            vs = o.data.vertices
            ctr = sum((v.co for v in vs), Vector()) / len(vs)
            c = o.matrix_world @ ctr
            err = max(err, (c - fr["feet"][n]).length)
    rep["per_action"][name] = {"gltf_action": act.name, "frames": len(frames), "max_foot_err_mm": round(err * 1000, 3)}
    print("VERIFY", name, rep["per_action"][name], flush=True)
json.dump(rep, open(OUT, "w"), indent=1)
if missing_actions:
    raise RuntimeError("Missing required GLB actions: " + ", ".join(missing_actions))
print("GLB_OK", json.dumps({k: rep[k] for k in ("objects", "actions", "per_action")}), flush=True)
