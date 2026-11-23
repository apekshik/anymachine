"""Export the rigged laptop to GLB with baked hinge animations (drivers don't survive glTF).

blender -b --python export.py -- --blend out/laptop.blend --out out/laptop.glb
Actions: `open_close` (the 4 s demo loop) and `open_param` (1 s, linear 0 -> max_deg: seek to t = open to pose any value).
The joint spec rides along as glTF extras on the rig node (`anymachine`), plus `open` / `max_deg`.
"""
import bpy, sys, os, math

argv = sys.argv[sys.argv.index("--") + 1:]
blend, out = os.path.abspath(argv[argv.index("--blend") + 1]), os.path.abspath(argv[argv.index("--out") + 1])
bpy.ops.wm.open_mainfile(filepath=blend)
sc = bpy.context.scene
arm = bpy.data.objects["laptop_rig"]
pb = arm.pose.bones["lid_hinge"]
MAX = arm["max_deg"]
# sample the keyed parameter BEFORE dropping the driver/action
demo = []
for f in range(sc.frame_start, sc.frame_end + 1):
    sc.frame_set(f)
    demo.append((f, float(arm["open"])))
pb.driver_remove("rotation_euler", 1)
arm.animation_data.action = None
pb.rotation_mode = "QUATERNION"


def bake(name, samples):
    act = bpy.data.actions.new(name)
    arm.animation_data.action = act
    for f, o in samples:
        a = -math.radians(o * MAX)
        pb.rotation_quaternion = (math.cos(a / 2), 0, math.sin(a / 2), 0)  # about bone Y (= world X)
        pb.keyframe_insert("rotation_quaternion", frame=f)
    act.use_fake_user = True
    trk = arm.animation_data.nla_tracks.new()
    trk.name = name
    trk.strips.new(name, int(samples[0][0]), act)
    arm.animation_data.action = None
    return act


bake("open_close", demo)
bake("open_param", [(1 + i, i / 24) for i in range(25)])  # 24 fps: t in seconds == open
pb.rotation_quaternion = (1, 0, 0, 0)
# textures <= 2K (normalize.py rule); repack only what was scaled
for img in bpy.data.images:
    width, height = img.size
    long_edge = max(width, height)
    if long_edge > 2048:
        img.scale(max(1, width * 2048 // long_edge), max(1, height * 2048 // long_edge))
        img.pack()
for o in bpy.data.objects:
    o.select_set(o.name in ("laptop_rig", "base", "lid", "screen"))
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=True, export_apply=True, export_yup=True,
                          export_animations=True, export_animation_mode="NLA_TRACKS", export_extras=True,
                          export_force_sampling=True)
print("EXPORTED", out, os.path.getsize(out) // 1024, "KB", flush=True)
