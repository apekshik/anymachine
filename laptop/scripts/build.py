"""AnyMachine experiment 1: generated laptop GLB -> rigged laptop (.blend) with one working lid hinge.

blender -b --factory-startup --python build.py -- --glb gen/tripo/model.glb --gen tripo --ui refs/screen_ui_0.png \
    --out out/laptop.blend [--width 0.32] [--lid-t 0.005] [--max-deg 135] [--gap 0.001]

Pipeline: orient + scale -> measure (deck plane, lid line, hinge line) -> cut the generated mesh at the hinge and keep
the BASE (cap the cut) -> REBUILD the lid as a clean slab whose back edge is a cylinder coaxial with the hinge axis ->
emissive screen with an invented UI -> armature (root + lid_hinge), Limit Rotation, `open` (0..1) custom prop driver.
"""
import bpy, bmesh, sys, math, json, os
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]


def opt(k, d=None, cast=str):
    return cast(argv[argv.index(k) + 1]) if k in argv else d


GLB, GEN, UI, OUT = opt("--glb"), opt("--gen", "tripo"), opt("--ui"), opt("--out")
WIDTH = opt("--width", 0.32, float)
LID_T = opt("--lid-t", 0.005, float)
MAX_DEG = opt("--max-deg", 135.0, float)
GAP = opt("--gap", 0.001, float)
report = {"gen": GEN, "glb": GLB}

# ---------------------------------------------------------------- import, orient, scale (normalize.py logic)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
if not meshes:
    raise ValueError("The input GLB contains no mesh objects")
if GEN.startswith("tripo"):
    for o in bpy.context.scene.objects:
        o.rotation_mode = "QUATERNION"
        o.rotation_quaternion = (1, 0, 0, 0)
    bpy.context.view_layer.update()
for o in meshes:
    mw = o.matrix_world.copy()
    o.parent = None
    o.data.transform(mw)
    o.matrix_world = Matrix.Identity(4)
for o in [o for o in bpy.context.scene.objects if o.type != "MESH"]:
    bpy.data.objects.remove(o)
vl = bpy.context.view_layer
for o in meshes:
    o.select_set(True)
vl.objects.active = meshes[0]
if len(meshes) > 1:
    bpy.ops.object.join()
gen = vl.objects.active
me = gen.data
if GEN.startswith("tripo"):
    me.transform(Matrix.Rotation(math.radians(-90), 4, "Z"))
vs = [v.co for v in me.vertices]
if not vs:
    raise ValueError("The input GLB mesh has no vertices")
lo = Vector([min(v[i] for v in vs) for i in range(3)])
hi = Vector([max(v[i] for v in vs) for i in range(3)])
source_width = hi.x - lo.x
if source_width <= 0:
    raise ValueError("The input GLB has no width after orientation")
s = WIDTH / source_width
me.transform(Matrix.Diagonal((s, s, s, 1)) @ Matrix.Translation(-Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))))
vs = [v.co.copy() for v in me.vertices]
lo = Vector([min(v[i] for v in vs) for i in range(3)])
hi = Vector([max(v[i] for v in vs) for i in range(3)])
report["gen_dims_m"] = [round(x, 4) for x in hi - lo]


# ---------------------------------------------------------------- measure
def pct(a, p):
    a = sorted(a)
    return a[min(len(a) - 1, int(p * len(a)))]


# deck: front half of the footprint; its 98th-percentile height is the top of the keyboard deck
front = [v for v in vs if v.y < lo.y + 0.55 * (hi.y - lo.y) and abs(v.x) < 0.12]
if not front:
    raise ValueError("Could not measure the front deck; check the input GLB orientation")
deck_top_front = pct([v.z for v in front], 0.98)
lid = [v for v in vs if v.z > deck_top_front + 0.012]
if not lid:
    raise ValueError("Could not measure a lid above the deck; use a source mesh with the lid open")
cy = sum(v.y for v in lid) / len(lid)
cz = sum(v.z for v in lid) / len(lid)
syy = sum((v.y - cy) ** 2 for v in lid)
szz = sum((v.z - cz) ** 2 for v in lid)
syz = sum((v.y - cy) * (v.z - cz) for v in lid)
ang = 0.5 * math.atan2(2 * syz, syy - szz)  # principal axis of the lid's YZ cloud
d = Vector((0, math.cos(ang), math.sin(ang)))
if d.z < 0:
    d = -d
lid_angle = math.degrees(math.atan2(d.z, -d.y))  # lid-to-deck angle, measured from the front
# deck plane: per 1 cm Y bin, the area-weighted MEDIAN height of up-facing faces (keytops, notches and hinge parts are
# outliers either way), then an area-weighted line fit. A zmax fit doubled the slope (2.1 vs 1.05 deg) on this mesh.
y_lid_foot = min(v.y for v in lid)
bins = {}
for p in me.polygons:
    c = p.center
    if p.normal.z > 0.9 and abs(c.x) < WIDTH * 0.44 and c.z < deck_top_front + 0.006 and lo.y + 0.005 < c.y < y_lid_foot - 0.02:
        bins.setdefault(int((c.y - lo.y) / 0.01), []).append((c.z, p.area))
pts = []
for bi, l in bins.items():
    l.sort()
    tot = sum(a_ for _, a_ in l)
    acc = 0
    for z, a_ in l:
        acc += a_
        if acc >= tot / 2:
            pts.append((lo.y + (bi + 0.5) * 0.01, z, tot))
            break
sw_ = sum(p[2] for p in pts)
if len(pts) < 2 or sw_ <= 0:
    raise ValueError("Could not fit the deck plane; use a mesh with a visible keyboard deck")
my = sum(p[0] * p[2] for p in pts) / sw_
mz = sum(p[1] * p[2] for p in pts) / sw_
slope = sum(p[2] * (p[0] - my) * (p[1] - mz) for p in pts) / sum(p[2] * (p[0] - my) ** 2 for p in pts)


def deck_z(y):
    return mz + slope * (y - my)


# hinge line: where the lid line meets the deck plane (solve cz + t*d.z = deck_z(cy + t*d.y))
rise = d.z - slope * d.y
if math.isclose(rise, 0, abs_tol=1e-9):
    raise ValueError("The lid and deck do not define a hinge; use a source mesh with the lid open")
t = (deck_z(cy) - cz) / rise
y_h = cy + t * d.y
hinge_pt = Vector((0, y_h, deck_z(y_h)))
L_gen = max((v - hinge_pt).dot(d) for v in lid)
W_gen = max(v.x for v in lid) - min(v.x for v in lid)
nrm = Vector((0, -d.z, d.y))
lid_thick = pct([abs((v - Vector((0, cy, cz))).dot(nrm)) for v in lid], 0.98) * 2
report.update(deck_slope_deg=round(math.degrees(math.atan(slope)), 2), gen_lid_open_deg=round(lid_angle, 1),
              hinge_y=round(y_h, 4), hinge_deck_z=round(deck_z(y_h), 4), gen_lid_len=round(L_gen, 4),
              gen_lid_width=round(W_gen, 4), gen_lid_thickness_approx=round(lid_thick, 4),
              deck_top_front=round(deck_top_front, 4))
print("MEASURE", json.dumps(report), flush=True)

# ---------------------------------------------------------------- base: cut the generated mesh at the hinge, cap it
# The hinge axis sits t/2 in front of the cut, at deck + gap + t/2, so the lid's barrel is flush with the base back.
# The lid line meets the deck ~2 cm in front of the real back edge (the generated lid sits on a hinge block), so cut at
# the back edge of the BOTTOM shell instead and treat the strip behind the lid line as remnant to strip and re-cap.
y_back = pct([v.y for v in vs if v.z < 0.003], 0.995)
y_cut = max(y_h, y_back)
report["y_back_bottom_shell"] = round(y_back, 4)
axis = Vector((0, y_cut - LID_T / 2, deck_z(y_cut - LID_T / 2) + GAP + LID_T / 2))
bm = bmesh.new()
bm.from_mesh(me)
bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, y_cut, 0), plane_no=(0, 1, 0),
                       clear_outer=True)
# The generated shell is not usable as-is: ~48k open boundary edges (Tripo splits at UV seams), an open side wall, and
# a hinge block fused to the lid stub. A global holes_fill fanned giant triangles across the keyboard. So:
#   keep only the generated TOP SKIN (keys, deck, trackpad: the detail worth keeping), and
#   REBUILD the shell as a clean bevelled wedge whose top follows the fitted deck plane, back edge = hinge line.
report["gen_boundary_edges"] = sum(1 for e in bm.edges if e.is_boundary)
SKIN_DEPTH = 0.0025
bm.to_mesh(me)
bm.free()
gen.name = me.name = "base"
base = gen
sm_ = bpy.data.meshes.new("shell")
bm = bmesh.new()
x0, x1 = -WIDTH / 2 + 0.0003, WIDTH / 2 - 0.0003
ya, yb = lo.y + 0.0003, y_cut
za, zb = deck_z(ya) - 0.0004, deck_z(yb) - 0.0004       # 0.4 mm under the deck: the skin sits on top of it
vv = [bm.verts.new(p) for p in ((x0, ya, 0), (x1, ya, 0), (x1, yb, 0), (x0, yb, 0),
                                (x0, ya, za), (x1, ya, za), (x1, yb, zb), (x0, yb, zb))]
for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
    bm.faces.new([vv[i] for i in f])
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
bm.to_mesh(sm_)
bm.free()
blk = bpy.data.objects.new("shell", sm_)
bpy.context.scene.collection.objects.link(blk)
bv = blk.modifiers.new("bev", "BEVEL")
bv.width = 0.003
bv.segments = 5
vl.objects.active = blk
with bpy.context.temp_override(object=blk, active_object=blk):
    bpy.ops.object.modifier_apply(modifier="bev")
report["shell_m"] = [round(x1 - x0, 4), round(yb - ya, 4), round(za, 4), round(zb, 4)]
vl.update()

# ---------------------------------------------------------------- lid: rebuilt slab (stadium profile, extruded on X)
W = W_gen if 0.8 * WIDTH < W_gen <= WIDTH else WIDTH * 0.985
# the closed lid covers the base footprint (the generated lid was ~2.5 cm shorter than the base: a generator guess)
L = axis.y - lo.y - 0.0008
rr = LID_T / 2
prof = []  # YZ profile in the hinge frame (axis at origin, lid toward -Y)
for i in range(13):  # back: semicircle centred ON the axis -> it spins in place
    a = -math.pi / 2 + math.pi * i / 12
    prof.append((rr * math.cos(a), rr * math.sin(a)))
for i in range(13):  # front: rounded lip
    a = math.pi / 2 + math.pi * i / 12
    prof.append((-(L - rr) + rr * math.cos(a), rr * math.sin(a)))
lm = bpy.data.meshes.new("lid")
bm = bmesh.new()
left = [bm.verts.new((-W / 2, y, z)) for y, z in prof]
right = [bm.verts.new((W / 2, y, z)) for y, z in prof]
n = len(prof)
for i in range(n):
    j = (i + 1) % n
    bm.faces.new((left[i], left[j], right[j], right[i]))
bm.faces.new(list(reversed(left)))
bm.faces.new(right)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
bm.to_mesh(lm)
bm.free()
lid_ob = bpy.data.objects.new("lid", lm)
bpy.context.scene.collection.objects.link(lid_ob)
# round the four corners of the slab in plan view (edges parallel to Z-ish: the side caps' outline corners)
bev = lid_ob.modifiers.new("corners", "BEVEL")
bev.width = 0.0015
bev.segments = 3
bev.limit_method = "ANGLE"
bev.angle_limit = math.radians(60)
vl.objects.active = lid_ob
with bpy.context.temp_override(object=lid_ob, active_object=lid_ob):
    bpy.ops.object.modifier_apply(modifier="corners")
# screen quad just below the inner (z = -t/2) face; bezel 7 mm sides/top, 14 mm chin by the hinge
bz, chin = 0.007, 0.012
sw, sh = W - 2 * bz, L - bz - chin
sm = bpy.data.meshes.new("screen")
bm = bmesh.new()
y0, y1 = -chin, -chin - sh
zq = -rr - 0.0002
q = [bm.verts.new(p) for p in ((-sw / 2, y0, zq), (-sw / 2, y1, zq), (sw / 2, y1, zq), (sw / 2, y0, zq))]
f = bm.faces.new(q)
f.normal_update()
if f.normal.z > 0:
    f.normal_flip()
uvl = bm.loops.layers.uv.new("UVMap")
# UI image is 16:9; crop to the screen aspect. u along +X, v from the chin edge (bottom of UI) to the far edge (top)
img_aspect = 16 / 9
scr_aspect = sw / sh
cu = min(1, scr_aspect / img_aspect)
cv = min(1, img_aspect / scr_aspect)
for loop in f.loops:
    p = loop.vert.co
    u = (p.x + sw / 2) / sw
    v = (y0 - p.y) / sh
    loop[uvl].uv = (0.5 + (u - 0.5) * cu, 0.5 + (v - 0.5) * cv)
bm.to_mesh(sm)
bm.free()
screen = bpy.data.objects.new("screen", sm)
bpy.context.scene.collection.objects.link(screen)


def mat(name, base_col, metal=0.0, rough=0.4):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*base_col, 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    return m


# aluminium tint: sample the base's colour texture on its underside faces so the rebuilt lid matches
col = (0.2, 0.2, 0.21)
try:
    m0 = base.data.materials[0]
    ti = next(nd for nd in m0.node_tree.nodes if nd.type == "TEX_IMAGE" and
              any(l.to_socket.name == "Base Color" for l in nd.outputs["Color"].links))
    img = ti.image
    W_, H_ = img.size
    px = img.pixels[:]
    uvd = base.data.uv_layers.active.data
    acc, k = [0, 0, 0], 0
    for p in base.data.polygons:
        if p.normal.z < -0.95:  # bottom shell: pure aluminium, no keys or screen
            for li in p.loop_indices:
                u, v = uvd[li].uv
                xi = min(W_ - 1, max(0, int(u % 1 * W_)))
                yi = min(H_ - 1, max(0, int(v % 1 * H_)))
                i4 = 4 * (yi * W_ + xi)
                acc[0] += px[i4]; acc[1] += px[i4 + 1]; acc[2] += px[i4 + 2]
                k += 1
    if k:
        srgb = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4  # pixels are sRGB-encoded
        col = tuple(srgb(c / k) for c in acc)
        report["alu_sampled_from"] = img.name
except Exception as e:  # keep the default tint
    report["alu_sample_error"] = repr(e)
report["alu_rgb"] = [round(c, 3) for c in col]
alu = mat("aluminium", col, metal=0.7, rough=0.5)
# the generator metallic map turns black keycaps into chrome; replace it with a constant (deck reads as anodised metal)
for m in base.data.materials:
    for nd in m.node_tree.nodes:
        if nd.type == "BSDF_PRINCIPLED":
            for l in list(nd.inputs["Metallic"].links):
                m.node_tree.links.remove(l)
            nd.inputs["Metallic"].default_value = 0.25
            for l in list(nd.inputs["Roughness"].links):  # glossy roughness map turned keycaps into mirrors
                m.node_tree.links.remove(l)
            nd.inputs["Roughness"].default_value = 0.5
bezel = mat("bezel_glass", (0.008, 0.008, 0.01), rough=0.06)
lm.materials.append(alu)
lm.materials.append(bezel)
for p in lm.polygons:
    p.material_index = 1 if p.normal.z < -0.95 else 0
sc_mat = bpy.data.materials.new("screen_ui")
sc_mat.use_nodes = True
nt = sc_mat.node_tree
b = nt.nodes["Principled BSDF"]
tex = nt.nodes.new("ShaderNodeTexImage")
tex.image = bpy.data.images.load(os.path.abspath(UI))
tex.image.pack()
tex.extension = "EXTEND"
b.inputs["Base Color"].default_value = (0.0, 0.0, 0.0, 1)  # the panel is black glass; the image is all emission
nt.links.new(tex.outputs["Color"], b.inputs["Emission Color"])
b.inputs["Emission Strength"].default_value = 2.5
b.inputs["Roughness"].default_value = 0.15
b.inputs["Specular IOR Level"].default_value = 0.25
sm.materials.append(sc_mat)

# trim the generated base to its top skin, then join the rebuilt shell into the base part
bm = bmesh.new()
bm.from_mesh(base.data)
kill = [f for f in bm.faces if f.calc_center_median().z < deck_z(f.calc_center_median().y) - SKIN_DEPTH
        or f.calc_center_median().z > deck_z(f.calc_center_median().y) + 0.003
        or f.calc_center_median().y > y_cut - LID_T - 0.002 or abs(f.calc_center_median().x) > WIDTH / 2 - 0.002]
bmesh.ops.delete(bm, geom=kill, context="FACES")
report["skin_faces_kept"] = len(bm.faces)
# closed-pose clearance: the lid must sit above the tallest thing left on the deck (keytops, bumps), not the plane
prot = max(v.co.z - deck_z(v.co.y) for v in bm.verts)
gap = max(GAP, prot + 0.0005)
axis.z += gap - GAP
report["skin_max_above_deck_mm"] = round(prot * 1000, 2)
report["closed_gap_mm"] = round(gap * 1000, 2)
bm.to_mesh(base.data)
bm.free()
# hinge pedestal: a rounded strip under the lid barrel so the barrel visibly rests on the base (0.3 mm clearance)
ped_top = axis.z - LID_T / 2 - 0.0003
bpy.ops.mesh.primitive_cube_add(size=1)
ped = bpy.context.active_object
ped.name = "hinge_pedestal"
pz0 = deck_z(axis.y) - 0.001
ped.location = (0, axis.y, (pz0 + ped_top) / 2)
ped.scale = (W * 0.92, LID_T * 0.9, ped_top - pz0)
bpy.ops.object.transform_apply(location=True, scale=True)
pbv = ped.modifiers.new("bev", "BEVEL")
pbv.width = 0.0006
pbv.segments = 2
with bpy.context.temp_override(object=ped, active_object=ped):
    bpy.ops.object.modifier_apply(modifier="bev")
ped.data.materials.append(alu)
report["pedestal_h_mm"] = round((ped_top - deck_z(axis.y)) * 1000, 2)
blk.data.materials.append(alu)
ped.select_set(True)
for o in bpy.context.scene.objects:
    o.select_set(False)
blk.select_set(True)
ped.select_set(True)
for o_ in (blk, ped):
    vl.objects.active = o_
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(35))
base.select_set(True)
vl.objects.active = base
bpy.ops.object.join()
base = vl.objects.active
base.name = "base"
vl.update()
report["base_dims_m"] = [round(x, 4) for x in base.dimensions]

for o in bpy.context.scene.objects:
    o.select_set(False)
lid_ob.select_set(True)
vl.objects.active = lid_ob
bpy.ops.object.shade_smooth_by_angle(angle=math.radians(35))

# place lid + screen: hinge frame -> world (deck tilt, then axis position)
tilt = math.atan(slope)  # deck rises toward +Y, so the closed lid tips down toward the front by the same angle
M = Matrix.Translation(axis) @ Matrix.Rotation(tilt, 4, "X")
lm.transform(M)
sm.transform(M)

# ---------------------------------------------------------------- rig
arm_d = bpy.data.armatures.new("laptop_rig")
arm = bpy.data.objects.new("laptop_rig", arm_d)
bpy.context.scene.collection.objects.link(arm)
for o in bpy.context.scene.objects:
    o.select_set(False)
vl.objects.active = arm
arm.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
root = arm_d.edit_bones.new("root")
root.head = (0, 0, 0)
root.tail = (0, 0.05, 0)
hb = arm_d.edit_bones.new("lid_hinge")
hb.head = axis
hb.tail = axis + Vector((0.06, 0, 0))
hb.roll = 0
hb.parent = root
hb.use_connect = False
bpy.ops.object.mode_set(mode="POSE")
pb = arm.pose.bones["lid_hinge"]
pb.rotation_mode = "XYZ"
lim = pb.constraints.new("LIMIT_ROTATION")
lim.owner_space = "LOCAL"
lim.use_limit_x = lim.use_limit_y = lim.use_limit_z = True
lim.min_y, lim.max_y = math.radians(-MAX_DEG), 0.0  # bone Y == world +X; opening is a negative turn
bpy.ops.object.mode_set(mode="OBJECT")
arm["open"] = 0.0
ui = arm.id_properties_ui("open")
ui.update(min=0.0, max=1.0, soft_min=0.0, soft_max=1.0, description="0 closed, 1 fully open")
arm["max_deg"] = MAX_DEG
fc = pb.driver_add("rotation_euler", 1)
drv = fc.driver
drv.type = "SCRIPTED"
var = drv.variables.new()
var.name = "open"
var.type = "SINGLE_PROP"
var.targets[0].id = arm
var.targets[0].data_path = '["open"]'
drv.expression = f"-open*{math.radians(MAX_DEG):.6f}"
# screen brightness follows the lid: dark when closed, fully on past ~25 deg
fc2 = sc_mat.node_tree.driver_add(f'nodes["{b.name}"].inputs[{list(b.inputs).index(b.inputs["Emission Strength"])}].default_value')
ed = fc2.driver
ed.type = "SCRIPTED"
v2 = ed.variables.new()
v2.name = "open"
v2.type = "SINGLE_PROP"
v2.targets[0].id_type = "OBJECT"
v2.targets[0].id = arm
v2.targets[0].data_path = '["open"]'
ed.expression = "2.5*min(1.0, max(0.0, (open-0.08)*10))"


def parent_to(ob, bone):
    vl.update()
    mw = ob.matrix_world.copy()
    ob.parent = arm
    if bone:
        ob.parent_type = "BONE"
        ob.parent_bone = bone
    vl.update()
    ob.matrix_world = mw


parent_to(base, "root")
parent_to(lid_ob, "lid_hinge")
parent_to(screen, "lid_hinge")
joint = {"name": "lid_hinge", "type": "hinge", "parent": "base", "child": ["lid", "screen"],
         "axis_origin_m": [round(x, 5) for x in axis], "axis_dir": [1, 0, 0],
         "limits_deg": [0, MAX_DEG], "param": "open", "param_map": f"angle_deg = open * {MAX_DEG}"}
arm["anymachine"] = json.dumps({"joints": [joint]})
report["joint"] = joint
report["lid_built"] = {"W": round(W, 4), "L": round(L, 4), "t": LID_T}

# ---------------------------------------------------------------- the PARAMETER is what gets animated
sc = bpy.context.scene
sc.render.fps = 24
sc.frame_start, sc.frame_end = 1, 96
for fr, val in ((1, 0), (8, 0), (44, 1), (54, 1), (90, 0), (96, 0)):
    arm["open"] = float(val)
    arm.keyframe_insert('["open"]', frame=fr)
sc.frame_set(1)
OUTA = os.path.abspath(OUT)
os.makedirs(os.path.dirname(OUTA), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=OUTA)
json.dump(report, open(os.path.splitext(OUTA)[0] + "_build.json", "w"), indent=1)
print("BUILT", json.dumps(report), flush=True)
