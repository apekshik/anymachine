"""Procedural round-trip tests. Run in Blender with --python-exit-code 1."""
import contextlib
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_glb_motion import verify


def build_fixture(directory):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = 30
    scene.render.fps_base = 1.25  # Exercise import with a non-default source timebase.
    arm = bpy.data.armatures.new("Fixture")
    rig = bpy.data.objects.new("Armature", arm)
    scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    root = arm.edit_bones.new("root")
    root.tail = (0, 1, 0)
    joint = arm.edit_bones.new("hinge")
    joint.head, joint.tail, joint.parent = (0, 1, 0), (0, 2, 0), root
    bpy.ops.object.mode_set(mode="OBJECT")
    mesh = bpy.data.meshes.new("Triangle")
    mesh.from_pydata([(0, 1, 0), (1, 1, 0), (0, 2, 0)], [], [(0, 1, 2)])
    obj = bpy.data.objects.new("Triangle", mesh)
    obj.parent = rig
    scene.collection.objects.link(obj)
    group = obj.vertex_groups.new(name="hinge")
    group.add([0, 1, 2], 1.0, "REPLACE")
    deform = obj.modifiers.new("Armature", "ARMATURE")
    deform.object = rig
    bone = rig.pose.bones["hinge"]
    bone.rotation_mode = "XYZ"

    def keyed(frames, angles):
        for frame, angle in zip(frames, angles):
            bone.rotation_euler[2] = angle
            bone.keyframe_insert("rotation_euler", frame=frame)
            bone.keyframe_insert("scale", frame=frame)

    keyed(range(1, 20, 2), (0, 0.3, 0.9, 0.8, 0.5, 0.2, 0, 0.2, 0.3, 0))
    rig.animation_data.action.name = "Lift"
    rig.animation_data.action.use_fake_user = True
    rig.animation_data.action = None
    keyed((1, 5, 10), (0, -0.45, -0.75))  # An authored final even frame.
    rig.animation_data.action.name = "Lower"
    rig.animation_data.action.use_fake_user = True
    source = directory / "source.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(source))

    def export(name, variant):
        bpy.ops.wm.open_mainfile(filepath=str(source), use_scripts=False)
        rig = bpy.data.objects["Armature"]
        ad = rig.animation_data
        ad.action = None
        for clip in ("Lift", "Lower"):
            action = bpy.data.actions[clip]
            if variant == "missing" and clip == "Lift":
                continue
            channelbag = action.layers[0].strips[0].channelbag(action.slots[0])
            for curve in channelbag.fcurves:
                if clip != "Lift":
                    continue
                for key in curve.keyframe_points:
                    if variant == "wrong_pose" and curve.data_path.endswith("rotation_euler") and curve.array_index == 2:
                        key.co.y = 0
                    elif variant == "wrong_scale" and curve.data_path.endswith("scale") and curve.array_index == 0:
                        key.co.y = 1.2 if key.co.x == 15 else 1
                    elif variant == "wrong_duration":
                        key.co.x = 1 + (key.co.x - 1) / 2
                curve.update()
            track = ad.nla_tracks.new()
            track.name = "DifferentName" if variant == "wrong_name" and clip == "Lift" else clip
            strip = track.strips.new(track.name, 1, action)
            strip.action_slot = action.slots[0]
        path = directory / (name + ".glb")
        bpy.ops.export_scene.gltf(
            filepath=str(path), export_format="GLB", export_animations=True,
            export_animation_mode="NLA_TRACKS", export_force_sampling=True,
            export_frame_step=2, export_yup=True,
        )
        return path

    return source, {v: export(v, v) for v in ("good", "wrong_pose", "wrong_scale", "wrong_duration", "wrong_name", "missing")}


class RoundTrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.source, cls.glbs = build_fixture(Path(cls.directory.name))

    def check(self, variant):
        return verify(self.source, self.glbs[variant])

    def test_good_glb_checks_both_clips_and_even_final_sampling(self):
        report = self.check("good")
        self.assertTrue(report["ok"], report)
        rows = {r["clip"]: r for r in report["clips"]}
        self.assertEqual(set(rows), {"Lift", "Lower"})
        self.assertEqual(rows["Lower"]["frames"][-1], 9)

    def test_wrong_motion_with_matching_names_is_rejected(self):
        report = self.check("wrong_pose")
        self.assertFalse(report["ok"], report)
        self.assertTrue(any(e["kind"] == "pose" and e["clip"] == "Lift" and e["bone"] == "hinge"
                            for e in report["errors"]), report)

    def test_a_single_scale_only_key_is_rejected(self):
        report = self.check("wrong_scale")
        self.assertFalse(report["ok"], report)
        bad_poses = [e for e in report["errors"] if e["kind"] == "pose" and e["clip"] == "Lift"]
        self.assertEqual([e["frame"] for e in bad_poses], [15], report)
        self.assertEqual(bad_poses[0]["bone"], "hinge")
        self.assertGreater(bad_poses[0]["linear_error"], 0.1)

    def test_wrong_duration_is_rejected(self):
        report = self.check("wrong_duration")
        self.assertFalse(report["ok"], report)
        self.assertTrue(any(e["kind"] == "frame_range" and e["clip"] == "Lift"
                            for e in report["errors"]), report)

    def test_renamed_and_missing_clips_are_rejected(self):
        for variant in ("wrong_name", "missing"):
            with self.subTest(variant=variant):
                report = self.check(variant)
                self.assertFalse(report["ok"], report)
                self.assertTrue(any(e["kind"] == "clip_names" for e in report["errors"]), report)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RoundTrip)
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        raise RuntimeError("GLB motion regression tests failed")
