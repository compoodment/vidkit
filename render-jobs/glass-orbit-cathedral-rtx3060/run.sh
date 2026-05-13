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
FRAMES_DIR="$OUT_DIR/$JOB_ID-frames"
BLENDER_BIN="${BLENDER_BIN:-blender}"

{
  echo "[job] Blender: $BLENDER_BIN"
  command -v "$BLENDER_BIN" || true
  "$BLENDER_BIN" --version | head -n 5 || true
  echo "[job] nvidia-smi:"
  nvidia-smi || true
  echo "[job] ffmpeg:"
  ffmpeg -version | head -n 2 || true
} | tee "$LOG"

python3 "$ROOT/tools/vidkit-blender.py" validate "$JOB_DIR/scene.json" | tee -a "$LOG"
set +e
python3 "$ROOT/tools/vidkit-blender.py" render "$JOB_DIR/scene.json" "$OUT_MP4" --blender "$BLENDER_BIN" --keep-script "$SCRIPT_OUT" --device cuda --output-mode sequence --frames-dir "$FRAMES_DIR" --no-cpu-fallback 2>&1 | tee -a "$LOG"
render_status=${PIPESTATUS[0]}
set -e
if [ "$render_status" -ne 0 ]; then
  echo "Render failed. Return this log for QA: $LOG" >&2
  exit "$render_status"
fi

if command -v ffprobe >/dev/null 2>&1; then
  ffprobe -v error -show_entries format=duration,size:stream=index,codec_type,codec_name,width,height,r_frame_rate -of json "$OUT_MP4" | tee "$PROBE"
else
  echo '{"warning":"ffprobe not found; render completed but probe was skipped"}' | tee "$PROBE"
fi

echo "Rendered $OUT_MP4"
echo "Frames: $FRAMES_DIR"
echo "Return: $OUT_MP4, $PROBE, $LOG"
