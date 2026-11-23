#!/usr/bin/env bash
# AnyMachine experiment 3 (quadruped), end to end from the cached generation (refs/ + gen/meshy/model.glb):
#   bash run_all.sh [render]
# build -> check -> export -> verify GLB -> trot loop + stills (Cycles, GPU queue) -> sit/stand clip (Eevee) -> mp4/gif
set -eo pipefail
FFMPEG_X264=$(uv run --python 3.13 --with imageio-ffmpeg python -I -c "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())" | tr -d '\r')  # pipeline ffmpeg lacks libx264
source /c/Users/apek-anna/Developer/anyscene/pipeline/env.sh
Q=C:/Users/apek-anna/Developer/anymachine/quadruped; S=$Q/scripts; O=$Q/out
G=C:/Users/apek-anna/Developer/anyscene/builder/blender_gpu.py; GPU=/c/Users/apek-anna/Developer/anyscene/pipeline/gpu_run.sh
# Keep progress readable without masking Blender's exit status or requiring a marker.
B() {
  "$BLENDER" -b --factory-startup --python-exit-code 1 "$@" 2>&1 |
    awk '/BUILT|SWEEP|RANDOM|ACTION|EXPORTED|VERIFY|GLB_OK|RENDERED|Error|Traceback/'
}
if [ "$1" != render ]; then  # `bash run_all.sh render` re-renders only
B --python $S/build.py -- --glb $Q/gen/meshy/model.glb --out $O/quadruped.blend --length 0.70
B --python $S/check.py -- --blend $O/quadruped.blend --out $O/check.json --random 300 | tee $O/check.log
B --python $S/export.py -- --blend $O/quadruped.blend --out $O/quadruped.glb
B --python $S/verify_glb.py -- --glb $O/quadruped.glb --out $O/verify_glb.json
fi
rm -rf $O/anim $O/anim_sit $O/stills
R="--python $G --python $S/render.py -- --blend $O/quadruped.blend"
bash "$GPU" "$BLENDER" -b --factory-startup --python-exit-code 1 $R --out $O/anim --cam persp --action trot_forward --anim --track --samples 40 --resx 1280 --resy 720 --name trot | grep RENDERED
for a in "--cam persp --action trot_forward --frames 1,13 --track --samples 96 --resx 1600 --resy 900 --name persp" \
         "--cam persp --action sit --frames 49 --samples 96 --resx 1600 --resy 900 --name persp" \
         "--cam side --action trot --frames 1,5,10 --samples 64 --resx 1600 --resy 900 --name side" \
         "--cam side --action sit --frames 49 --samples 64 --resx 1600 --resy 900 --name side" \
         "--cam knee --action trot --frames 1,10 --samples 64 --resx 1200 --resy 900 --name knee" \
         "--cam knee --action sit --frames 49 --samples 64 --resx 1200 --resy 900 --name knee"; do
  bash "$GPU" "$BLENDER" -b --factory-startup --python-exit-code 1 $R --out $O/stills $a | grep RENDERED
done
B --python $S/render.py -- --blend $O/quadruped.blend --out $O/anim_sit --cam persp --action sit --anim --engine EEVEE --resx 960 --resy 540 --name sit
B --python $S/render.py -- --blend $O/quadruped.blend --out $O/anim_sit --cam persp --action stand --anim --engine EEVEE --resx 960 --resy 540 --name stand
cd $O
FF() { "$FFMPEG_X264" -y -loglevel error "$@"; }
FF -framerate 30 -i anim/trot_%04d.png -c:v libx264 -preset slow -crf 18 -movflags +faststart -pix_fmt yuv420p quadruped_trot.mp4
FF -framerate 30 -i anim/trot_%04d.png -vf "scale=720:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer" -loop 0 quadruped_trot.gif
# sit -> hold -> stand
FF -framerate 30 -i anim_sit/sit_%04d.png -framerate 30 -i anim_sit/stand_%04d.png -filter_complex "[0][1]concat=n=2:v=1[v]" -map "[v]" -c:v libx264 -preset slow -crf 18 -movflags +faststart -pix_fmt yuv420p quadruped_sit_stand.mp4
FF -i quadruped_sit_stand.mp4 -vf "fps=20,scale=640:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer" -loop 0 quadruped_sit_stand.gif
echo DONE
