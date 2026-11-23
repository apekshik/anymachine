"""Check renders, close-ups, clash check and video frames for the Stilt-walker.
Run:  blender.exe --background stilt.blend --python render_stilt.py -- [views...] [--engine cycles] [--samples N] [--frames DIR] [--step N] [--tag T]
Stills:  front left rear right top 3q 3q_rear cu (the seven close-ups that match refs/closeup_*.png) poses
Checks:  check (part-vs-part intersections over every action, compared with the rest pose)
Video frames (need --frames DIR):  walk reach head turntable assembly
"""
import bpy, sys, os, json
from math import radians, sin, cos, pi
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from zlib import crc32

HERE = os.path.dirname(os.path.abspath(__file__))
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
SAMPLES, FRAMES, ENGINE, STEP, TAG, RES = 64, None, 'EEVEE', 1, '', None
views = []
i = 0
while i < len(argv):
    if argv[i] == '--samples':
        SAMPLES = int(argv[i + 1]); i += 2
    elif argv[i] == '--frames':
        FRAMES = argv[i + 1]; i += 2
    elif argv[i] == '--engine':
        ENGINE = argv[i + 1].upper(); i += 2
    elif argv[i] == '--step':
        STEP = int(argv[i + 1]); i += 2
    elif argv[i] == '--tag':
        TAG = argv[i + 1]; i += 2
    elif argv[i] == '--res':
        RES = tuple(int(v) for v in argv[i + 1].split('x')); i += 2
    else:
        views.append(argv[i]); i += 1
if not views:
    views = ['front', 'left', 'rear', 'top', '3q', '3q_rear', 'cu']
OUT = os.path.join(HERE, 'renders')
os.makedirs(OUT, exist_ok=True)
INFO = json.load(open(os.path.join(HERE, 'stilt_info.json')))

scn = bpy.context.scene
ARM = bpy.data.objects['Armature']
PARTS = [o for o in bpy.data.collections['Stilt'].objects if o.type == 'MESH']
HUMAN = bpy.data.objects['Scale_Human']
EMIT = bpy.data.materials['M_Stilt_Emit_Sensor']
scn.render.engine = 'CYCLES' if ENGINE == 'CYCLES' else 'BLENDER_EEVEE'
if ENGINE != 'CYCLES':
    try:
        scn.eevee.taa_render_samples = 32
        scn.eevee.use_raytracing = True
        scn.eevee.use_shadows = True
    except Exception as _e:
        print('eevee opts', _e)
else:
    prefs = bpy.context.preferences.addons['cycles'].preferences
    for t in ('OPTIX', 'CUDA'):
        try:
            prefs.compute_device_type = t
            prefs.get_devices()
            for d in prefs.devices:
                d.use = True
            scn.cycles.device = 'GPU'
            break
        except Exception:
            pass
    scn.cycles.samples = SAMPLES
    scn.cycles.use_denoising = True
scn.render.film_transparent = False
scn.view_settings.view_transform = 'AgX'
try:
    scn.view_settings.look = 'AgX - Medium High Contrast'
except Exception:
    pass
scn.render.image_settings.file_format = 'PNG'
cam = scn.camera
cam_d = cam.data
cam_d.clip_start, cam_d.clip_end = 0.3, 3000


def look(loc, target, ortho=None, lens=50):
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    if ortho:
        cam_d.type = 'ORTHO'
        cam_d.ortho_scale = ortho
    else:
        cam_d.type = 'PERSP'
        cam_d.lens = lens


def render(name, res=(1600, 900)):
    scn.render.resolution_x, scn.render.resolution_y = res
    scn.render.filepath = os.path.join(OUT, 'stilt_' + (TAG + '_' if TAG else '') + name + '.png')
    bpy.ops.render.render(write_still=True)
    print('RENDERED', name)


def set_action(name):
    ad = ARM.animation_data
    if name is None:
        ad.action = None
        for pb in ARM.pose.bones:
            pb.location = (0, 0, 0)
            pb.rotation_quaternion = (1, 0, 0, 0)
        ARM['sensor_light'] = 1.0
        return
    act = bpy.data.actions[name]
    ad.action = act
    try:
        ad.action_slot = act.slots[0]
    except Exception as e:
        print('slot', e)


def light_off_driver():
    """Take the emission off its driver so a script can set it directly."""
    nt = EMIT.node_tree
    try:
        nt.animation_data_clear()
    except Exception:
        pass
    return nt.nodes['Principled BSDF'].inputs['Emission Strength']


# ---------------------------------------------------------------------------------------------- clash check
def world_bvh(ob, dg):
    e = ob.evaluated_get(dg)
    me = e.to_mesh()
    mw = e.matrix_world
    t = BVHTree.FromPolygons([mw @ v.co for v in me.vertices], [tuple(p.vertices) for p in me.polygons], epsilon=0.0)
    e.to_mesh_clear()
    return t


def bone_of(ob):
    return ob.vertex_groups[0].name if len(ob.vertex_groups) == 1 else 'smooth'


def overlaps(frame):
    scn.frame_set(frame)
    dg = bpy.context.evaluated_depsgraph_get()
    trees = [(o.name, bone_of(o), world_bvh(o, dg)) for o in PARTS]
    out = {}
    for a in range(len(trees)):
        for b in range(a + 1, len(trees)):
            if trees[a][1] == trees[b][1]:
                continue
            n = len(trees[a][2].overlap(trees[b][2]))
            if n:
                out[(trees[a][0], trees[b][0])] = n
    return out


def check():
    set_action(None)
    rest = overlaps(1)
    print('REST OVERLAPS (joints by design):', len(rest))
    for name, d in INFO['actions'].items():
        set_action(name)
        worst = {}
        for f in range(1, d['frames'] + 1, 6):
            for k, n in overlaps(f).items():
                if k not in rest or n > rest[k] * 3 + 60:
                    if n > worst.get(k, (0, 0))[0]:
                        worst[k] = (n, f)
        print('ACTION', name, 'NEW OVERLAPS:', len(worst))
        for k, (n, f) in sorted(worst.items(), key=lambda q: -q[1][0])[:60]:
            print('  CLASH', k[0], 'x', k[1], 'tris', n, 'frame', f)


# ---------------------------------------------------------------------------------------------- video frames
def sm(a, b, x):
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def frames_out(n, fn, res):
    os.makedirs(FRAMES, exist_ok=True)
    scn.render.resolution_x, scn.render.resolution_y = RES or res
    k = 0
    for f in range(1, n + 1, STEP):
        fn(f)
        scn.render.filepath = os.path.join(FRAMES, 'f_%04d.png' % k)
        bpy.ops.render.render(write_still=True)
        k += 1
    print('ANIM FRAMES', k)


def anim_walk():
    set_action('A_Stilt_Walk')
    WK = INFO['walk']
    WN = WK['frames']
    adv = WK['stride'] / (1 - WK['swing']) / WN                         # ground speed that keeps the planted feet still
    HUMAN.location = (17.0, 9.0, 0.0)
    N = WN * 3

    def fn(f):
        scn.frame_set((f - 1) % WN + 1)
        ARM.location = (-12.0 + adv * (f - 1), 0, 0)
        x = -12.0 + adv * (f - 1)
        look((x * 0.5 + 34, 62 - 6 * sm(1, N, f), 5.0), (x * 0.8 + 1.5, 0, 14.2), lens=42)
    frames_out(N, fn, (1280, 720))
    ARM.location = (0, 0, 0)


def anim_reach():
    set_action('A_Stilt_Reach')
    HUMAN.location = (9.4, 6.4, 0.0)
    HUMAN.rotation_euler = (0, 0, radians(200))

    def fn(f):
        scn.frame_set(f)
        k = sm(70, 150, f) - sm(225, 295, f)
        az = radians(34 + 14 * sm(1, 312, f))
        r = 60 - 20 * k
        look((r * cos(az) + 4, r * sin(az) + 2, 4.0 + 2.0 * k), (3.5 + 2.0 * k, 2.0 + 1.5 * k, 13.5 - 6.0 * k), lens=40 + 3 * k)
    frames_out(312, fn, (1280, 720))


def anim_head():
    set_action('A_Stilt_HeadTurn')
    HUMAN.location = (7.0, 4.4, 0.0)

    def fn(f):
        scn.frame_set(f)
        az = radians(28 + 16 * sm(1, 240, f))
        r = 19 - 3 * sm(40, 120, f)
        look((6.5 + r * cos(az), r * sin(az), 29.6), (6.4, 0, 28.3), lens=58)
    frames_out(240, fn, (1280, 720))


def anim_turntable():
    set_action(None)
    HUMAN.location = (7.0, 4.4, 0.0)
    N = 240

    def fn(f):
        a = radians(40) + 2 * pi * (f - 1) / N
        look((74 * cos(a), 74 * sin(a), 9.0), (0, 0, 14.8), lens=50)
    frames_out(N, fn, (1080, 1350))


def stage(ob):
    b = bone_of(ob)
    n = ob.name
    order = (('toe', 0), ('foot', 0.5), ('tarsus', 1), ('act_ankle', 1.6), ('shin', 2), ('act_knee', 2.6), ('thigh', 3), ('act_hip', 3.6),
             ('hip', 4), ('shoulder', 7), ('upperarm', 7.6), ('act_elbow', 8.3), ('forearm', 8.6), ('hand', 9.4), ('finger', 9.8),
             ('neck', 10.5), ('smooth', 10.9), ('head_yaw', 11.4), ('head', 11.8), ('sensor', 12.6))
    for key, s in order:
        if b.startswith(key):
            if key == 'neck':
                s += 0.12 * int(b[-1])
            if key == 'finger':
                s += 0.15 * int(b.split('_')[1][1])
            if 'Shell' in n or 'Cap' in n or 'Collar' in n:
                s += 0.35
            return s
    return {'Body_Core': 4.8, 'Body_Frame': 5.2, 'Belly_Cables': 5.6, 'Chest_Shield': 6.0, 'Body_Spine_Shell': 6.2}.get(n, 6.5)


def anim_assembly():
    """Build-up: the parts fly in feet first, shells after structure, the lights come on last. Render only."""
    set_action(None)
    em = light_off_driver()
    HUMAN.location = (7.0, 4.4, 0.0)
    st = {o.name: stage(o) for o in PARTS}
    home = {o.name: o.matrix_world.to_translation().copy() for o in PARTS}
    N, SPAN, FLY = 336, 17.0, 20.0
    t_last = max(st.values())

    def fn(f):
        for o in PARTS:
            fa = 8 + st[o.name] * SPAN + (crc32(o.name.encode('utf-8')) % 7)
            t = (f - fa) / FLY
            o.hide_render = t <= 0
            e = 1 - (1 - min(max(t, 0.0), 1.0)) ** 3
            h = home[o.name]
            out = Vector((h.x, h.y, 0))
            out = out.normalized() * 9.0 if out.length > 0.5 else Vector((0, 0, 0))
            o.delta_location = (out + Vector((0, 0, 7.0))) * (1 - e)
            o.delta_scale = (0.6 + 0.4 * e,) * 3
        on = sm(8 + (t_last + 1.2) * SPAN, 8 + (t_last + 2.2) * SPAN, f)
        em.default_value = 6.0 * on * (0.55 + 0.45 * sin(f * 1.9) if on < 1 else 1.0)
        a = radians(52) + radians(150) * sm(1, N, f)
        k = sm(1, N * 0.75, f)
        look(((58 + 14 * k) * cos(a), (58 + 14 * k) * sin(a), 3.0 + 9.0 * k), (0, 0, 4.0 + 10.8 * k), lens=46)
    frames_out(N, fn, (1080, 1350))
    for o in PARTS:
        o.hide_render = False
        o.delta_location = (0, 0, 0)
        o.delta_scale = (1, 1, 1)


ANIMS = dict(walk=anim_walk, reach=anim_reach, head=anim_head, turntable=anim_turntable, assembly=anim_assembly)
for v in list(views):
    if v in ANIMS:
        ANIMS[v]()
        views.remove(v)
if 'check' in views:
    check()
    views.remove('check')

# ---------------------------------------------------------------------------------------------- stills
S_F, S_L = 30.0 / 1010.0, 30.0 / 950.0
CZF = (1035 - 544) * S_F
CZL, CXL = (992 - 512) * S_L, (430 - 384) * S_L
if views:
    set_action(None)
    HUMAN.location = (7.0, 4.4, 0.0)
    scn.frame_set(1)
CU = dict(      # camera, target, lens: framed like refs/closeup_<name>.png
    hip=((8.5, 9.5, 18.6), (1.9, 2.0, 20.6), 50), knee=((11.0, 8.5, 13.4), (4.0, 2.1, 13.0), 60), foot=((11.0, 8.0, 1.9), (4.4, 2.6, 1.9), 48),
    hand=((9.5, 12.0, 8.6), (3.6, 4.6, 7.5), 85), head=((13.5, 8.0, 29.8), (6.6, 0, 28.5), 58), shoulder=((12.0, 8.5, 20.5), (2.4, 1.2, 23.0), 42),
    elbow=((4.5, 14.0, 17.2), (1.8, 4.0, 16.3), 110), belly=((4.0, 4.5, 11.0), (-0.2, 0.3, 21.0), 28), rear_hip=((-9.0, 9.5, 18.0), (-2.2, 2.3, 20.2), 50))
for v in views:
    if v == 'front':
        look((200, 0, CZF), (0, 0, CZF), ortho=1088 * S_F); render(v, (608, 1088))
    elif v == 'rear':
        look((-200, 0, CZF), (0, 0, CZF), ortho=1088 * S_F); render(v, (608, 1088))
    elif v == 'left':
        look((CXL, 200, CZL), (CXL, 0, CZL), ortho=1024 * S_L); render(v, (768, 1024))
    elif v == 'right':
        look((CXL, -200, CZL), (CXL, 0, CZL), ortho=1024 * S_L); render(v, (768, 1024))
    elif v == 'top':
        cam.location = (0.5, 0, 200); cam.rotation_euler = (0, 0, radians(-90))
        cam_d.type = 'ORTHO'; cam_d.ortho_scale = 26; render(v, (1024, 1024))
    elif v == '3q':
        look((52, 44, 7), (0.5, 0, 14.8), lens=50); render(v, (1050, 1400))
    elif v == '3q_rear':
        look((-52, 44, 10), (0, 0, 14.8), lens=50); render(v, (1050, 1400))
    elif v == 'cu':
        for n, (loc, tgt, lens) in CU.items():
            look(loc, tgt, lens=lens); render('cu_' + n, (1200, 1200))
    elif v.startswith('cu_') and v[3:] in CU:
        loc, tgt, lens = CU[v[3:]]
        look(loc, tgt, lens=lens); render(v, (1200, 1200))
    elif v == 'motion':       # first frames for the video model (refs/motion/*_start.png), locked-off cameras
        md = os.path.join(HERE, 'refs', 'motion')
        os.makedirs(md, exist_ok=True)

        def shot(name, res=(1280, 720)):
            scn.render.resolution_x, scn.render.resolution_y = res
            scn.render.filepath = os.path.join(md, name + '.png')
            bpy.ops.render.render(write_still=True)
        set_action(None)
        scn.frame_set(1)
        HUMAN.location = (16.0, 7.0, 0.0)
        look((7.0, 120, 11.0), (7.0, 0, 15.2), lens=52); shot('walk_side_start')
        look((66, 58, 6), (5.0, 0, 14.6), lens=40); shot('walk_3q_start')
        set_action('A_Stilt_Reach')
        scn.frame_set(1)
        HUMAN.location = (9.4, 6.4, 0.0)
        look((50, 42, 5), (3.5, 2.0, 14.0), lens=40); shot('reach_3q_start')
        set_action('A_Stilt_HeadTurn')
        scn.frame_set(1)
        look((6.5 + 19 * cos(radians(28)), 19 * sin(radians(28)), 29.6), (6.4, 0, 28.3), lens=58); shot('head_start')
        set_action(None)
    elif v == 'poses':
        for an, f in (('A_Stilt_Walk', 30), ('A_Stilt_Reach', 175), ('A_Stilt_HeadTurn', 128)):
            set_action(an)
            scn.frame_set(f)
            look((48, 46, 8), (2, 0, 13.5), lens=45); render('pose_%s_%d' % (an.split('_')[-1].lower(), f), (1280, 1280))
        set_action(None)
