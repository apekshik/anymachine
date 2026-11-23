"""Run the backpack check against a synthetic Blender scene."""
import json
from pathlib import Path
import runpy
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("check.py")


class Point:
    def __init__(self, coords):
        self.length = 0

    def normalized(self):
        return self

    def __sub__(self, other):
        return self


class Identity:
    def __matmul__(self, point):
        return point


class NoCollisionBvh:
    @staticmethod
    def FromPolygons(vertices, triangles):
        return NoCollisionBvh()

    def find_nearest(self, point):
        return None, None, None, None

    def overlap(self, other):
        return []


class Objects(dict):
    def __iter__(self):
        return iter(self.values())


def mesh(name, arm, weight):
    vertex = NS(co=Point((0, 0, 0)), groups=[NS(group=0, weight=weight)])
    data = NS(vertices=[vertex], loop_triangles=[], calc_loop_triangles=lambda: None)
    obj = NS(name=name, type="MESH", parent=arm, data=data, vertex_groups={"lid": NS(index=0)})
    obj.evaluated_get = lambda graph: NS(
        matrix_world=Identity(), to_mesh=lambda: data, to_mesh_clear=lambda: None
    )
    return obj


def run_check(out, *, groups=None, exclusions=None, weight=1):
    check = {"body": "body", "moving": [{"name": "lid", "object": "lid", "groups": groups}]}
    if exclusions is not None:
        check["body_exclude_groups"] = exclusions
    spec = {"bag": "fixture", "controls": [{"param": "fill", "default": 0}], "check": check}

    class Arm(dict):
        type = "ARMATURE"
        animation_data = None

    arm = Arm(anymachine=json.dumps(spec))
    modules = {
        "bpy": NS(
            ops=NS(wm=NS(open_mainfile=lambda **kwargs: None)),
            data=NS(objects=Objects(arm=arm, body=mesh("body", arm, 1), lid=mesh("lid", arm, weight))),
            context=NS(evaluated_depsgraph_get=lambda: None),
        ),
        "mathutils": NS(Vector=Point),
        "mathutils.bvhtree": NS(BVHTree=NoCollisionBvh),
        "softlib": NS(set_controls=lambda arm, values: None),
    }
    argv = ["blender", "--", "--blend", "fixture.blend", "--out", str(out), "--step", "0.5"]
    with patch.dict(sys.modules, modules), patch.object(sys, "argv", argv), patch.object(sys, "path", list(sys.path)):
        runpy.run_path(str(SCRIPT), run_name="__main__")


class CollisionGroupTests(unittest.TestCase):
    def test_empty_explicit_mask_does_not_report_a_pass(self):
        self.assert_check_rejects("lid: collision check groups select no vertices: lid", groups=["lid"], weight=0.25)

    def test_missing_mover_group_does_not_report_a_pass(self):
        self.assert_check_rejects("lid: unknown vertex groups for collision check: typo", groups=["typo"])

    def test_missing_body_exclusion_group_does_not_report_a_pass(self):
        self.assert_check_rejects("body: unknown vertex groups for collision check: typo", exclusions=["lid", "typo"])

    def test_valid_groups_and_absent_masks_still_run_the_sweep(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "check.json"
            for groups in (["lid"], None):
                with self.subTest(groups=groups):
                    run_check(out, groups=groups)
                    report = json.loads(out.read_text())
                    self.assertTrue(report["pass"])
                    self.assertEqual(report["states"], 3)

    def assert_check_rejects(self, message, **options):
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "check.json"
            with self.assertRaisesRegex(ValueError, message):
                run_check(out, **options)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
