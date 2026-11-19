"""Measure baked-vs-imported GLB pose distances and report animation metadata.

Strict mode gates on symmetric vertex distance, a present imported armature,
and valid point clouds. It does not certify all animation or mesh properties.
blender -b --python-exit-code 1 --python verify_glb.py -- <glb> <baked.blend> <out.json> [--max-error-mm MM]
"""
import argparse
import json
from math import isfinite
import os
import sys

import bpy
sys.path.insert(0, os.path.dirname(__file__))
from glb_pose_distance import export_source_meshes, finite_mm, import_pose_meshes, write_pose_report


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("glb")
    parser.add_argument("baked")
    parser.add_argument("out")
    parser.add_argument("--max-error-mm", type=finite_mm, metavar="MM",
                        help="fail if either direction exceeds this pose error")
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])


def snap(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in sorted(objs, key=lambda o: o.name):
        oe = o.evaluated_get(dg)
        m = oe.to_mesh()
        try:
            pts += [oe.matrix_world @ v.co for v in m.vertices]
        finally:
            oe.to_mesh_clear()
    return pts


def pose_all(act_name, frame):
    for o in bpy.data.objects:
        for idb in (o, getattr(o.data, "shape_keys", None) if o.type == "MESH" else None):
            if idb is None or not idb.animation_data:
                continue
            ad = idb.animation_data
            for t in ad.nla_tracks:
                t.mute = True
            ad.action = None
    sc = bpy.context.scene
    for o in bpy.data.objects:
        for idb in (o, getattr(o.data, "shape_keys", None) if o.type == "MESH" else None):
            if idb is None or not idb.animation_data:
                continue
            for t in idb.animation_data.nla_tracks:
                t.mute = t.name != act_name
    sc.frame_set(frame)
    bpy.context.view_layer.update()


def main():
    args = arguments()
    glb, baked, out = map(os.path.abspath, (args.glb, args.baked, args.out))
    # Use only meshes the exporter selects, not guides or other scene objects.
    bpy.ops.wm.open_mainfile(filepath=baked, use_scripts=False)
    arm = next((o for o in bpy.context.scene.objects if o.type == "ARMATURE"), None)
    if arm is None:
        raise ValueError("Baked Blender scene has no armature")
    ctls = [c["param"] for c in json.loads(arm["anymachine"])["controls"]]
    source = export_source_meshes(bpy.context.view_layer.objects, arm)
    poses = [(c, f) for c in ctls for f in (1, 13, 25)] + [("demo", 60)]
    ref = {}
    for c, frame in poses:
        pose_all(f"{c}_param" if c != "demo" else c, frame)
        ref[(c, frame)] = snap(source)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    meshes = import_pose_meshes(bpy, glb)
    res = {"glb": glb, "size_kb": os.path.getsize(glb) // 1024,
           "objects": sorted((o.name, o.type) for o in bpy.data.objects),
           "actions": sorted(a.name for a in bpy.data.actions),
           "morph_targets": {o.name: [k.name for k in o.data.shape_keys.key_blocks]
                             for o in meshes if o.data.shape_keys}}
    garm = next((o for o in bpy.context.scene.objects if o.type == "ARMATURE"), None)
    res["extras_keys"] = list(garm.keys()) if garm is not None else []
    res["tracks"] = {}
    for o in bpy.data.objects:
        for idb in (o, getattr(o.data, "shape_keys", None) if o.type == "MESH" else None):
            if idb is not None and idb.animation_data:
                res["tracks"][idb.name] = [t.name for t in idb.animation_data.nla_tracks]

    def samples():
        # The importer puts each glTF animation on an NLA track named after it.
        for (c, frame), reference in ref.items():
            action = f"{c}_param" if c != "demo" else c
            pose_all(action, frame)
            yield f"{action}@{frame}", reference, snap(meshes)

    moves = {}
    for c in ctls:
        pose_all(f"{c}_param", 1)
        start = snap(meshes)
        pose_all(f"{c}_param", 25)
        end = snap(meshes)
        if not start or len(start) != len(end):
            moves[c] = None
            continue
        distances = [(a - b).length for a, b in zip(start, end)]
        moves[c] = round(max(distances) * 1000, 1) if all(map(isfinite, distances)) else None
    res["param_action_max_motion_mm"] = moves
    write_pose_report(out, res, samples(), garm is not None, args.max_error_mm)


if __name__ == "__main__":
    main()
