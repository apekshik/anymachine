"""Check that Stilt's baked GLB motion matches the source rig at sampled poses.

Run with Blender's --python-exit-code 1 to make a failed check fail the command.
This is independent of the visual/FBX checks in verify_glb.py.
"""
import argparse
import json
from math import isfinite
from pathlib import Path
import sys

import bpy
from mathutils import Matrix

# Stilt's exporter uses export_frame_step=2. Blender's GLB round trip introduces
# small numerical changes; keep position (in this model's metres) and linear
# transform (dimensionless) tolerances separate.
FRAME_STEP = 2
FRAME_TOLERANCE = 1e-3
POSITION_TOLERANCE = 0.002
LINEAR_TOLERANCE = 0.0002


def load_source(path):
    return bpy.ops.wm.open_mainfile(filepath=str(path), use_scripts=False, load_ui=False)


def armature():
    rigs = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if len(rigs) != 1:
        raise ValueError(f"Expected one armature, found {len(rigs)}")
    return rigs[0]


def activate(rig, action, slot):
    ad = rig.animation_data_create()
    ad.use_nla = False
    ad.action = action
    ad.action_slot = slot
    for bone in rig.pose.bones:
        bone.matrix_basis = Matrix.Identity(4)


def pose(rig, frame):
    bpy.context.scene.frame_set(frame)
    evaluated = rig.evaluated_get(bpy.context.evaluated_depsgraph_get())
    world = evaluated.matrix_world
    world_inverse = world.inverted()
    # The importer can choose a different local joint basis. Pose relative to
    # rest in world axes cancels such a basis change but retains actual motion.
    return {
        bone.name: (
            world @ bone.head,
            world @ bone.matrix @ bone.bone.matrix_local.inverted() @ world_inverse,
        )
        for bone in evaluated.pose.bones
    }


def source_frames(action):
    first, last = action.frame_range
    if not first.is_integer() or not last.is_integer() or first < 1 or first >= last:
        raise ValueError(f"{action.name}: expected a positive, multi-frame integer range")
    return range(int(first), int(last) + 1, FRAME_STEP)


def compare_pose(expected, actual):
    head, deform = expected
    actual_head, actual_deform = actual
    linear = [abs(deform[i][j] - actual_deform[i][j]) for i in range(3) for j in range(3)]
    position = [(head - actual_head).length, (deform.translation - actual_deform.translation).length]
    if not all(map(isfinite, linear + position)):
        return None
    return max(position), max(linear)


def add_pose_comparison(report, row, expected, actual, frame):
    first_failure = None
    for name in sorted(expected):
        error = compare_pose(expected[name], actual[name])
        if error is None:
            if first_failure is None:
                first_failure = {"detail": "non-finite transform", "bone": name}
            continue
        position, linear = error
        row["max_position_error_m"] = max(row["max_position_error_m"], position)
        row["max_linear_error"] = max(row["max_linear_error"], linear)
        if position > POSITION_TOLERANCE or linear > LINEAR_TOLERANCE:
            if first_failure is None:
                first_failure = {"bone": name, "position_error_m": position, "linear_error": linear}
    if first_failure is not None:
        report["errors"].append({"kind": "pose", "clip": row["clip"], "frame": frame, **first_failure})


def verify(source, glb):
    if "FINISHED" not in load_source(source):
        raise ValueError(f"Could not open source {source}")
    rig = armature()
    scene = bpy.context.scene
    fps, fps_base = scene.render.fps, scene.render.fps_base
    bones = set(rig.pose.bones.keys())
    clips = {}
    # The Stilt source names its single rig slot after the armature object.
    for action in sorted(bpy.data.actions, key=lambda item: item.name):
        slot = action.slots.get("OB" + rig.name)
        if slot is None:
            continue
        activate(rig, action, slot)
        clips[action.name] = {frame: pose(rig, frame) for frame in source_frames(action)}
    if not clips:
        raise ValueError("Source contains no actions for its armature")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps, scene.render.fps_base = fps, fps_base
    if "FINISHED" not in bpy.ops.import_scene.gltf(filepath=str(glb)):
        raise ValueError(f"Could not import GLB {glb}")
    rig = armature()
    ad = rig.animation_data
    tracks = {track.name: track for track in ad.nla_tracks} if ad else {}
    imported_bones = set(rig.pose.bones.keys())
    report = {"bones": len(bones), "clips": [], "errors": []}
    if bones != imported_bones:
        report["errors"].append({"kind": "bones", "missing": sorted(bones - imported_bones),
                                 "unexpected": sorted(imported_bones - bones)})
    if clips.keys() != tracks.keys():
        report["errors"].append({"kind": "clip_names", "missing": sorted(clips.keys() - tracks.keys()),
                                 "unexpected": sorted(tracks.keys() - clips.keys())})
    for clip in sorted(clips.keys() & tracks.keys()):
        expected = clips[clip]
        frames = list(expected)
        strips = tracks[clip].strips
        if len(strips) != 1 or strips[0].action is None or strips[0].action_slot is None:
            report["errors"].append({"kind": "binding", "clip": clip})
            continue
        strip = strips[0]
        action, slot = strip.action, strip.action_slot
        actual_range = list(action.frame_range)
        expected_range = [frames[0], frames[-1]]
        if any(not isfinite(a) or abs(a - e) > FRAME_TOLERANCE
               for a, e in zip(actual_range, expected_range)):
            report["errors"].append({"kind": "frame_range", "clip": clip, "expected": expected_range,
                                     "actual": [a if isfinite(a) else None for a in actual_range]})
            continue
        if bones != imported_bones:
            continue
        row = {"clip": clip, "frames": frames, "max_position_error_m": 0.0, "max_linear_error": 0.0}
        report["clips"].append(row)
        activate(rig, action, slot)
        for frame, source_pose in expected.items():
            add_pose_comparison(report, row, source_pose, pose(rig, frame), frame)
    report["ok"] = not report["errors"]
    return report


def main():
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=here / "stilt.blend")
    parser.add_argument("--glb", type=Path, default=here / "stilt.glb")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    try:
        report = verify(args.source.resolve(), args.glb.resolve())
    except (OSError, RuntimeError, ValueError) as error:
        report = {"ok": False, "errors": [{"kind": "load", "detail": str(error)}]}
    print(json.dumps(report, allow_nan=False, sort_keys=True), flush=True)
    if not report["ok"]:
        raise RuntimeError("Stilt GLB motion verification failed")


if __name__ == "__main__":
    main()
