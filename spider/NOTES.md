# AnyMachine: experiment 2, robot spider (8 legs × 3 revolute joints, walking)

Date: 2026-11-03. Everything runs headless with Blender 5.0. To rebuild from the cached generations in `gen/`, run `bash run_all.sh`; the Cycles renders go through the shared GPU queue.

## What came out

| | |
|---|---|
| Walk loop | `out/spider_walk.mp4` (1280x720, 97 frames, 24 fps, 4 gait cycles, Cycles GPU), `out/spider_walk.gif` (640 px) |
| Stills | `out/stills/threequarter_007.png`, `side_007.png`, `joint_007.png` / `joint_013.png` (close-up looking down the R2 hip-pitch and knee axes), `crouch_025.png` |
| Rig | `out/spider.blend`. The armature `spider_rig` has 34 bones: `root`, `body`, and for each of the 8 legs `coxa_*`, `femur_*`, `tibia_*` and an `ik_*` foot target. Each joint has a Limit Rotation constraint and IK locks/limits. Each tibia has an IK constraint (chain 3) whose influence is driven by the custom prop `ik_blend` (0 = baked FK, 1 = pose by dragging the `ik_*` bones). The custom props `step_length`, `step_height`, `body_height`, `speed`, `duty` plus the embedded text `spider_rebake.py` regenerate the walk. |
| GLB | `out/spider.glb` (10 MB). It carries the plain linear FK actions `walk` (one cycle, 25 keys, root motion on `root`), `idle` (3 s loop) and `crouch` (1 s, linear: seek t = crouch amount). The joint/chain/gait spec is stored in the rig's extras (`anymachine`, `anymachine_params`). There are no constraints or drivers in the GLB. |
| Check | `out/check.json` (Blender) and `out/verify_glb.json` (re-imported GLB). Numbers are below. |
| Build report | `out/spider_build.json`: every measured and design number, rest angles, local limits, the commanded range per joint. |
| Body size | I picked a **body 40 cm long**, about 20 cm wide including the hip actuators, with a standing hip height of 10 cm. The feet sit about 33 cm from the centre, so the footprint is roughly 0.66 m × 0.62 m. |

Scripts in `scripts/`:
- `shell.py`: generated GLB → normalised carapace skin, plus measurements of the generated pose.
- `spider_lib.py`: pure kinematics (layout, analytic IK, gait/idle/crouch).
- `spider_bake.py`: bakes linear FK actions.
- `build.py`: builds the parts, armature, constraints and actions.
- `check.py`, `export.py`, `verify_glb.py`.
- `render.py`, `render_all.sh`.

## Pipeline as built

1. **Reference.** GPT Image 2.5 (sunburst), three images in total. `refs/spider34_0.png` was used: a three-quarter view from above, standing, legs spread, with every joint visible.
   - **The image model drew 6 legs every time**, even though the prompt said "exactly eight legs, four per side". So did the 3D models generated from it.
   - The leg count came from the category prior, not from the image. Legs were going to be rebuilt anyway, so this cost nothing. It does mean an endpoint must **not trust the generated leg count**.
2. **Image-to-3D.** Tripo P2 (face_limit 50000) and Meshy v7.1.
   - **Picked Meshy for the body.** Its carapace is elongated, symmetric and cleanly panelled, with a sensible head.
   - Tripo's body was chunky, with leg roots and actuators fused all round the sides. Its crop left mostly black side debris.
   - Both generated 6 fused legs.
3. **Normalise and measure (`shell.py`, all automatic):**
   - **Orientation.** Forward = -Y, and the ground (the lowest foot) sits at z = 0.
     - Gotcha: on Meshy the head is at +Y raw, and I first got that wrong. A *straight-down* inspect camera has no defined "up", so the top view was ambiguous. Use a slightly tilted top camera.
   - **Body footprint.** Build a top-down occupancy grid of face centroids, then a morphological **opening** with a disc wider than a leg (about 3.7 cm at final scale) but narrower than the body. That strips the legs. Keep the largest component.
   - **Measurements of the generated pose:**
     - foot contacts (ground-level vertex clusters): 5 of 6 were found, at 0.31–0.38 m from the centre;
     - per-leg knee (highest point by azimuth sector): r ≈ 0.22–0.29 m, z ≈ 0.14–0.16 m;
     - hip radius ≈ 0.10–0.13 m;
     - generated hip height ≈ 7.8 cm (midway between the generated belly and the carapace rim).

     These set the proportions: coxa 4.5 cm, femur 13 cm, tibia 17 cm, foot reach 22.5 cm from the yaw axis. With them the rebuilt rest pose reproduces the generated knee height (16.9 cm vs 14–16 cm measured).
   - **Skin = top-visible faces only.** Faces are ray-cast from five upper-hemisphere directions. Up-facing normals could not be used: Meshy's winding is inconsistent, and a normal-z filter removed half the carapace.
     - Islands are found by union-find on *quantised vertex positions*. Meshy splits vertices at UV seams, so plain connectivity gives hundreds of fake islands. Welding destroys faces, which broke the face-index mapping.
     - Next, trim per 1 cm station to the *carapace* half-width, taken from vertices within 4 cm of the station's top. Hip-actuator stubs sit low and get dropped.
     - Clip the ragged tail (y > 15 cm).
     - **Mirror the cleaner half (+X)**, because the generator's left side was torn where the legs fused.
4. **Rebuild (`build.py`):**
   - **Chassis.** A superellipse loft under the skin, measured from the placed skin at each 1 cm station: rim height and half-width (×0.96). The belly comes from the generated footprint's low z, clamped to ≥ 5.5 cm ground clearance.
   - **Hip brackets.** Each is the upper half of a vertical yaw barrel plus a strut into the chassis wall. The yaw axis sits at chassis half-width + 6 mm + barrel radius.
   - **Legs, rebuilt completely, 24 rigid parts.** The key design choice is **side-by-side axial slabs**:
     - The coxa and tibia live on one side of each pitch axis and the femur on the other, split by a 1.5 mm gap.
     - Each joint is two **coaxial half-barrels of equal radius**: the parent half on one side of the gap, the child half on the other.
     - A rotation about the axis maps each slab onto itself, so **adjacent segments cannot intersect at any angle, by construction.** The hip-yaw joint is the same idea, stacked vertically: the coxa's lower half-barrel sits below the body's upper half.
     - This is the exact multi-joint generalisation of the laptop's coaxial lid barrel.
     - It also matches the reference art (offset knuckle joints with end caps).
   - **Leg layout** (fallback design, symmetric):
     - hips at y = -10.5, -3.5, +3.5, +10.5 cm;
     - rest directions 52°, 17°, -17° and -50° forward of lateral. The generated 6-leg spider had about ±50° and 0°, so I spread them for 8.
5. **Rig:**
   - Bones sit on the true joint axes, with local X exactly = the pitch axis and the coxa's local Z = world Z (axis error 2e-7).
   - Parts are bone-parented with mesh data in the bone-tail frame and identity transforms, so the glTF node tree is clean.
   - Limits are set per leg in local space:

     | Joint | Limit | Basis |
     |---|---|---|
     | Hip yaw | ±22° | Derived from the collision sweep: first contact at 27.5° (the leg-2 femur against the leg-1 coxa), 0.13 mm at 25° |
     | Femur | -35..80° absolute elevation | Design |
     | Knee | -165..-25° relative to the femur | Design |
6. **Motion (`spider_lib.py` + `spider_bake.py`):**
   - **Analytic IK.** It handles the foot's lateral offset (the tibia slab sits about 1.1 cm off the coxa plane): yaw = atan2(target) - atan2(-c, ρ), then a 2-link planar knee-up solution.
   - **Walk.** An **alternating tetrapod**: A = {L1, R2, L3, R4} and B = {L2, L4, R1, R3}, with a half-cycle phase offset.
     - Duty 0.6, so all 8 feet are down at each hand-over (two windows per cycle).
     - Footholds are planned in world space (mid-stance body position + neutral foot), so stance feet are fixed in the world exactly.
     - Swing uses cycloidal horizontal interpolation (zero velocity at lift-off and touch-down) and a (1 - cos) lift to `step_height`.
     - The body moves at constant speed, with a 3 mm bob twice per cycle (high at each tetrapod's mid-stance).
     - Defaults: stride 12 cm per cycle, step height 3.5 cm, hip height 10 cm, speed 0.12 m/s, so the period is 1.0 s = 24 frames.
   - **Idle.** A 3 s loop of body sway: ±6 mm, ±3° yaw, ±1.5° roll. The feet stay planted.
   - **Crouch.** The body drops 4.5 cm with the feet planted.
   - Everything is keyed every frame as linear FK channels, plus the `ik_*` target locations.

## Check results (`out/check.json`, `out/verify_glb.json`)

The half-frame walk and IK-only probes measure foot motion. Their geometry fields are
`null` because those probes skip collision and clearance checks. The summary takes
geometry measurements from the full-motion and joint-sweep checks.

| Check | Result |
|---|---|
| Joint sweeps: all 24 joints through their full limit range in 2.5° steps (984 poses), against all 26 parts | **0 triangle overlaps.** Min non-adjacent clearance 2.81 mm. Coaxial half-barrel gap 1.50 mm everywhere. |
| Limit clamping (each joint commanded 20° past each limit) | Clamps exactly (0.000° error) |
| Angle tracking (evaluated bone angle vs command), sweeps and all motions | 0.000° error |
| Motions: `walk_demo` (4 cycles, 97 frames), `walk`, `idle`, `crouch`, every frame | **0 overlaps.** Min non-adjacent clearance 7.6 mm (chassis vs the femur of leg 2). Lowest non-foot part 21.8 mm above ground (at full crouch). All commanded angles are inside the limits, and no IK target is out of reach. |
| **Foot slip during stance**, Blender, at the keyed frames (40 stance runs) | **0.0003 mm** |
| Foot slip at half-frames (what linear key interpolation produces between keys) | 0.75 mm max; feet dip at most 0.7 mm into the ground between keys |
| Foot position vs commanded target | 0.048 mm (a constant float offset) |
| IK mode (`ik_blend` = 1, leg bones zeroed to rest every frame, Blender's IK solver drives from the `ik_*` targets) | Foot error 0.048 mm and slip 0.0002 mm. The IK constraint reproduces the walk from foot targets alone. |
| **GLB re-import**: 34 bones, actions `walk` / `idle` / `crouch`, extras intact | Rest foot error 0.048 mm. Walk sampled at half frames: **slip 0.021 mm**, target error 1.09 mm (swing feet between keys). Idle and crouch slip ≤ 0.001 mm. |

## What worked

- **Rebuilding the legs as axial-slab parts with coaxial half-barrels is the result of this experiment.** With 24 joints and 26 parts there were 0 overlaps across about 1,200 checked poses, and nothing had to be tuned to get there. The only collisions the sweep ever found were *between neighbouring legs* (leg-2 femur against leg-1 coxa at a yaw of 27.5° or more). That turned the yaw limit into a measured number, not a guess.
- **World-space foothold planning plus analytic IK makes stance slip exactly zero at the keys.** The residue is only key interpolation: 0.75 mm in Blender's euler interpolation and 0.02 mm in the GLB.
- **Measuring proportions from a mid-stance generated mesh works, even with the wrong leg count.** Feet, knees and the hip radius came from simple clustering, and the rebuilt rest pose lands on the generated knee height.
- **Keeping the generator's carapace as a skin and lofting a chassis under it** works, as in experiment 1: the generated surface detail and texture are kept, and I own the topology underneath.
- The rig carries the same plain FK actions as the GLB, so web and game engines need no solver. The `ik_*` bones still export, so an engine can run its own runtime foot IK on them.

## What had to be remade (and why)

| Part | Problem in the generation | Fix |
|---|---|---|
| Leg count | 6 legs in the image and in both meshes, despite the prompt | Category prior (8) |
| All leg segments | Fused into each other and into the body; no separable segments | 24 parametric parts (chamfered tapered beams, half-barrels, end caps, a rubber ball foot) |
| Body sides and belly | Hip actuators and leg roots fused into the side walls; Meshy's normals were inconsistent | Kept the top-visible carapace only; lofted a chassis |
| Carapace left half and tail | Torn where legs fused; ragged tail | Mirrored the cleaner half; clipped the tail at y = 15 cm |
| Hip mounts | Generated actuators fused into the shell | 8 brackets with vertical yaw half-barrels |
| Materials | Generator metallic/roughness maps (same issue as experiment 1) | Unlinked: metallic 0, roughness 0.45 on the skin |

## Honest quality notes

- **Gait: believable as a machine.** The two tetrapods hand over cleanly, the feet visibly plant, and the body glides with only a small bob. It reads as a careful robot, not an animal.
  - There is no body roll or pitch, no per-leg phase lag inside a tetrapod, and no turning. All four feet in a group lift on the same frame, which is slightly metronomic.
  - The 0.12 m/s pace is slow. The 3.5 cm step height clears flat ground only.
- **Feet do not slide.** That is verified numerically above, and the grid floor in the MP4 makes it visible.
- **Nothing clips at the rig level** (0 overlaps). **The generator skin is the weak part:**
  - The front of the carapace (the head) has torn white fragments at its edge.
  - The mirror seam down the centre is faintly visible in close shots.
  - The skin texture shows some grey blotches.
  - It reads fine at walk-loop distance but looks scrappy in the three-quarter still.
- **The legs are clean but plain.** They are white chamfered beams with a dark inlay strip, with no fasteners, cables or panel breaks. The hip yaw barrels look like a row of stacked cans from the front-left.
- The side still is ortho with 13° of elevation. The checker floor reads as stripes there. It is useful for leg geometry, but it is not a beauty shot.
- The joint limits for femur and knee are design values. They are verified collision-free by the sweep, but not derived from it. Only yaw is a measured limit.

## How `ref-to-machine` should grow for multi-limb machines

Experiment 1's schema had a flat `joints[]`. For walkers, the unit is a **chain** with an end effector, chains come in **mirrored/repeated sets**, and motion is a **gait**, not a per-joint param. Proposed additions (backwards compatible: a laptop is one chain with one joint and no gait):

```jsonc
{
  "category": "robot_spider",
  "real_size_m": {"body_length": 0.40},
  "topology": {                                   // replaces counting legs in the generated mesh (it was wrong: 6 vs 8)
    "root_part": "chassis",
    "chain_sets": [{
      "name": "leg", "count": 8, "symmetry": "bilateral",      // L1..L4 / R1..R4, mirrored
      "mount": {"along": "body_length", "spread_m": [-0.105, 0.105], "rest_dir_deg": [52, 17, -17, -50]},
      "joints": [
        {"name": "coxa",  "type": "hinge", "axis": "vertical",   "limits_deg": "auto",       "length_m": "measure"},
        {"name": "femur", "type": "hinge", "axis": "chain_plane_normal", "limits_deg": [-35, 80], "limit_frame": "absolute_elevation", "length_m": "measure"},
        {"name": "tibia", "type": "hinge", "axis": "chain_plane_normal", "limits_deg": [-165, -25], "limit_frame": "relative_parent", "length_m": "measure"}
      ],
      "end_effector": {"type": "ball_foot", "radius_m": 0.013, "contact": "ground"},
      "joint_style": "axial_slab"                 // coaxial half-barrels in alternating slabs: clip-free by construction
    }]
  },
  "limits_policy": "design_then_sweep",           // "auto" limits = largest collision-free range from the sweep minus a margin
  "gaits": [
    {"name": "walk", "pattern": "alternating_tetrapod",       // tripod | tetrapod | wave | ripple | trot | custom phases[]
     "phases": {"A": ["L1", "R2", "L3", "R4"], "B": ["L2", "R1", "L4", "R3"]}, "phase_offsets": {"A": 0, "B": 0.5},
     "duty": 0.6, "step_length_m": 0.12, "step_height_m": 0.035, "body_height_m": 0.10, "speed_mps": 0.12,
     "body": {"bob_m": 0.003, "roll_deg": 0, "pitch_deg": 0}, "swing_profile": "cycloid", "root_motion": true}
  ],
  "poses": [{"name": "idle", "type": "loop", "seconds": 3}, {"name": "crouch", "type": "param", "drop_m": 0.045}],
  "ik": {"solver": "analytic", "export_targets": true, "blend_ik_constraint": true},
  "outputs": ["glb", "blend", "preview_mp4"]
}
```

The response gains:
- `chains[]`: joints, bones, local axes, limits, end effector and IK target bone;
- `gaits[]`: frames per cycle, the action name, root motion, and which chains are in stance per phase;
- `validation` per motion:
  - `max_foot_slip_mm` at keys and at half-keys;
  - `min_clearance_mm`, split into adjacent gap and non-adjacent;
  - `overlaps`;
  - `min_ground_clearance_mm`;
  - `unreachable_targets`;
  - `ik_mode_foot_err_mm`;
  - sweep results per joint, including the *measured* collision-free limit.

The engine-facing contract stays the same as in experiment 1: **plain linear FK actions + a JSON spec in extras**. No drivers or solvers are required.

## Top learnings

1. **Never trust the generated topology for counted parts (legs, wheels, fingers).** Two image calls and two 3D generators all said 6. Counts and chain structure must come from the category prior or the request. The mesh supplies proportions, skin and body shape.
2. **"Adjacent parts in alternating axial slabs around coaxial half-barrels" is the multi-joint version of the experiment-1 barrel trick.** It makes every parent/child pair clip-free by construction. The collision sweep is left with the only real failure mode, *neighbouring chains*, and it converts that into measured limits.
3. **Plan feet in world space and solve IK analytically; bake per-frame linear FK.** Stance slip is then zero by construction. The only measurable error is key interpolation (0.75 mm Blender, 0.02 mm GLB), so the check should sample half-frames, not just keys.

## Spend

About $2.15, all logged to `anyscene/generate/spend.jsonl`:
- 3 GPT Image calls (1 + 2);
- Tripo P2 ×1;
- Meshy ×1.

Renders are about 3 min of GPU time through `gpu_run.sh`.
