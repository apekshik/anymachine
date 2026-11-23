"""Run with blender -b --factory-startup --python-exit-code 1 --python stilt/tests/test_clash_check.py."""
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clash_check import emit_strict_report, scan_action, strict_report


def cube_tree(obj, graph):
    evaluated = obj.evaluated_get(graph)
    mesh = evaluated.to_mesh()
    try:
        return BVHTree.FromPolygons(
            [evaluated.matrix_world @ vert.co for vert in mesh.vertices],
            [tuple(poly.vertices) for poly in mesh.polygons],
        )
    finally:
        evaluated.to_mesh_clear()


def fixture(clash_frame=None, stable=False):
    bpy.ops.mesh.primitive_cube_add(size=2)
    base = bpy.context.object
    bpy.ops.mesh.primitive_cube_add(size=2)
    moving = bpy.context.object
    scene = bpy.context.scene
    for frame in range(1, 9):
        moving.location = Vector((0.75 if stable or frame == clash_frame else 4, 0.23, 0.31))
        moving.keyframe_insert(data_path="location", frame=frame)

    def overlaps(frame):
        scene.frame_set(frame)
        graph = bpy.context.evaluated_depsgraph_get()
        count = len(cube_tree(base, graph).overlap(cube_tree(moving, graph)))
        return {("base", "arm"): count} if count else {}

    return overlaps


args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if args:
    case = args[0]
    overlaps = fixture(clash_frame={"frame2": 2, "frame8": 8}.get(case), stable=case == "rest")
    emit_strict_report({case: scan_action(overlaps, overlaps(1), 8, step=1)})
else:
    for target in (2, 8):
        overlaps = fixture(clash_frame=target)
        assert overlaps(target), "fixture must contain a real geometric intersection"
        assert all(not overlaps(frame) for frame in range(1, 9) if frame != target)
        assert not scan_action(overlaps, {}, 8, step=6)["clashes"]
        result = scan_action(overlaps, {}, 8, step=1)
        assert result["frames_checked"] == 8
        assert result["clashes"] == [{
            "parts": ["base", "arm"], "first_frame": target, "worst_frame": target,
            "overlap_count": overlaps(target)[("base", "arm")],
        }], result

    clean = fixture()
    assert not scan_action(clean, {}, 8, step=1)["clashes"]
    stable = fixture(stable=True)
    rest = stable(1)
    assert rest
    assert not scan_action(stable, rest, 8, step=1)["clashes"]

    # Preserve the exact legacy threshold and report the earliest frame of a tied peak.
    pair = ("base", "arm")
    samples = [{pair: count} for count in (90, 91, 100, 100)]
    result = scan_action(lambda frame: samples[frame - 1], {pair: 10}, 4, step=1)
    assert result["clashes"] == [{
        "parts": ["base", "arm"], "first_frame": 2, "worst_frame": 3, "overlap_count": 100,
    }]
    assert strict_report({"z": result, "a": {"frames_checked": 1, "clashes": []}})["actions"][0]["action"] == "a"
    print("PASS: real overlap on frame 2, final frame overlap, clean rig, stable rest overlap, and threshold")
