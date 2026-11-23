# AnyMachine experiment 4: soft goods (backpacks)

Date: 2026-11-03. Everything runs headless in Blender 5.0. Question: does the hinge/slider/wheel/spring vocabulary
stretch to soft objects? Short answer: **partly**. Straps and buckles fit (a strap is a slider plus a chain, and a buckle is a
rigid part on a bone). Flaps, zips, fill and roll each needed a new joint type with its own solver. Soft joints are
**coupled through contact** (a lid drapes on whatever fill shape is under it), which a set of independent 0..1 params
cannot fully express.

## Outputs

| bag | demo | GLB | .blend (controls) | check |
|---|---|---|---|---|
| top-loading rucksack | `out/rucksack/rucksack_demo.{mp4,gif}` | `out/rucksack/rucksack.glb` | `out/rucksack/rucksack.blend` | `out/rucksack/check.json` |
| zip daypack | `out/daypack/daypack_demo.{mp4,gif}` | `out/daypack/daypack.glb` | `out/daypack/daypack.blend` | `out/daypack/check.json` |
| roll-top | `out/rolltop/rolltop_demo.{mp4,gif}` | `out/rolltop/rolltop.glb` | `out/rolltop/rolltop.blend` | `out/rolltop/check.json` |

Each bag folder also has:
- `stills/`: `hero_threequarter.png` plus `<control>_0.png` / `<control>_1.png` (Cycles GPU, 1280x720, 64 spp);
- `<bag>_baked.blend`: the export copy with constraints removed and all actions as NLA tracks;
- `verify_glb.json`: the GLB re-import check;
- `<bag>_build.json`: measured and derived numbers.

The demos render in EEVEE at 960x540 and 24 fps. Each one cycles through the controls, then shows a "carry bob" in which the dangling straps swing.

Rebuild: `scripts/build_<bag>.py`, then `bash run_bag.sh <bag> [still views]` (check, export, verify, stills, demo, mp4/gif).

### Controls

All controls are custom props on `<bag>_rig`, clamped 0..1. In the GLB, every control is one linear 1 s action
`<control>_param`: seek t = param. The bone channels and the morph-weight channels share one glTF animation. There is also a
`demo` action, and the joint spec is stored in the rig node's extras (`anymachine`).

| bag | built | how |
|---|---|---|
| rucksack | `fill` | Deformer bones: `fill_top` rotates the upper body about the lid-hinge axis; `fill_front` and `fill_side.L/R` translate. A `slack` fold shape key fades in below 0.6. 0.6 = the generated shape. |
| | `lid_open` | **The generated lid skin is kept** and skinned to a 5-bone chain that follows the lid's measured centre-line. 0 = closed (chain fitted to a drape path over the collar). 0.65 = the generated pose. 1 = folded back 50 deg further. The far bones lag (a floppy flap peels from the hinge) and sag mid-swing. The rebuilt lid straps lie on the body when closed (links walked down the surface) and hang under gravity when open, **draped**, so they are pushed out of the collar. |
| | `strap_length` | Rebuilt padded straps on a 9-bone chain. A cubic path is solved so that padded + webbing = target length. The webbing bone stretches, the free tail shortens by the same amount, and the ladder-lock is rigid. |
| daypack | `zip` | **Rebuilt front panel**: a ruled grid between the left and right crossings of the zip plane, sampled from the generated front with rays. The generator left the panel peeled open at the upper right, so those samples are mirrored from the left. The panel texture is baked from the generated texture through the same rays into a clean grid UV. The slider bone travels the U path (94 cm: right side up, over the top, down the left). The panel opens through 12 in-between shape keys: rotation about the bottom hinge, pinned within 15 cm of still-zipped teeth, with a gravity sag, clamped to the floor. Liner, zip tape and a swept zip track are rebuilt. The track covers the jagged edge where the cut runs through Meshy's noisy zip geometry. |
| | `pocket_fill` | Shape key on the panel: the front pocket bulges 2.2 cm. |
| | `fill`, `strap_length` | As on the rucksack (shared `straps.py`). |
| roll-top | `roll` | **Rebuilt collar**: a tube lofted from the body's cut rim, flattened to 3.2 mm over 4.5 cm, 40 cm tall, with a black stiffener edge. A 67-bone chain (6 mm segments) curls it into an Archimedean spiral with curvature 1/r(d), where r(d) = sqrt(r0^2 + t d/pi), d is measured from the tip, r0 = 12 mm (stiffener core) and the pitch is 7 mm. roll = 1 is 2.5 turns (32.6 cm rolled), and the roll travels down as it grows. The male buckles ride the roll ends on swivel tabs. The first version (r0 = 7 mm, 5.2 mm pitch, 30 cm collar) self-intersected: about 70 deg of bend per bone at the tip, and the last turn rolled up the thick taper. The check caught it. |
| | `clip` | The side webbing swings up in an arc and stretches, and the female buckles meet the males. **Dependent joint**: the pose is solved at roll = 1. |
| | `fill`, `strap_length` | As above. The collar rides `fill_top`. |

**Jiggle**: done for all three. Dangling chains are re-simulated over the demo as damped springs that lag the evaluated pose: strap tails, the rucksack's lid straps (pinned while clipped), and the daypack's zip puller. The result is baked into `demo` only and is not a param.

**Skipped**:
- `cinch` (drawstring) on the rucksack. The drawstring collar is fused generator skin, and the open lid shows it but nothing rigs it. It would need a ring-scale deformer on a rebuilt collar, the same machinery as the roll-top collar.
- Separate compression-strap tension. The generated side straps ride `fill` as painted skin.
- Strap jiggle driven by `strap_length` scrubbing outside the demo timeline.

## Check results (`scripts/check.py`)

What the check does:
- Sweeps every control 0..1 in 0.05 steps with the others at their defaults, then 5x5 grids for the coupled pairs.
- Penetration = the depth of each moving-part vertex inside the body. The inside test is a majority vote of 5 ray-parity rays: nearest-normal signs lied by up to 25 cm on these open, generated skins, so they are not used.
- Tolerance is 4 mm, because soft goods touch by design.
- Also checks: floor penetration for parts that fall open; self-intersection of the rolled collar (triangle pairs at least 4 rings apart); limit clamping at -0.3 and 1.4.

**Verdict**:
- **Roll-top passes everything.** Across 159 states there is 0 mm penetration and 0 collar self-intersections. The first coil version failed with 3.5k self-intersecting triangle pairs and was fixed: see the roll-top row above.
- **Rucksack and daypack fail only where joints are coupled or a rigid part rides a soft surface.**
- **All three:**
  - every out-of-range value is held exactly at the limit (0.0 mm deviation at -0.3 and 1.4);
  - the GLB re-import matches the baked .blend (demo median 0 mm);
  - every `<ctl>_param` action moves the rig.

**Failures above tolerance**, with the reason for each:
- **Rucksack, lid vs collar, 11.6 mm at fill 0.** The empty collar sags under a lid whose closed drape was solved for fill 0.6.
- **Rucksack, clipped male buckles, 11-15 mm at fill 1 and with the lid nearly closed.** The rigid buckle sits on a front that bulges independently of the lid strap.
- **Daypack, zip slider 7.7-14 mm.** The slider is placed on the teeth line 6 mm out, so it overlaps the zip tape by construction. This is a contact, not a bug.
- **Daypack, zip puller 29 mm at zip about 0.6.** Over the top of the bag, the puller hangs straight down into it. It needs the same drape pass the rucksack lid straps got.
- **Daypack, zip 1 with fill 0: panel 35 mm below the floor.** The open panel inherits the fill deformation of its *closed* position. This is the clearest example of a coupled joint.


### rucksack: 113 states, clamp max dev 0 mm, GLB 4330 KB, actions demo, fill_param, lid_open_param, strap_length_param, demo pose match median 0 mm

| sweep (others at default) | worst part: max penetration mm |
|---|---|
| fill | lid 11.6; strap.L 0.0; strap.R 0.0; lidstrap.L 3.6; lidstrap.R 5.3; buckle_m.L 13.7; buckle_m.R 15.3 |
| lid_open | lid 5.8; strap.L 0.0; strap.R 0.0; lidstrap.L 1.1; lidstrap.R 1.0; buckle_m.L 10.7; buckle_m.R 11.3 |
| strap_length | lid 5.8; strap.L 0.0; strap.R 0.0; lidstrap.L 0.0; lidstrap.R 0.0; buckle_m.L 1.8; buckle_m.R 3.8 |

| coupled pair (5x5) | worst |
|---|---|
| fillxlid_open | lid 11.6; lidstrap.R 5.3; buckle_m.L 13.7; buckle_m.R 15.3 |
| fillxstrap_length | lid 11.6; lidstrap.R 5.3; buckle_m.L 13.7; buckle_m.R 15.3 |

### daypack: 159 states, clamp max dev 0 mm, GLB 11052 KB, actions demo, fill_param, pocket_fill_param, strap_length_param, zip_param, demo pose match median 0 mm

| sweep (others at default) | worst part: max penetration mm |
|---|---|
| zip | panel 6.3; panel min z 2.6; zip_slider 7.7; zip_pull 29.4; zip_pull min z 10.8; strap.L 0.0; strap.R 0.0 |
| pocket_fill | panel 6.3; panel min z 12.0; zip_slider 7.7; zip_pull 0.0; zip_pull min z 10.8; strap.L 0.0; strap.R 0.0 |
| fill | panel 6.5; panel min z 12.0; zip_slider 14.4; zip_pull 1.3; zip_pull min z 10.8; strap.L 0.0; strap.R 0.0 |
| strap_length | panel 6.3; panel min z 12.0; zip_slider 7.7; zip_pull 0.0; zip_pull min z 10.8; strap.L 0.0; strap.R 0.0 |

| coupled pair (5x5) | worst |
|---|---|
| zipxfill | panel 6.5; panel min z -35.0; zip_slider 14.4 |
| zipxpocket_fill | panel 6.3; zip_slider 7.7 |
| fillxstrap_length | panel 6.5; zip_slider 14.4 |

### rolltop: 159 states, clamp max dev 0 mm, GLB 4043 KB, actions clip_param, demo, fill_param, roll_param, strap_length_param, demo pose match median 0 mm

| sweep (others at default) | worst part: max penetration mm |
|---|---|
| roll | collar 0.0; buckle_m.L 0.0; buckle_m.R 0.0; buckle_f.L 0.0; buckle_f.R 0.0; strap.L 0.0; strap.R 0.0; self:collar 0.0 |
| clip | collar 0.0; buckle_m.L 0.0; buckle_m.R 0.0; buckle_f.L 0.0; buckle_f.R 0.0; strap.L 0.0; strap.R 0.0; self:collar 0.0 |
| fill | collar 0.0; buckle_m.L 0.0; buckle_m.R 0.0; buckle_f.L 0.0; buckle_f.R 0.0; strap.L 0.0; strap.R 0.0; self:collar 0.0 |
| strap_length | collar 0.0; buckle_m.L 0.0; buckle_m.R 0.0; buckle_f.L 0.0; buckle_f.R 0.0; strap.L 0.0; strap.R 0.0; self:collar 0.0 |

| coupled pair (5x5) | worst |
|---|---|
| rollxfill | all <= 4 mm |
| rollxclip | all <= 4 mm |
| fillxstrap_length | all <= 4 mm |


## What worked / what was remade

- **Kept generator skin:** rucksack body and lid (generated open pose), daypack body (gusset, back, handle), and the roll-top body below the roll. Fabric texture and normal detail survive deformation fine.
- **Remade:**
  - all shoulder straps, webbing, tails, adjusters and buckles;
  - back panels: the generators fuse shoulder straps into the back, so I cut behind the back plane and covered the cut;
  - the daypack front panel, liner and zip;
  - the roll-top collar, roll, stiffener and clips.
- **Segmentation.** Two signals separated the parts, with no ML:
  - Welding by distance makes Tripo's UV-island soup into real components, and the straps then fall out as separate components.
  - Texture colour finds webbing and buckles: neutral black/grey versus saturated fabric.

  Meshy fused its straps to the back, so they had to be cut by plane instead.
- **Generator choice.**
  - Tripo P2 for the rucksack and the roll-top: matte fabric and a clean silhouette.
  - Meshy v7.1 for the daypack: better weave texture and a cleaner zip line.

  Meshy's rucksack and roll-top read as glossy plastic.
- **Mid-motion references paid off again.** The rucksack's half-open lid gave a lid skin and a measurable hinge line. The daypack's half-open zip located the zip plane: the puller ends sit at y = -0.083. But the generator *peeled* the panel, so the open side had to be rebuilt from its mirror. On the roll-top, the rolled reference was simply cut off and the roll synthesised, like the microwave cavity in experiment 1.

## Honest quality notes

- **Rucksack lid**: reads as fabric at mid-swing, because the tip lags and sags. Closed, it reads as a stiff cap: it is the generated domed shell bent by 5 bones, with no draping onto the collar and no wrinkles. The lid straps are flat rigid-looking planks. The male and female buckles are blocky primitives.
- **Fill**: the empty pack sags convincingly thanks to the fold shape key. Without the shape key, it is just an inflate/deflate of a smooth blob and reads as rubber. The folds are procedural sine crumples: fine at demo distance, obviously regular up close. The tan base also deforms a little where it shouldn't.
- **Daypack zip**: the slider and the progressive peel read correctly. Once fully open, the panel swings like a stiff mat with a sag: there is no buckling at the hinge and no wrinkling where it meets the floor. Some furry dark generated zip geometry still shows on the gusset outside the rebuilt track. The upper right of the panel is a mirror of the upper left (the generator had peeled it), so the panel is perfectly symmetric there. The interior is a dark liner shell, plausible but empty.
- **Roll-top**: the best of the three, and the only bag that passes every check. The spiral is geometrically right: the coil sits on the collar and travels down as it rolls. The collar is a clean procedural tube with a sampled tint and no texture, so it is visibly smoother than the generated body below it. The flattening taper leaves a crease at the seam.
- **Straps**: the shoulder straps read as webbing and pads. `strap_length` looks right from the side. Up close they are clean low-poly sweeps, cleaner than the generated skin.
- **Overall**: the moving fabric reads as fabric where the motion has *lag or contact*: the lid peel, the zip peel, the roll, and the jiggling tails. It reads as bending plastic wherever a part moves as one smooth blend without contact: closed lid, fully opened panel, fill bulge.

## What `ref-to-machine` needs for soft goods

New joint types (each still one 0..1 param, baked to one linear action plus morph weights):

```jsonc
{"type": "flap",     "chain": 5, "hinge": "auto", "rest_pose": "generated", "closed": {"drape_over": "body"},
 "range": [0, 1], "generated_at": 0.65, "tip_lag": 0.9, "sag_deg": 14}
{"type": "zip_path", "path": "auto|polyline", "panel": "remake", "hinge": "bottom", "open_deg": 98,
 "pin_radius_m": 0.15, "inbetweens": 12, "slider": "rigid", "puller": "jiggle"}
{"type": "fill",     "deformers": ["top", "front", "sides"], "rest": 0.6, "slack_folds": true}
{"type": "strap",    "anchors": ["auto", "auto"], "padded_m": 0.46, "webbing_m": [0.06, 0.2], "tail": "jiggle"}
{"type": "roll",     "collar_m": 0.4, "turns": 2.5, "r0_m": 0.012, "pitch_m": 0.007, "bone_m": 0.006}
{"type": "clip",     "male": "roll.ends", "female": "side_strap", "requires": {"roll": 1}}
{"type": "jiggle",   "chains": "auto", "k": 40, "damping": 3, "pinned_when": "clip"}
```

Schema-level additions:
1. **`requires` / coupling**: some joints are only valid in another joint's state (clip needs roll = 1). Contact couples fill with lid, panel and buckles. Two options: export 2D blend tables for the coupled pairs (fill x lid), or move the drape solve to runtime. Independent per-param actions are exact only at the other params' defaults.
2. **`remake` vocabulary for fabric**:
   - `panel_from_rays` (ruled grid + mirror + baked texture);
   - `collar_from_rim`;
   - `strap_sweep`;
   - `buckle`;
   - `liner`;
   - `back_panel`.
3. **Segmentation hints**: `weld_components`, `texture_neutral`, `cut_plane`.
4. **Validation for soft goods**:
   - penetration depth with a tolerance (not zero-overlap);
   - ray-parity inside tests;
   - floor contact;
   - self-intersection for rolled or folded parts;
   - an extra row per coupled pair.
5. **Outputs**: morph targets (in-betweens) next to bones. The GLB carries both, merged per action by NLA track name.

## Top learnings

1. **Make the deformation non-uniform and the fabric reads as fabric.** Lag along the chain, pinning near the zipped teeth, curvature from a spiral law, and drape-on-contact made the difference. A plain interpolation between two shapes looks like plastic.
2. **Soft joints are coupled through contact.** Independent 0..1 actions are exact only at the other params' defaults. The check catches this: the remaining failures are all coupled cases, e.g. fill 0 with the lid closed. The API needs `requires` and coupled tables, or a runtime drape.
3. **Remake what moves, but bake the skin into it.** The texture bake through the same rays turned a rebuilt grid into something that still looks generated. That, together with weld-then-components and texture-colour segmentation, is the reusable trick for any generated soft good.

## Spend

About $4.95, logged to `anyscene/generate/spend.jsonl`: 3 GPT Image references, 3 Tripo P2 runs and 3 Meshy v7.1 runs.

### GLB pose coverage report

The verifier compares the evaluated world-space vertex clouds at the sampled
poses. Its existing `median_mm`, `p99_mm`, and `max_mm` fields are still
imported-to-source distances. The source cloud includes only the rig's direct
mesh children in the active view layer, matching the backpack export selection
rather than including unrelated scene guides. The `reference_to_import_mm` stats
also look for source points that have no nearby imported point.
`symmetric_max_mm` is the larger directional maximum. This can detect spatially
missing pieces without assuming matching mesh names, vertex counts or order.
It is not a topology test: coincident or sufficiently nearby geometry can mask
the loss of a piece, and the verifier still samples only selected poses.

The default invocation measures and writes the JSON report without applying a
distance tolerance. For an opt-in pass/fail check, choose the tolerance for
your asset and invoke Blender directly:

```sh
blender -b --disable-autoexec --python-exit-code 1 --python backpacks/scripts/verify_glb.py -- bag.glb bag_baked.blend report.json --max-error-mm 2
blender -b --disable-autoexec --python-exit-code 1 --python backpacks/tests/test_glb_pose_distance.py
```

A failed threshold still writes the report before raising an error; comparison
uses unrounded distances. Empty or non-finite point clouds are reported as
invalid, and an import without an armature fails even when pose distances
are zero. The importer excludes Blender-generated bone display geometry.
The procedural regression uses the verifier’s import and report helpers in
separate Blender processes and checks the JSON and exit codes for an intact
GLB, one with an omitted part, and one with no armature. Checking only
imported vertices can report zero error for a missing part.
