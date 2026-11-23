# AnyMachine experiment 5: Stilt, a 30 m walker built from references

**In this repo:** the scripts, the references, `stilt.blend`, `stilt.glb`, the comparison stills (as JPG) and four
videos (`stilt_showcase`, `stilt_assembly`, `stilt_walk`, `stilt_reference_to_model`). Left out for size: `stilt.fbx`,
the 4K `textures/` (the build bakes them again in about 80 s, so do not pass `--reuse-bake` on a first run), the
other videos and the motion-reference clips in `refs/motion/` (their start frames and prompts are here). The method
this build follows is written up in [`../PIPELINE.md`](../PIPELINE.md).

Design C, the 30 m four-legged, two-armed strider. Built by script from the reference views and close-up plates in
`refs/`. Every joint is a real mechanism: a fork and tongue on a pin, a motor drum with a bolted flange and a ceramic
cap, a grooved cable drum that the leg tendons run tangent to, and a working two-part hydraulic actuator across each
hip, knee, ankle and elbow.

| File | What |
|---|---|
| `build_stilt.py` | The whole build: solver, geometry, materials, UVs, texture bake, rig, three actions, export. Re-run to rebuild everything. |
| `render_stilt.py` | Check renders, close-ups, the clash check and the video frames. |
| `verify_glb.py` | Re-imports `stilt.glb` and `stilt.fbx` into empty scenes, reports what is in them and renders the GLB. |
| `stilt.blend` | Result. Collections: `Stilt` (160 parts + `Armature`), `Studio` (lights, floor, camera, `Scale_Human`). Actions `A_Stilt_Walk`, `A_Stilt_Reach`, `A_Stilt_HeadTurn`. |
| `stilt.glb` | Skinned, textures embedded (JPEG), the three animations. Metres. |
| `stilt.fbx` | **Skeletal mesh for UE** with the three animations as takes. Centimetres, no scale on the armature. References the PNGs in `textures/`. |
| `textures/` | `stilt_ceramic_*` and `stilt_frame_*`: base colour (with baked ambient occlusion), ORM, normal. 4096 px PNG. |
| `stilt_info.json` | Machine-readable parts, bones, rest axes, actuator anchors and strokes, written by the build. |
| `stilt_anchors.json` | The frozen actuator anchor points and cylinder / rod lengths (see "Actuators"). |
| `PARTS.md` | The parts breakdown written before modeling. |
| `refs/` | Concept and crops, turnaround, five single views, 28 close-up plates (seven areas, four angles each), `motion/` (video-model motion reference). `jobs_*.json` + `edit.ps1` / `video.ps1` regenerate them. |
| `renders/` | Videos (below), `stilt_front / left / rear / top / 3q / 3q_rear`, `stilt_cu_*` (the model framed like each close-up plate), `stilt_compare_*` (reference beside model), `stilt_glb_*` (from the re-imported GLB). |

```
"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --background --python build_stilt.py -- [--reuse-bake] [--no-bake] [--no-export] [--search-anchors] [--tex 4096]
"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --background stilt.blend --python render_stilt.py -- [front left rear top 3q 3q_rear cu poses check]
"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --background stilt.blend --python render_stilt.py -- walk --frames <folder>      (also: reach head turntable assembly)
"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --background --python verify_glb.py -- [still] [turn] [fbx]
```

`--reuse-bake` skips the bake and loads `textures/` together with the UV layout that was baked
(`textures/stilt_uv_atlas.npz`; the bake itself takes about 80 s). It is only valid while the geometry is unchanged,
and the build stops if the topology no longer matches. Animation edits do not change geometry as long as `stilt_anchors.json` is kept; `--search-anchors` re-picks
the actuator anchors from the animations, which moves lugs and shell slots and needs a fresh bake.

## Videos (`renders/`)

| | |
|---|---|
| `stilt_assembly.mp4` | Build-up: the parts arrive feet first, structure before shells, the sensor lights come on last. |
| `stilt_walk.mp4` | Three cycles of the walk past a 1.75 m figure. `stilt_walk_v1.mp4` is the first version, one foot at a time. |
| `stilt_reach.mp4` | Lowers itself, reaches the left hand to the ground beside the figure, opens and closes the hand, stands. |
| `stilt_head.mp4` | Head lifts, lights flicker on, looks left, right, settles. |
| `stilt_turntable.mp4` | Rest pose, full orbit, with the figure at the front-left foot. |
| `stilt_glb_turntable.mp4` | The same from the re-imported GLB only (what a plain GLB viewer shows). |
| `stilt_showcase.mp4` | Assembly, walk, reach and head cut together (1280 x 720). |

## Dimensions

Blender units are metres. +X forward, +Y left, +Z up, origin on the ground under the body.

| | |
|---|---|
| Height | 29.98 m to the antenna tips, 29.4 m to the top of the head shell |
| Footprint | feet at X +5.0 / -5.4, front feet 5.0 m apart, rear feet 9.2 m apart; 16.9 x 12.5 m over everything |
| Body | hull X -4.2..+4.0, 2.6 m wide; 10.8 m over the wing shells |
| Hip drums | front (1.6, +/-1.9, 21.3), rear (-2.0, +/-2.2, 20.9); abduction pins 1.35 m above them |
| Leg segments | thigh 8.55, shin 7.55, tarsus 5.05 m; foot ball 0.60 m above the ground |
| Joint drums | hip dia 1.9, knee 1.5, ankle 1.0, shoulder 1.4, elbow 1.0, wrist 0.72 m |
| Arm | upper arm 7.0, forearm 6.8, palm 1.25, fingers 3.6 m (1.5 + 1.2 + 0.9; the thumb 1.3 + 1.1 + 0.9) |
| Triangles | about 352k in 160 parts (155k unique: the four legs, two arms and the wings are copies), no LODs yet |

## Skeleton

104 bones. Body, neck and head bones are world-aligned at rest (X forward, Y left, Z up). Limb bones are
**segment-aligned**: local Z runs up the segment to its upper joint, local Y is the hinge pin, local X is the
segment's front. A positive rotation about local Y is the same fold on every leg. The rear legs are the front legs
turned half a turn about Z, so their local X points backward and they fold knee-backward. Exact rest axes of every
bone are in `stilt_info.json`.

| Bone | Parent | Joint as modeled | Axis |
|---|---|---|---|
| `root` | - | ground, under the body | |
| `pelvis` | root | body and everything fixed to it, at (0, 0, 21.1) | free |
| `hip_FL/FR/RL/RR` | pelvis | abduction block on a fore-aft pin between two body lugs | X |
| `thigh_*` | hip | hip drum: thigh tongue between the yoke cheeks | Y |
| `shin_*` | thigh | knee: thigh fork, shin tongue, pin | Y |
| `tarsus_*` | shin | ankle: shin fork, tarsus tongue, pin | Y |
| `foot_*` | tarsus | steel ball in the foot socket | free; the actions keep it level |
| `toe_a/b/c_*` | foot | pin hinge between two lugs; a and b point away from the body, c toward it | Y |
| `act_hip/knee/ankle_top_*`, `_bot_*` | upper / lower segment | actuator halves on their lug pins | local Z runs along the actuator |
| `shoulder_L/R` | pelvis | abduction block, as the hip | X |
| `upperarm_*`, `forearm_*` | chain | shoulder drum, elbow | Y |
| `hand_*` | forearm | wrist pitch hinge inside a roll ring | Y pitch, Z roll |
| `finger_a1..a3`, `b1..b3`, `c1..c3` | hand, then chain | pin hinges; a and b side by side, c opposes them | Y, positive curls |
| `act_elbow_top/bot_*` | upperarm / forearm | actuator halves | |
| `neck_01..05` | pelvis, then chain | pin joints of the five neck links | Y pitch, Z yaw |
| `head_yaw` | neck_05 | bolted bearing ring | Z |
| `head` | head_yaw | yoke pin | Y |
| `sensor` | head | socket for a light component; carries `Light_Sensors` | none |
| `ik_foot_root`, `ik_foot_*`, `ik_hand_root`, `ik_hand_L/R` | root | no meshes; they follow the feet and hands in every action | |

Every part is skinned 100% to one bone and its origin sits on that bone. The one exception is `Neck_Bundle` (the cable
bundle under the neck), smooth-skinned across `neck_01..05`. No mesh shares a name with a bone (the build asserts it).

**How the legs are solved.** The plane of a leg always contains the body's fore-aft axis through the hip pin and the
foot, so `hip` only ever turns about X. In that plane the three segments zigzag: the knee sits ahead of the hip-to-foot
line and the ankle behind it by 0.6 of that. The arm is the same with two segments. `solve()` in the build script
is the reference if you rebuild this as Control Rig or an Anim Blueprint.

## Actuators

Hip, knee, ankle and elbow each carry a hydraulic cylinder (on the upper bone) and a rod (on the lower bone), aimed at
each other. The build samples every action, then picks anchor points where one cylinder and rod telescope over the
whole stroke on all four legs with the largest lever arm, and fails if a rod could leave its cylinder. The numbers
it chose are in `stilt_anchors.json` and `stilt_info.json`. In UE use a Look At pair per actuator, or just play the
baked actions, which already carry the aimed bones.

## Actions (24 fps, keys every second frame, baked on export)

| Action | Frames | What |
|---|---|---|
| `A_Stilt_Walk` | 1 to 133 (132-frame loop, 5.5 s) | In place. A natural four-beat walk in lateral sequence, timed like a giraffe's: rear-left, then front-left 0.14 of a cycle later, then the right pair half a cycle on. Each foot is in the air for 0.34 of the cycle, so the swings overlap and two or three feet carry the body. Stride 6.0 m, foot lifted 1.9 m with a high knee. Body 0.8 m lower than at rest, swaying 0.95 m toward the supporting side and rolling 2.2 deg; the neck rocks with each side's step and the head stays level; each arm swings against its own side's front leg. Ground speed that keeps the planted feet still: 9.09 m per cycle (`stride / (1 - swing)`; the numbers are under `walk` in `stilt_info.json`). |
| `A_Stilt_Reach` | 1 to 312 (13 s) | Feet planted. The body drops 4.6 m and tips 22 deg nose-down (front legs fold, rear legs stay tall), the left arm reaches to the ground at (7.0, 4.6), the hand opens, closes, and it stands again. |
| `A_Stilt_HeadTurn` | 1 to 240 (10 s) | Starts drooped with the lights off; lifts, lights flicker on at frame 60, looks 52 deg left, 40 deg right, returns. |

The custom property `sensor_light` on the armature (0 = off, 1 = calm) is keyed in every action and drives the emissive
material in Blender. It is not exported; drive `M_Stilt_Emit_Sensor` in UE yourself.

**Motion reference.** The walk and reach were retimed against clips made with fal's H3 Max image-to-video model from
renders of this model (`refs/motion/`, `jobs_motion.json`, `video.ps1`). Taken from the clips: the high heron-style knee
lift, quick lift and slow set-down, the body dipping as a foot lands and nodding while a front foot is in the air; for
the reach, the long slow lowering led by the front legs with the rear legs tall, the arm unfolding late and the hand
holding open. The first walk moved one foot at a time; it was replaced with the overlapping gait above, whose cycle
length and high-knee, low-foot swing come from a second pair of clips prompted for a giraffe's walk (`refs/motion/walk2_*.mp4`,
`jobs_motion_walk2.json`). This was done by reading frame strips of the clips, not by tracking them. The head clip drifted off the
design and only its timing was used.

`render_stilt.py -- check` compares every part against every part on another bone through all three actions and
reports intersections that are not there in the rest pose. The current build reports none.

## Materials and UVs

Exported: `M_Stilt_Ceramic` and `M_Stilt_Frame` (both textured from the bake) and `M_Stilt_Emit_Sensor` (blue emissive,
linear 0.01, 0.10, 1.0, strength 6) on its own object `Light_Sensors`. The frame texture set holds what were five
procedural materials before the bake: black carbon, graphite metal, polished steel, braided cable and rubber.
`--no-bake` keeps those five as separate procedural slots.

- `UV_Atlas` (channel 0): two packed sets, ceramic and frame. Copies share islands (four legs, two arms, left and
  right wings), so 921 m2 of unique surface fills the two 4096 px maps instead of about 2,200 m2.
- `UV_Tile` (channel 1): box projection at 1 UV unit = 1 m, for tiling materials in UE.

Hard edges carry a 6 to 20 mm chamfer and all parts have weighted custom normals.

## Import into UE 5.9

1. Import `stilt.fbx` as a **Skeletal Mesh** with animations (Import Mesh, Import Animations, Combine Meshes on, normals:
   Import Normals, tangents: MikkTSpace). The file is in centimetres with scale applied, so it should arrive about
   1687 x 1247 x 2998 cm, head along +X, `root` as the root bone with scale 1. UE mirrors Y, so the walker's left is -Y.
2. Materials: plug `stilt_<set>_basecolor`, `_orm` (R occlusion, G roughness, B metallic, set to linear / Masks) and
   `_normal` into `M_Stilt_Ceramic` and `M_Stilt_Frame`. The FBX only references base colour and normal.
3. Put a blue light component on the `sensor` socket and drive the emissive strength for expression.
4. Physics Asset: delete the auto bodies; capsules on `thigh`, `shin`, `tarsus`, `upperarm`, `forearm`, a box on
   `pelvis` (about 9 x 11 x 5 m with the wings) and on `head`, spheres on the feet. None on actuator, toe, finger or
   socket bones.

## What differs from the references

- **Shells are panels on a visible frame**, not the continuous smooth skin of the turnaround. Each limb segment is a
  lattice mast with a ceramic channel over its front and sides, split into panels, with a slot where an actuator lug
  comes through. From the back the legs are mostly dark structure, tendons and actuators.
- **Legs stand in a visible zigzag** (knee about 1 m ahead of the hip-to-foot line), where the views draw them almost
  straight.
- **Arms follow the concept's length**, not the shorter turnaround arms: fingertips hang about 5 m above the ground.
- **Three fingers and three toes**, as the design says; the hand and foot close-up plates drew four.
- **Six limbs.** The left view fused the arm into the front leg; the arms have their own shoulder drums above and
  outside the front hips.
- **Body.** One dark hull with ribs, a three-plate dorsal shell, a two-piece chest shield and three overlapping wing
  plates per side. The references have more layered plates, a notch in the chest shield around the neck base, and
  looms of cable through the frame. The belly has five hanging cable loops.
- **Neck** is five lattice links with a ceramic dorsal plate each and a five-cable bundle underneath; the plate shows
  pistons between the vertebrae, which are left out.
- **Head.** Sensor cluster of seven lights in a bay on each side plus three on the nose. Three antenna blades per side
  with one whisker each. The head close-up's panel lines are reduced to a centre seam, one cross seam and a vent.
- **Joint caps** are round domes with a ring, bolts and a groove; the knee plate shows a larger leaf-shaped shield.
- **Hands, elbows and feet are plainer than their plates.** The hand has a simple palm block and bar fingers with
  ceramic backs, without the sculpted knuckle housing and looms; the elbow has no knuckle casting around the drum; the
  foot follows the small foot of the turnaround, not the person-high ankle housing of the foot plate. `renders/stilt_compare_cu_*.png`
  put each plate beside the model.
- **Clean.** No moss, dirt, damage or decals: the dead one among the pylons is a material and set-dressing pass.
- **Texel density is low for close shots** (a 30 m machine on two 4K maps). The bake carries tone, streaks and
  ambient occlusion; for close-ups in UE use tiling detail on `UV_Tile`.

## Headless GLB motion verification

`verify_glb_motion.py` loads the source rig and reimports the exported GLB into
an empty scene using the source frame rate. It checks the imported clip names,
baked frame ranges, bone names, and evaluated motion at every expected baked
key, including the first and last, across all bones. Stilt
exports every other frame, so an even source end frame is not expected to be
present. The comparison uses world-space joint positions and deformation
relative to the bind pose. Its thresholds are 2 mm for position differences
and 0.0002 for individual linear transform elements. The JSON summary is
printed on a single line; Blender's `--python-exit-code 1` makes failures
machine-detectable. This is a sampled rig-motion check, not continuous
validation of interpolation, materials or skin weights.

From the repository root, run the procedural regression tests with:

```sh
blender --background --disable-autoexec --python-exit-code 1 --python stilt/tests/test_verify_glb_motion.py
```
