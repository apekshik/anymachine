"""Procedural Blender fixture; no generated backpack assets are needed."""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from glb_pose_distance import compare_pose, export_source_meshes, finite_mm, import_pose_meshes, write_pose_report


def points(objs):
    return [obj.matrix_world @ v.co for obj in objs for v in obj.data.vertices]


def cube(name, x, parent=None):
    # A unique underlying mesh name makes the result easy to inspect, but
    # coverage comparisons do not depend on preserving that name.
    bpy.ops.mesh.primitive_cube_add(size=0.03, location=(x, 0, 0))
    obj = bpy.context.object
    obj.name = obj.data.name = name
    obj.parent = parent
    return obj


def export_selected(path, objects):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB",
                              use_selection=True, export_animations=False)


def reimport(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return points(import_pose_meshes(bpy, path))


def main():
    with TemporaryDirectory() as directory:
        intact = Path(directory) / "intact.glb"
        omitted = Path(directory) / "body-only.glb"
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.object.armature_add()
        rig = bpy.context.object
        body = cube("body", 0, rig)
        pull = cube("zipper_pull", 1, rig)
        guide = cube("guide", 2)
        bpy.context.view_layer.update()
        source = export_source_meshes(bpy.context.view_layer.objects, rig)
        assert set(source) == {body, pull} and guide not in source
        reference = points(source)
        body_only = points([body])
        export_selected(intact, [body, pull])
        export_selected(omitted, [body])
        good = reimport(intact)
        bad = reimport(omitted)

    measure, raw = compare_pose(reference, good)
    assert raw < 1e-4 and measure["symmetric_max_mm"] == 0
    measure, raw = compare_pose(reference, bad)
    assert measure["max_mm"] == 0 and measure["reference_to_import_mm"]["max_mm"] == 1000
    assert measure["symmetric_max_mm"] == 1000 and raw > finite_mm("0.1")
    measure, raw = compare_pose(body_only, good)
    assert measure["max_mm"] == 1000 and measure["reference_to_import_mm"]["max_mm"] == 0
    assert measure["symmetric_max_mm"] == 1000

    # Reordering and splitting/duplicating a vertex are not geometry loss.
    measure, raw = compare_pose(reference, list(reversed(reference)) + [reference[0]])
    assert measure["symmetric_max_mm"] == 0 and raw == 0
    measure, raw = compare_pose([Vector((0, 0, 0))], [Vector((0.0001004, 0, 0))])
    assert measure["symmetric_max_mm"] == 0.1 and raw > finite_mm("0.1")

    for ref, imported in ((reference, []), ([], reference),
                          ([Vector((float("nan"), 0, 0))], good),
                          (reference, [Vector((0, float("inf"), 0))])):
        try:
            compare_pose(ref, imported)
        except ValueError as error:
            assert "no points" in str(error) or "non-finite" in str(error)
        else:
            raise AssertionError("invalid cloud must fail")
    for value in ("-1", "nan", "inf"):
        try:
            finite_mm(value)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid threshold must fail")
    print("PASS: intact GLB; omitted part forward 0.000 mm / reverse 1000.000 mm; "
          "extra geometry; reordered/duplicated vertices; raw gate; invalid inputs")



def smoke_child(case, directory):
    path, report = Path(directory) / "fixture.glb", Path(directory) / "report.json"
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.object.armature_add()
    rig = bpy.context.object
    body = cube("body", 0, rig)
    pull = cube("zipper_pull", 1, rig)
    bpy.context.view_layer.update()
    reference = points([body, pull])
    selected = [body] if case == "dropped-part" else [body, pull]
    if case != "no-rig":
        # Export an actual skin, not just an empty transform node.
        bpy.ops.object.select_all(action="DESELECT")
        for obj in selected:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = body
        bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)
        for obj in selected:
            skin = obj.modifiers.new("Rig", "ARMATURE")
            skin.object = rig
            group = obj.vertex_groups.new(name=rig.data.bones[0].name)
            group.add(list(range(len(obj.data.vertices))), 1, "REPLACE")
        selected.append(rig)
    else:
        for obj in selected:
            obj.parent = None
    export_selected(path, selected)
    imported = reimport(path)
    has_armature = any(o.type == "ARMATURE" for o in bpy.context.scene.objects)
    write_pose_report(report, {"glb": str(path)},
                      [("demo@60", reference, imported)], has_armature, tolerance_mm=0.1)


def smoke_test():
    for case in ("intact", "dropped-part", "no-rig"):
        with TemporaryDirectory() as directory:
            run = subprocess.run(
                [bpy.app.binary_path, "-b", "--disable-autoexec", "--threads", "1",
                 "--python-exit-code", "1", "--python", str(Path(__file__).resolve()),
                 "--", case, directory],
                capture_output=True, text=True, timeout=60,
            )
            diagnostics = run.stdout + run.stderr
            assert run.returncode == (0 if case == "intact" else 1), diagnostics
            report_path = Path(directory) / "report.json"
            assert report_path.is_file(), diagnostics
            report = json.loads(report_path.read_text(encoding="utf-8"))
            pose = report["pose_match"]["demo@60"]
            assert report["pose_tolerance_mm"] == 0.1, report
            assert pose["max_mm"] == 0, report
            if case == "dropped-part":
                assert report["pose_tolerance_failures"] == ["demo@60"], report
                assert pose["symmetric_max_mm"] == 1000 and "errors" not in report, report
            else:
                assert not report["pose_tolerance_failures"] and pose["symmetric_max_mm"] == 0, report
            if case == "no-rig":
                assert report["errors"] == ["Imported GLB has no armature"], report
            if case == "intact":
                assert "VERIFIED" in diagnostics and "errors" not in report, diagnostics
            print(f"PASS: Blender report/exit smoke {case} (exit {run.returncode})", flush=True)


if __name__ == "__main__":
    if "--" in sys.argv:
        smoke_child(*sys.argv[sys.argv.index("--") + 1:])
    else:
        main()
        smoke_test()
