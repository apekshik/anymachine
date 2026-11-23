#!/usr/bin/env bash
# AnyMachine exp 4 (soft goods): one bag end to end after build: check -> export -> verify -> stills -> demo -> mp4/gif
# bash run_bag.sh <bag> [stills views e.g. strap_length=115]
set -e
FFMPEG_X264=$(uv run --python 3.13 --with imageio-ffmpeg python -I -c "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())" | tr -d '\r')  # pipeline ffmpeg lacks libx264
source /c/Users/apek-anna/Developer/anyscene/pipeline/env.sh
B=C:/Users/apek-anna/Developer/anymachine/backpacks; S=$B/scripts; O=$B/out/$1; G=C:/Users/apek-anna/Developer/anyscene/builder/blender_gpu.py
Q=/c/Users/apek-anna/Developer/anyscene/pipeline/gpu_run.sh
X() { "$@" 2>&1 | grep -E "CHECK|EXPORTED|MEASURED|VERIFIED|RENDERED|Error|Traceback" | cut -c1-400 || true; }
X "$BLENDER" -b --python $S/check.py -- --blend $O/$1.blend --out $O/check.json --step 0.05
X "$BLENDER" -b --python $S/export.py -- --blend $O/$1.blend --glb $O/$1.glb --baked $O/$1_baked.blend
X "$BLENDER" -b --python $S/verify_glb.py -- $O/$1.glb $O/$1_baked.blend $O/verify_glb.json
rm -rf $O/stills $O/anim
X bash $Q "$BLENDER" -b --python $G --python $S/render.py -- --blend $O/$1.blend --out $O/stills --stills --samples 64 --views "${2:-}"
X bash $Q "$BLENDER" -b --python $S/render.py -- --blend $O/${1}_baked.blend --out $O/anim --anim
"$FFMPEG_X264" -y -loglevel error -framerate 24 -i $O/anim/f_%04d.png -c:v libx264 -preset slow -crf 18 -movflags +faststart -pix_fmt yuv420p $O/${1}_demo.mp4
"$FFMPEG" -y -loglevel error -framerate 24 -i $O/anim/f_%04d.png -vf "fps=15,scale=560:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer" $O/${1}_demo.gif
echo DONE $1
