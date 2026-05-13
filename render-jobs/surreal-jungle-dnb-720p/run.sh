#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
JOB_ID="surreal-jungle-dnb-720p"
JOB_DIR="$ROOT/render-jobs/$JOB_ID"
OUT_DIR="$ROOT/outputs/$JOB_ID"
FRAMES_DIR="$OUT_DIR/frames"
LOG="$OUT_DIR/$JOB_ID.render.log"
VIDEO_NO_AUDIO="$OUT_DIR/$JOB_ID.no-audio.mp4"
FINAL_MP4="$OUT_DIR/$JOB_ID.mp4"
PROBE="$OUT_DIR/$JOB_ID.ffprobe.json"
AUDIO="$OUT_DIR/jungle-dnb-bed.wav"
BLENDER_BIN="${BLENDER_BIN:-blender}"
mkdir -p "$OUT_DIR" "$FRAMES_DIR"
{
  echo "[job] $JOB_ID"
  echo "[job] Blender: $BLENDER_BIN"
  command -v "$BLENDER_BIN" || true
  "$BLENDER_BIN" --version | head -n 5 || true
  echo "[job] nvidia-smi:"; nvidia-smi || true
  echo "[job] ffmpeg:"; ffmpeg -version | head -n 2 || true
  echo "[job] generating audio"
} | tee "$LOG"
python3 "$JOB_DIR/make_audio.py" | tee -a "$LOG"
cp artifacts/video-compose/surreal-jungle-dnb/jungle-dnb-bed.wav "$AUDIO" 2>/dev/null || cp "$ROOT/artifacts/video-compose/surreal-jungle-dnb/jungle-dnb-bed.wav" "$AUDIO" 2>/dev/null || true
if [ ! -s "$AUDIO" ]; then
  # make_audio writes relative to cwd in older/local runs; fall back to known generated path
  find "$ROOT" -path "*/jungle-dnb-bed.wav" -print -quit | xargs -r -I{} cp {} "$AUDIO"
fi
set +e
VIDKIT_WIDTH="${VIDKIT_WIDTH:-1280}" VIDKIT_HEIGHT="${VIDKIT_HEIGHT:-720}" VIDKIT_FPS="${VIDKIT_FPS:-24}" VIDKIT_DURATION="${VIDKIT_DURATION:-120}" VIDKIT_SAMPLES="${VIDKIT_SAMPLES:-128}" VIDKIT_CYCLES_DEVICE="${VIDKIT_CYCLES_DEVICE:-CUDA}" \
  "$BLENDER_BIN" -b --python "$JOB_DIR/render_scene.py" -- "$OUT_DIR" 2>&1 | tee -a "$LOG"
render_status=${PIPESTATUS[0]}
set -e
if [ "$render_status" -ne 0 ]; then
  echo "Render failed. Return this log for QA: $LOG" >&2
  exit "$render_status"
fi
ffmpeg -y -framerate "${VIDKIT_FPS:-24}" -i "$FRAMES_DIR/frame_%04d.png" -c:v libx264 -pix_fmt yuv420p "$VIDEO_NO_AUDIO" 2>&1 | tee -a "$LOG"
ffmpeg -y -i "$VIDEO_NO_AUDIO" -i "$AUDIO" -shortest -c:v copy -c:a aac -b:a 192k "$FINAL_MP4" 2>&1 | tee -a "$LOG"
ffprobe -v error -show_entries format=duration,size:stream=index,codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels -of json "$FINAL_MP4" | tee "$PROBE"
echo "Rendered $FINAL_MP4"
echo "Return: $FINAL_MP4, $PROBE, $LOG"
