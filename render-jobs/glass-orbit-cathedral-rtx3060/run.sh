#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
JOB_ID="glass-orbit-cathedral-rtx3060"
JOB_DIR="$ROOT/render-jobs/$JOB_ID"
OUT_DIR="$ROOT/outputs"
mkdir -p "$OUT_DIR"
OUT_MP4="$OUT_DIR/$JOB_ID.mp4"
PROBE="$OUT_DIR/$JOB_ID.ffprobe.json"
SCRIPT_OUT="$OUT_DIR/$JOB_ID.blender.py"
LOG="$OUT_DIR/$JOB_ID.render.log"
BLENDER_BIN="${BLENDER_BIN:-blender}"

python3 "$ROOT/tools/vidkit-blender.py" validate "$JOB_DIR/scene.json"
set +e
python3 "$ROOT/tools/vidkit-blender.py" render "$JOB_DIR/scene.json" "$OUT_MP4" --blender "$BLENDER_BIN" --keep-script "$SCRIPT_OUT" 2>&1 | tee "$LOG"
render_status=${PIPESTATUS[0]}
set -e
if [ "$render_status" -ne 0 ]; then
  echo "Render failed. Return this log to Coda: $LOG" >&2
  exit "$render_status"
fi

if command -v ffprobe >/dev/null 2>&1; then
  ffprobe -v error -show_entries format=duration,size:stream=index,codec_type,codec_name,width,height,r_frame_rate -of json "$OUT_MP4" | tee "$PROBE"
else
  echo '{"warning":"ffprobe not found; render completed but probe was skipped"}' | tee "$PROBE"
fi

echo "Rendered $OUT_MP4"
echo "Return: $OUT_MP4, $PROBE, $LOG"
