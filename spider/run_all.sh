#!/usr/bin/env bash
# AnyMachine experiment 2 (robot spider), end to end from the cached generations in gen/:
# shell -> build -> check -> export -> verify -> renders (GPU queue) -> mp4/gif
set -eo pipefail
source /c/Users/apek-anna/Developer/anyscene/pipeline/env.sh
S=C:/Users/apek-anna/Developer/anymachine/spider
# Keep progress readable without masking Blender's exit status or requiring a marker.
B() {
  "$BLENDER" -b --factory-startup --python-exit-code 1 "$@" 2>&1 |
    awk '/SHELL|BUILT|SWEEP|MOTION|CHECK|EXPORTED|VERIFY|Error|Traceback/ { print substr($0, 1, 400) }'
}
B --python $S/scripts/shell.py -- --glb $S/gen/meshy/model.glb --gen meshy --out $S/gen/shell_meshy.blend --png $S/gen/shell_meshy.png --mirror right --clip-rear 0.15 --upper 0.04
B --python $S/scripts/build.py -- --shell $S/gen/shell_meshy.blend --out $S/out/spider.blend
B --python $S/scripts/check.py -- --blend $S/out/spider.blend --out $S/out/check.json
B --python $S/scripts/export.py -- --blend $S/out/spider.blend --out $S/out/spider.glb
B --python $S/scripts/verify_glb.py -- $S/out/spider.glb $S/out/verify_glb.json
bash $S/scripts/render_all.sh
