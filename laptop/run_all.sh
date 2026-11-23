#!/usr/bin/env bash
# AnyMachine experiment 1, end to end (after refs + gen/ exist): build -> check -> export -> stills -> anim -> mp4/gif
set -euo pipefail

D=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
OUT="$D/out"
BLENDER=${BLENDER:-blender}
FFMPEG=${FFMPEG:-ffmpeg}
MODEL="$D/gen/tripo/model.glb"
UI="$D/refs/screen_ui_0.png"

fail() { printf '%s\n' "$*" >&2; exit 1; }
[[ -r "$MODEL" ]] || fail "Missing cached Tripo model: $MODEL"
[[ -r "$UI" ]] || fail "Missing screen reference: $UI"
command -v -- "$BLENDER" >/dev/null || fail "Blender 5.0 is required; set BLENDER to its executable."
command -v -- "$FFMPEG" >/dev/null || fail "FFmpeg with libx264 is required; set FFMPEG to its executable."
encoders=$("$FFMPEG" -hide_banner -encoders 2>&1)
[[ $encoders =~ [[:space:]]libx264[[:space:]] ]] || fail "FFmpeg must support the libx264 encoder."

render_args=(--python "$D/scripts/render.py")
device=CPU
if [[ -n ${BLENDER_GPU_SCRIPT:-} ]]; then
    [[ -r "$BLENDER_GPU_SCRIPT" ]] || fail "Missing Blender GPU setup script: $BLENDER_GPU_SCRIPT"
    render_args=(--python "$BLENDER_GPU_SCRIPT" "${render_args[@]}")
    device=GPU
fi

blender_run() { "$BLENDER" -b --factory-startup --python-exit-code 1 "$@"; }
render() {
    blender_run "${render_args[@]}" -- \
        --blend "$OUT/laptop.blend" --device "$device" "$@"
}

blender_run --python "$D/scripts/build.py" -- --glb "$MODEL" --gen tripo --ui "$UI" --out "$OUT/laptop.blend"
blender_run --python "$D/scripts/check.py" -- --blend "$OUT/laptop.blend" --out "$OUT/check.json" --step 1
blender_run --python "$D/scripts/export.py" -- --blend "$OUT/laptop.blend" --out "$OUT/laptop.glb"
render --out "$OUT/stills" --stills 0,90,135 --samples 128 --resx 1600 --resy 900 --cam persp
render --out "$OUT/stills" --stills 0,90,135 --samples 96 --resx 1600 --resy 900 --cam side
render --out "$OUT/stills" --stills 0,45,90,135 --samples 64 --resx 1200 --resy 900 --cam hinge

# Fresh animation frames keep leftovers from earlier runs out of the encodes.
anim=$(mktemp -d "$OUT/anim.XXXXXX")
trap 'rm -rf -- "$anim"' EXIT
render --out "$anim" --anim --samples 48 --resx 1280 --resy 720 --cam persp
"$FFMPEG" -y -loglevel error -framerate 24 -i "$anim/f_%04d.png" -c:v libx264 -preset slow -crf 18 -movflags +faststart -pix_fmt yuv420p "$OUT/laptop_hinge.mp4"
"$FFMPEG" -y -loglevel error -framerate 24 -i "$anim/f_%04d.png" -vf "fps=16,scale=640:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer" "$OUT/laptop_hinge.gif"
echo DONE
