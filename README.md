# AnyMachine: machines that work, built in Blender by an agent

Part of a family: [AnyScene](https://github.com/apekshik/anyscene) builds whole sets,
[AnyKit](https://github.com/apekshik/anykit) builds the props that go in them, AnyMachine makes machines that move, and
[AnyShot](https://github.com/apekshik/anyshot) shoots the result.

![Stilt walking past a 1.75 m figure](stilt/renders/stilt_walk.gif)

**Stilt**: a 30 m walker with 160 parts, working hydraulics on every joint, a 104-bone rig and three animations. It
started as one painting. Every part of it is built by [one Python script](stilt/build_stilt.py) that runs in Blender.
The work was done by an agent (Claude Fable 5.2 in Claude Code) following the steps in [PIPELINE.md](PIPELINE.md),
with a person choosing the design and approving each stage.

| Reference | Built |
|---|---|
| ![](stilt/refs/concept_sheet.png) | ![](stilt/renders/stilt_compare_3q.jpg) |
| ![](stilt/refs/closeup_knee.png) | ![](stilt/renders/stilt_cu_knee.jpg) |

Video: [`stilt/renders/stilt_reference_to_model.mp4`](stilt/renders/stilt_reference_to_model.mp4) (the build, then
the references beside what was built). Model: [`stilt/stilt.glb`](stilt/stilt.glb).

## New: complicated objects, modelled part by part

| Reference sheet | Built (clay above, baked below) |
|---|---|
| ![](hardsurface/rig2_blender/kit/aircraft/helicopter/sheets/heli_turn.jpg) | ![](hardsurface/previews/helicopter/overview_clay_top_textured_bottom.jpg) |
| ![](hardsurface/rig2_blender/kit/sheets/survival_craft_turn.jpg) | ![](hardsurface/previews/lifeboat/after_bow.jpg) |

The same agent (Claude Fable 5.2 in Claude Code) now builds objects with far more on them: a helicopter with a full
rotor head, cabin and cockpit (31,477 triangles, three texture sets), an enclosed lifeboat on its davit and winch,
twelve pieces of oil-rig equipment, nineteen light fixtures, three rifles. The method: generate detailed reference
sheets first (the whole object from six sides, then sheets of close-ups), model it in Blender Python one real part
at a time, render it beside the sheets, do a second pass where it came out plainer, bake the textures on a GPU
render farm, export game-ready. Image-to-3D meshes are not used for these; the lifeboat replaced one.

They are still simpler and flatter than their sheets in places, and the notes say where.
[PIPELINE.md, part 2](PIPELINE.md#part-2-complicated-static-objects) is the method;
[`hardsurface/`](hardsurface/NOTES.md) has the scripts, sheets and comparisons.

## Three ways in

**From reference sheets, for static objects with a lot on them.** Above, and
[PIPELINE.md, part 2](PIPELINE.md#part-2-complicated-static-objects).

**From references, for machines no generator can give you.** One concept image becomes a turnaround, single views
and a close-up plate for every mechanism. A parts breakdown is written from those, then a script that builds the
geometry, materials, rig and animations, and check renders that put each reference beside the model.
[PIPELINE.md](PIPELINE.md) is the method; [`stilt/`](stilt/NOTES.md) is the worked example.

**From a generated mesh, for everyday objects.** Give it an object (a reference image, or a static mesh from a kit)
and it hands back a rig that works: a laptop lid on a real hinge, legs that walk without sliding, a bag that fills
and opens. Every control is a 0-1 parameter, and every result is checked by machine before anyone looks at it.

1. **Generate** the object in an articulated pose (Meshy and Tripo, both tried).
2. **Treat the mesh as a skin.** Measure the joint axes off it, then rebuild the moving parts as clean geometry on
   those axes: coaxial hinge barrels, side-by-side joint slabs, so nothing can pass through anything.
3. **Expose parameters.** Each joint gets a 0-1 custom property with drivers and limits, and bakes to linear glTF
   actions, so `seek(t = value)` poses the GLB in any engine.
4. **Check.** Sweep every parameter for triangle overlaps, clamp out-of-range values, measure foot slip, then
   re-import the GLB to confirm it matches.

**Status: experiments.** This repo holds the six runs so far; there is no endpoint yet.

## Experiments

| | Joints | Result |
|---|---|---|
| [hardsurface](hardsurface/NOTES.md) | none: static props. Lifeboat station, helicopter, 12 equipment pieces, 19 light fixtures, 3 rifles | Works as game props. From reference sheets, no generated mesh. Simpler and flatter than the sheets in places; the helicopter is not yet tested in the game |
| [stilt](stilt/NOTES.md) | 4 legs x 3 joints, 2 arms, hands, 5-link neck; 14 hydraulic actuators; walk, reach, head turn | Works. From references, no generated mesh. No intersections through all three actions; plainer than its plates in the hands, elbows and feet |
| [laptop](laptop/NOTES.md) | one lid hinge, 0-135 deg | Works. 0 overlaps over the full sweep, min clearance 0.32 mm |
| [quadruped](quadruped/NOTES.md) | 4 legs x 3 joints; trot, idle, sit, stand | Works. 0 overlaps, 0.014 mm foot slip; legs are plain slabs |
| [spider](spider/NOTES.md) | 8 legs x 3 joints; walk, idle, crouch | Works. 0 overlaps; generators gave 6 legs, the 8 come from the brief; body skin is rough |
| [backpacks](backpacks/NOTES.md) | roll, clip, fill, flap, zip, straps | Partly. The roll-top passes every check; the rucksack and daypack fail where controls interact |

What the backpacks showed: hinges, sliders and wheels cover hard-surface objects, but soft goods need their own joint
types (`flap`, `zip_path`, `fill`, `strap`, `roll`, `clip`, `jiggle`) and a way to say which controls depend on each
other. The notes in `backpacks/` draft them.

## Running

**Stilt** (Blender 5.2). The build needs nothing but the script:

```
blender --background --python stilt/build_stilt.py
blender --background stilt/stilt.blend --python stilt/render_stilt.py -- 3q cu check
blender --background --python stilt/verify_glb.py
blender --background --disable-autoexec --python-exit-code 1 --python stilt/verify_glb_motion.py
```

The first line rebuilds `stilt.blend` and `stilt.glb` from nothing, including the texture bake (about 80 s; add
`--no-bake` to skip it). `stilt/edit.ps1` and `stilt/video.ps1` regenerate the references from the `jobs_*.json`
prompt files and need `FAL_KEY`.

For a quick Stilt clash preview, use the `check` view (every sixth frame).
For a strict check with a JSON summary line and a nonzero exit on unexpected overlaps:

```bash
blender --background stilt/stilt.blend --python-exit-code 1 --python stilt/render_stilt.py -- check-strict
```

Strict mode checks every integer frame, including the last; it uses the same
rest-pose overlap heuristic and same-group exclusions as the fast check.
It does not detect collisions between frames.

**Hard-surface objects** (Blender 5.2). Each object is one script; `--nobake` builds the geometry in seconds:

```
cd hardsurface/rig2_blender/kit
blender -b --factory-startup --python aircraft/helicopter/build.py -- --nobake
blender -b --factory-startup --python equipment/xmas_tree/build.py -- --size 512 --spp 4 --noreview
```

See [`hardsurface/NOTES.md`](hardsurface/NOTES.md) for what is and is not in the repo.

**The others** (Blender 5.0). Each folder has a `run_all.sh` (`run_bag.sh` for the backpacks) that rebuilds
everything from the cached generations in its `gen/` folder, headless. Generations, `.blend` files, GLBs and render
frames are not in the repo; the demo GIFs, stills and `check.json` reports are.
