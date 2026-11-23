#!/bin/bash
# renders/stilt_reference_to_model.mp4: the Blender result first, then the references and how they were used.
# No added text, no zooms. Plain ffmpeg. Output 1280x720, 30 fps.
set -e
cd "$(dirname "$0")"
OUT=renders/stilt_reference_to_model.mp4
TMP=$(mktemp -d renders/_tmp.XXXXXX)
trap 'rm -rf -- "$TMP"' EXIT
ENC="-r 30 -pix_fmt yuv420p -c:v libx264 -preset medium -crf 15 -an"
n=0; LIST="$TMP/list.txt"; : > "$LIST"
seg() { n=$((n+1)); printf -v o "%s/s%02d.mp4" "$TMP" $n; echo "file '$(basename $o)'" >> "$LIST"; }
fades() { echo "fade=t=in:st=0:d=0.25,fade=t=out:st=$(awk "BEGIN{print $1-0.25}"):d=0.25"; }
FIT="scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black"
FILL="scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720"
# the showcase has grey side bars for its first 14 s (the assembly); paint them black
BARS="drawbox=x=0:y=0:w=352:h=ih:color=black:t=fill,drawbox=x=928:y=0:w=352:h=ih:color=black:t=fill"

clip()  { seg; ffmpeg -v error -y -ss $2 -t $3 -i "$1" -vf "${4:+$4,}fps=30,$FIT,$(fades $3)" -t $3 $ENC "$o"; }
still() { seg; ffmpeg -v error -y -loop 1 -i "$1" -vf "$2,$(fades $3)" -t $3 $ENC "$o"; }

# 1. the Blender video: walk first, then the build, then reach and head turn
# (stilt_showcase.mp4 is build 0-14 s, walk 14-30.5, reach 30.5-43.5, head 43.5-53.5)
V=renders/stilt_showcase.mp4
clip $V 14 16.5
clip $V 0 14 "$BARS"
clip $V 30.5 13
clip $V 43.5 10

# 2. the references that were made
still refs/concept_sheet.png "$FILL" 4
still refs/stilt_turnaround.png "$FILL" 3.5
R=refs/closeup_
ffmpeg -v error -y -i ${R}head.png -i ${R}shoulder.png -i ${R}elbow.png -i ${R}hand.png \
  -i ${R}hip.png -i ${R}knee.png -i ${R}foot.png -i ${R}head_front.png \
  -filter_complex "[0:v]scale=320:320[a];[1:v]scale=320:320[b];[2:v]scale=320:320[c];[3:v]scale=320:320[d];[4:v]scale=320:320[e];[5:v]scale=320:320[f];[6:v]scale=320:320[g];[7:v]scale=320:320[h];[a][b][c][d]hstack=4[r0];[e][f][g][h]hstack=4[r1];[r0][r1]vstack,pad=1280:720:0:40:color=black" -frames:v 1 "$TMP/grid.png"
still "$TMP/grid.png" "$FIT" 4.5

# 3. how they were used: reference on the left, model on the right
for p in head shoulder elbow hand hip knee foot; do
  still renders/stilt_compare_cu_$p.jpg "$FIT" 2
done
for p in front left 3q; do
  still renders/stilt_compare_$p.jpg "$FIT" 2.4
done

STAGED="$TMP/reference_to_model.mp4"
ffmpeg -v error -y -f concat -safe 0 -i "$LIST" -c copy -movflags +faststart "$STAGED"
ffprobe -v error -show_entries format=duration,size -of csv=p=0 "$STAGED"
mv -f -- "$STAGED" "$OUT"
