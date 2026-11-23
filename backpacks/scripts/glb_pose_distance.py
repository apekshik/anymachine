"""Nearest-vertex comparisons for a baked pose and a re-imported GLB pose."""
import json
from math import isfinite

from mathutils.kdtree import KDTree


def finite_mm(value):
    """Parse a nonnegative finite millimetre tolerance."""
    mm = float(value)
    if not isfinite(mm) or mm < 0:
        raise ValueError("expected a finite, nonnegative millimetre tolerance")
    return mm


def _tree(points, label):
    if not points or not all(isfinite(co) for point in points for co in point):
        raise ValueError(f"{label} has no points or contains non-finite coordinates")
    tree = KDTree(len(points))
    for i, point in enumerate(points):
        tree.insert(point, i)
    tree.balance()
    return tree


def _stats(tree, points):
    distances = sorted(tree.find(point)[2] * 1000 for point in points)
    if not all(map(isfinite, distances)):
        raise ValueError("non-finite nearest-vertex distance")
    n = len(distances)
    return {
        "median_mm": round(distances[n // 2], 3),
        "p99_mm": round(distances[int(n * 0.99)], 3),
        "max_mm": round(distances[-1], 3),
    }, distances[-1]


def compare_pose(reference, imported):
    """Return directional statistics and an unrounded symmetric maximum in mm."""
    source_tree = _tree(reference, "reference pose")
    imported_tree = _tree(imported, "imported pose")
    forward, forward_max = _stats(source_tree, imported)
    reverse, reverse_max = _stats(imported_tree, reference)
    worst = max(forward_max, reverse_max)
    return {
        **forward,
        "reference_to_import_mm": reverse,
        "symmetric_max_mm": round(worst, 3),
    }, worst


def export_source_meshes(objects, armature):
    """Mirror export.py's selection of the rig's direct children for meshes."""
    return [obj for obj in objects if obj.type == "MESH" and obj.parent == armature]


def import_pose_meshes(bpy, path):
    """Import a GLB without Blender's synthetic bone display geometry."""
    operator = bpy.ops.import_scene.gltf
    options = operator.get_rna_type().properties
    settings = {"disable_bone_shape": True} if "disable_bone_shape" in options else {}
    operator(filepath=str(path), **settings)
    objects = bpy.context.view_layer.objects
    bone_shapes = {bone.custom_shape for obj in objects if obj.type == "ARMATURE"
                   for bone in obj.pose.bones if bone.custom_shape is not None}
    return [obj for obj in objects if obj.type == "MESH" and obj not in bone_shapes]


def write_pose_report(out, report, poses, has_armature, tolerance_mm=None):
    """Write the report before enforcing structural, input and tolerance gates."""
    errors = ["Imported GLB has no armature"] if not has_armature else []
    if errors:
        report["errors"] = errors
    matches, failed, invalid = {}, [], []
    for name, reference, imported in poses:
        try:
            matches[name], raw_max = compare_pose(reference, imported)
        except ValueError as error:
            matches[name] = {"error": str(error)}
            invalid.append(name)
            continue
        if tolerance_mm is not None and raw_max > tolerance_mm:
            failed.append(name)
    report["pose_match"] = matches
    if tolerance_mm is not None:
        report["pose_tolerance_mm"] = tolerance_mm
        report["pose_tolerance_failures"] = failed
    with open(out, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=1, allow_nan=False)
    issues = errors + invalid + failed
    if issues:
        raise RuntimeError("GLB pose check failed: " + ", ".join(issues))
    status = "VERIFIED" if tolerance_mm is not None else "MEASURED"
    print(status, json.dumps({k: v for k, v in report.items() if k != "objects"})[:3000], flush=True)
