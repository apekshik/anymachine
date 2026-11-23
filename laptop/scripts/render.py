"""Render the rigged laptop.

blender -b --python anyscene/builder/blender_gpu.py --python render.py -- --blend out/laptop.blend --out out/render \
    (--stills 0,90,135 | --anim) [--engine CYCLES|EEVEE] [--device CPU|GPU] [--resx 1600 --resy 900] [--samples 64] [--cam persp|side|front|hinge]
"""
import bpy, sys, os, math
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]


def opt(k, d=None, cast=str):
    return cast(argv[argv.index(k) + 1]) if k in argv else d


BLEND, OUT = opt("--blend"), os.path.abspath(opt("--out"))
ENGINE = opt("--engine", "CYCLES")
DEVICE = opt("--device", "GPU")
SAMPLES = opt("--samples", 64, int)
CAM = opt("--cam", "persp")
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=os.path.abspath(BLEND))
sc = bpy.context.scene
arm = bpy.data.objects["laptop_rig"]
rx = opt("--resx", 1600, int)
ry = opt("--resy", 900, int)
sc.render.resolution_x, sc.render.resolution_y = rx, ry
sc.render.engine = "CYCLES" if ENGINE == "CYCLES" else "BLENDER_EEVEE"
if ENGINE == "CYCLES":
    sc.cycles.samples = SAMPLES
    sc.cycles.use_denoising = True
    sc.cycles.device = DEVICE
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"

# studio: floor + world + key/fill/rim
w = bpy.data.worlds.new("studio")
sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.8, 0.82, 0.85, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 0.12
bpy.ops.mesh.primitive_plane_add(size=6, location=(0, 0, 0))
floor = bpy.context.active_object
fm = bpy.data.materials.new("floor")
fm.use_nodes = True
fm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.30, 0.31, 0.33, 1)
fm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.55
floor.data.materials.append(fm)


def light(name, loc, energy, size, color=(1, 1, 1)):
    l = bpy.data.lights.new(name, "AREA")
    l.energy, l.size, l.color = energy, size, color
    o = bpy.data.objects.new(name, l)
    sc.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = (-Vector(loc)).to_track_quat("-Z", "Y").to_euler()


light("key", (-0.6, -0.7, 0.9), 70, 0.8)
light("fill", (0.8, -0.4, 0.4), 30, 0.8, (0.9, 0.95, 1))
light("rim", (0.3, 0.9, 0.7), 60, 0.5)

cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
tgt = Vector((0, 0.01, 0.07))
views = {"persp": (Vector((-0.48, -0.72, 0.42)), 50), "side": (Vector((0.85, 0.0, 0.0)), 50),
         "front": (Vector((0, -0.85, 0.25)), 50), "hinge": (Vector((0.6, 0.0, 0.0)), 50)}
if CAM == "hinge":  # close orthographic profile of the hinge axis
    import json as _j
    ax = _j.loads(arm["anymachine"])["joints"][0]["axis_origin_m"]
    tgt = Vector((0, ax[1] - 0.01, ax[2] + 0.005))
loc, lens = views[CAM]


def aim(tz):
    t = Vector((tgt.x, tgt.y, tz))
    cam.location = t + loc
    cam.rotation_euler = (-loc).to_track_quat("-Z", "Y").to_euler()


cam.data.lens = lens
aim(tgt.z if CAM != "persp" else 0.065)
if CAM in ("side", "hinge"):
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 0.5 if CAM == "side" else 0.07
    pass


def set_open(val):
    if arm.animation_data and arm.animation_data.action:
        arm.animation_data.action = None
    arm["open"] = val
    arm.update_tag()
    sc.frame_set(sc.frame_current)
    bpy.context.view_layer.update()


if "--anim" in argv:
    sc.render.filepath = os.path.join(OUT, "f_")
    sc.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(animation=True)
else:
    for deg in [float(x) for x in opt("--stills", "0,90,135").split(",")]:
        set_open(deg / arm["max_deg"])
        if CAM == "persp":
            aim(0.02 + 0.05 * min(1.0, deg / 90))
        sc.render.filepath = os.path.join(OUT, f"{CAM}_{int(deg):03d}.png")
        bpy.ops.render.render(write_still=True)
print("RENDERED", OUT, flush=True)
