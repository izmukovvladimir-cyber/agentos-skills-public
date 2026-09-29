#!/usr/bin/env bash
# Probe every slide and cut its last frame to a 700px jpg for visual check.
set -euo pipefail
dir="${1:?usage: qa_frames.sh DIR_WITH_MP4}"
[[ -d "$dir" ]] || { echo "missing dir: $dir" >&2; exit 1; }
shopt -s nullglob
files=("$dir"/*.mp4)
(( ${#files[@]} > 0 )) || { echo "no mp4 in: $dir" >&2; exit 1; }
out="$dir/qa"; mkdir -p "$out"
for f in "${files[@]}"; do
  meta=$(ffprobe -v error -show_entries stream=width,height:format=duration -of csv=p=0 "$f" | tr '\n' ' ')
  dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f")
  ss=$(python3 -c "import sys; print(max(0, float(sys.argv[1]) - 0.5))" "$dur")
  ffmpeg -v error -y -ss "$ss" -i "$f" -frames:v 1 -vf scale=700:-1 "$out/$(basename "${f%.mp4}")_end.jpg"
  echo "$(basename "$f"): $meta"
done
