"""Shared integer-frame scanning for Stilt's fast and strict checks."""
import json


def scan_action(overlaps, rest, last_frame, *, step):
    frames = range(1, last_frame + 1, step)
    clashes = {}
    for frame in frames:
        for pair, count in overlaps(frame).items():
            if pair in rest and count <= rest[pair] * 3 + 60:
                continue
            if pair not in clashes:
                clashes[pair] = {
                    "parts": list(pair), "first_frame": frame,
                    "worst_frame": frame, "overlap_count": count,
                }
            elif count > clashes[pair]["overlap_count"]:
                clashes[pair].update(worst_frame=frame, overlap_count=count)
    return {"frames_checked": len(frames), "clashes": list(clashes.values())}


def strict_report(actions):
    return {
        "actions": [
            {
                "action": name,
                "frames_checked": actions[name]["frames_checked"],
                "clashes": sorted(actions[name]["clashes"], key=lambda clash: clash["parts"]),
            }
            for name in sorted(actions)
        ]
    }


def emit_strict_report(actions):
    report = strict_report(actions)
    print(json.dumps(report), flush=True)
    if any(action["clashes"] for action in report["actions"]):
        raise RuntimeError("Unexpected overlap in Stilt's strict clash check")
