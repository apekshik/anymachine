# AnyMachine: experiment 1, laptop with one working lid hinge

Date: 2026-11-03. Everything runs headless with Blender 5.0. To rebuild from a checkout:

1. Put the cached Tripo laptop mesh at `laptop/gen/tripo/model.glb`. The generated mesh is not tracked here. The screen image is included at `laptop/refs/screen_ui_0.png`.
2. Install Blender 5.0 and FFmpeg with the `libx264` encoder, then run `bash laptop/run_all.sh` from the repository root. Set `BLENDER` or `FFMPEG` to use executables outside of `PATH`.

The runner uses Cycles on the CPU by default. To render with a configured GPU, set `BLENDER_GPU_SCRIPT` to a Blender Python setup script that enables the device.

## What came out

| | |
|---|---|
| Open/close demo | `out/laptop_hinge.mp4` (1280x720, 96 frames, 24 fps), `out/laptop_hinge.gif` |
| Stills | `out/stills/persp_{000,090,135}.png`, `side_{000,090,135}.png`, `hinge_{000,045,090,135}.png` (close orthographic shot of the hinge) |
| Rig | `out/laptop.blend`. The `laptop_rig` armature has the bones `root` and `lid_hinge`. Its custom prop `open` (0..1) drives the bone through a driver, and a Limit Rotation constraint holds it to 0..135 deg. |
| GLB | `out/laptop.glb` (6 MB). Actions: `open_close` (the demo) and `open_param` (1 s, linear: seek to t = open). The joint spec is stored in the rig node's extras (`anymachine`, `open`, `max_deg`). |
| Check | `out/check.json` sweeps 0..135 deg in 1 deg steps: **0 triangle overlaps at all 136 steps**. Minimum clearance is 0.32 mm, at 56 deg, between the barrel and the pedestal. Bone angle matches the command exactly. `open` = 1.4 clamps to 135 deg and `open` = -0.3 clamps to 0. |
| Build report | `out/laptop_build.json` lists every measured and derived number: hinge line, deck slope, gaps, dimensions. |

Scripts are in `scripts/`:
- `build.py`: generated GLB → rigged .blend.
- `check.py`: sweep and collision check.
- `export.py`: bakes the driver to actions and exports the GLB.
- `render.py`: stills and animation.
- `verify_glb.py`: re-imports the GLB to confirm it.
- `inspect_gen.py`, `analyze.py`, `deckprof.py`, `cavity_probe.py`: probes.

## Pipeline as built

1. **Reference.** GPT Image 2.5 (sunburst) product shot of the laptop open at about 110 deg in three-quarter view. The invented screen UI is a second GPT Image call (`refs/screen_ui_0.png`).
2. **Image-to-3D.** I ran both Tripo P2 and Meshy v7.1 and picked Tripo: crisper keys and a cleaner silhouette. Meshy was speckled and its base was about 40% thicker.
   - Tripo P2 rejects `face_limit` > 50000 with a 422. `fal.mjs` passes whatever you give it.
3. **Normalise.** Same rules as `normalize.py`: Tripo is rotated -90 deg about Z, then scaled uniformly to 0.32 m wide. The base comes out at 22.7 cm deep and 0.5→0.9 cm thick (a wedge).
4. **Measure the mechanism from the mesh** (all automatic):
   - Deck plane: per 1 cm Y bin, the area-weighted median height of up-facing faces, then a weighted line fit. It finds the 1.05 deg wedge.
   - Lid line: PCA of the vertices above the deck. The generated lid stands at 112 deg.
   - Hinge line: where the lid line meets the deck plane.
   - Back edge: from the bottom shell's vertices.
5. **Base: kept the generated top skin, rebuilt everything else.** Only faces within 2.5 mm below to 3 mm above the deck plane survive: keys, trackpad, deck texture. They sit on a clean bevelled wedge shell that follows the fitted deck plane. A small hinge pedestal is added under the barrel.
6. **Lid: rebuilt completely.** It is a stadium-profile slab whose back edge is a cylinder of radius t/2, **coaxial with the hinge axis**. The barrel turns in place, so the slab stays in the half-space above the deck plane at every angle. That is why the collision check comes out clean by construction, not by luck.
   - The lid's rest pose is tilted 1.05 deg to lie parallel to the wedge deck.
   - The closed gap is derived from the tallest key left on the deck: 0.96 mm + 0.5 mm, giving 1.46 mm.
   - Bezel: black glass. Screen: a separate quad, emission only, with a 16:9 UI cropped to the panel's aspect.
   - Screen brightness is driven by `open` (dark below about 5 deg), in .blend only.
7. **Rig.** The bone `lid_hinge` sits on the axis and points along +X, so bone Y = world X and opening is a negative rotation about Y.
   - Lid and screen are bone-parented: rigid parts, no skinning.
   - Driver: `rot_y = -open * radians(135)`. Limit Rotation on Y is [-135, 0] in local space.
8. **Export.** glTF does not carry drivers, so the driver is baked into quaternion keys in two NLA-track actions. Textures are capped at 2K.

## What worked

- **The hinge is mechanically right.** The pivot sits on the real axis at the back edge, and the barrel spins in place on its pedestal (see the `hinge_*` stills). The lid never dips below the deck, and the limits and clamping work.
- **Measuring the hinge from a generated open-pose mesh works.** The lid-line ∩ deck-plane estimate plus the bottom-shell back edge gave a sensible axis on the first try. The fact that the reference image shows the object *articulated* (lid open) is what makes the joint measurable.
- Keeping the generated surface detail as a "skin" on a clean primitive shell is a good general pattern. You keep the generator's texture and micro-geometry and own the topology that matters.

## What had to be remade (and why)

| Part | Problem in the generated mesh | Fix |
|---|---|---|
| Lid | Fused into the base through a hinge block. Too short: 20.3 cm vs a 22.7 cm base. Approximate thickness 6.9 mm with a lumpy back. | Rebuilt as a parametric slab: base footprint, t = 5 mm, coaxial barrel. |
| Screen | Black texture; no separate part. | Separate emissive quad with an invented UI. |
| Base shell | 47,776 open boundary edges (Tripo splits the mesh at UV seams). A global `holes_fill` fanned giant triangles across the keyboard. Side walls are unreliable. | Kept only the top skin and rebuilt the shell as a wedge. |
| Hinge block | The generator's block is fused to the lid stub. | Deleted, then replaced by a 1.2 mm pedestal plus the lid barrel. |
| Materials | Tripo's metallic and roughness maps turned the black keycaps into chrome. | Unlinked both maps: metallic 0.25, roughness 0.5. The lid's aluminium tint is sampled from the base colour texture on bottom faces, with sRGB→linear conversion. |
| Deck plane | A naive z-max fit doubled the slope (2.1 deg vs 1.05 deg), because keytops and hinge parts are outliers. | Area-weighted median per bin. |

### Interpretation call

The brief said "lid about 1.5 cm". Real 32 cm laptops have 5-7 mm lids and about 1.5 cm *closed* thickness, so I built a 5 mm lid on a 0.5-0.9 cm wedge base. Closed thickness is about 1.6 cm at the hinge. Lid thickness is the `--lid-t` flag if a literal 1.5 cm lid is wanted.

## Honest quality notes

- **The hinge reads correctly** in the side and hinge shots. The barrel is a clean cylinder sitting on a pedestal, with no visible floating and no clipping.
- **The base is the weak part.** It is still generator surface:
  - a dark triangular texture blotch on the left palm rest (baked into Tripo's texture);
  - keys catch a lot of light at 135 deg under the bright studio and read washed out;
  - the side profile is a plain bevelled wedge, with no ports.
- **The lid is plain.** It is a uniform aluminium slab with no back texture, logo or camera notch, and the screen quad is flat with square corners. It is fine at product-shot distance but obviously procedural up close.
- Flat-ish shading on the 12-segment barrel is visible only in the extreme close-up.
- The screen ramps from dark to on in .blend only. In the GLB it is always on.

## Microwave (stretch): generated, probed, not rigged

`refs/microwave_0.png` shows the door open with a visible glass turntable, and `gen/microwave_tripo/model.glb` was generated from it. A ray-cast probe into the opening (`scripts/cavity_probe.py`) hits a wall about 7 cm in, on a roughly 55 cm deep body. **The cavity is a shallow dent and there is no turntable.** The door is fused to the body at the hinge, as the lid was.

So for any "door + interior" machine, the endpoint must **synthesise the interior**: a cavity box from the opening outline, plus a turntable primitive. It cannot hope to cut one out. I stopped there rather than rig a cavity I'd have to invent wholesale; that is the next experiment.

## What an agent needs to do this automatically for any hinged object

1. **An articulated reference.** Prompt the generator for the object *mid-motion* (lid at 110 deg, door at 90 deg). Then the joint is measurable from the mesh: two planar clusters plus their intersection line give the axis. A closed-pose mesh leaves no seam to find.
2. **A part/joint prior per category.** For example, laptop = {base, lid; hinge on the base's back-top edge, axis ∥ width, 0..135}; microwave = {body, door: hinge on the left vertical edge, 0..100; plate: wheel on the cavity floor centre}. A VLM can propose this from the reference image as the same JSON as the request schema below. Geometry then only has to *refine* it.
3. **Robust measurement primitives:**
   - plane fits with area-weighted medians (not max/mean);
   - PCA on part clusters;
   - line∩plane for axes;
   - percentile edges for extents.
4. **A remake library:**
   - parametric slab, door and cavity box;
   - coaxial-barrel hinge ends, so the part is contained in its half-space and can't clip;
   - pedestals and knuckles;
   - turntable/wheel discs;
   - "keep the generated skin on a clean shell".
5. **Derived clearances, not constants.** The closed gap = tallest remaining protrusion + margin. Limits come from the category prior and are then verified.
6. **A verification loop:**
   - sweep each joint (and joint pairs) through its range;
   - check for zero BVH overlaps and a minimum clearance;
   - confirm the bone angle tracks the command;
   - confirm the limits clamp;
   - re-import the GLB and check the animation.
   
   This is cheap (seconds) and is what makes it safe to ship unattended.
7. **Material sanity rules:**
   - don't trust generator metallic/roughness maps on small parts;
   - sample tints for rebuilt parts from the generated texture, converting sRGB→linear.

## Proposed API: `fal-ai/anymachine/ref-to-machine`

### Request

```jsonc
{
  "source": {                         // exactly one of these
    "image_url": "https://...",       // reference photo (ideally articulated)
    "mesh_url": "https://.../x.glb",  // an existing mesh
    "anykit_item": "kit-id/item-id"   // an AnyKit prop (already normalised)
  },
  "category": "laptop",               // optional hint; otherwise a VLM proposes one
  "real_size_m": {"width": 0.32},     // or {"height": ..} / full {"fit": [x, y, z]}
  "generator": "tripo-p2",            // tripo-p2 | tripo-h31 | meshy | auto (try both, score)
  "joints": [                         // optional overrides or additions; omitted -> category prior
    {
      "name": "lid_hinge",
      "type": "hinge",                // hinge | slider | wheel | spring | ball
      "parent": "base",
      "child": "lid",                 // part names from the category prior or "parts" below
      "axis": "auto",                 // or {"origin": [x, y, z], "dir": [1, 0, 0]} in metres, Z-up, front -Y
      "limits": [0, 135],             // deg (hinge/wheel), m (slider/spring); wheel may be "continuous"
      "param": "open",                // the exposed 0..1 parameter name
      "rest": 0                       // param value of the modelled rest pose
    }
  ],
  "parts": [                          // optional remake directives
    {"name": "lid", "remake": "slab", "thickness_m": 0.005},
    {"name": "screen", "remake": "emissive_panel", "image_url": "https://.../ui.png"}
  ],
  "outputs": ["glb", "blend", "usdz", "preview_mp4"],
  "preview": {"stills_param": [0, 0.67, 1], "camera": "three_quarter"}
}
```

### Response

```jsonc
{
  "model_glb": {"url": "...", "actions": ["open_close", "lid_hinge.open_param"]},
  "blend": {"url": "..."},
  "preview_mp4": {"url": "..."},
  "stills": [{"param": {"open": 0}, "url": "..."}],
  "parts": [
    {"name": "base", "source": "generated_skin+rebuilt_shell", "tris": 41307},
    {"name": "lid", "source": "rebuilt", "tris": 1200}
  ],
  "joints": [
    {
      "name": "lid_hinge", "type": "hinge", "parent": "base", "child": ["lid", "screen"],
      "axis": {"origin": [0, 0.0829, 0.0133], "dir": [1, 0, 0]},
      "limits": [0, 135], "param": "open", "param_map": "angle_deg = open * 135",
      "bone": "lid_hinge", "gltf_action": "open_param", "action_seconds_per_unit": 1.0
    }
  ],
  "validation": {
    "sweep_steps": 136, "overlaps": 0, "min_clearance_mm": 0.32,
    "limits_clamp": true, "max_tracking_error_deg": 0.0
  },
  "dims_m": [0.32, 0.227, 0.0105],
  "remade": ["lid", "screen", "base_shell", "hinge_block"],
  "warnings": ["generator texture blotch on base (left palm rest)"],
  "cost_usd": 1.6
}
```

Notes on the schema:
- `wheel` = continuous hinge (`limits: "continuous"`) with a `speed` param.
- `spring` = slider plus `stiffness`/`rest_length`.
- `slider` uses metres.
- Every joint exposes one 0..1 param and one linear glTF action (seek `t = param` to pose it), so web/three.js consumers don't need drivers.

## Spend

About $4 estimated for this experiment, all logged to `anyscene/generate/spend.jsonl`:
- 3 images;
- Tripo P2 ×3, one of which failed with a 422 but was still logged;
- Meshy ×1.
