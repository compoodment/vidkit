#!/usr/bin/env bash
set -euo pipefail
MODE="${1:-benchmark}"
if [[ "$MODE" != "benchmark" && "$MODE" != "full" ]]; then
  echo "Usage: $0 [benchmark|full]" >&2
  exit 2
fi
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
JOB_ID="surreal-cg-dnb-20s-v2"
JOB_DIR="$ROOT/render-jobs/$JOB_ID"
OUT_DIR="$ROOT/outputs/$JOB_ID"
FRAMES_DIR="$OUT_DIR/frames"
BENCH_DIR="$OUT_DIR/benchmark-frames"
LOG="$OUT_DIR/$JOB_ID.render.log"
VIDEO_NO_AUDIO="$OUT_DIR/$JOB_ID.no-audio.mp4"
FINAL_MP4="$OUT_DIR/$JOB_ID.mp4"
PROBE="$OUT_DIR/$JOB_ID.ffprobe.json"
AUDIO="$OUT_DIR/jungle-dnb-20s.wav"
BLENDER_BIN="${BLENDER_BIN:-blender}"
mkdir -p "$OUT_DIR" "$FRAMES_DIR" "$BENCH_DIR"
{
  echo "[job] $JOB_ID mode=$MODE"
  echo "[job] Blender: $BLENDER_BIN"
  command -v "$BLENDER_BIN" || true
  "$BLENDER_BIN" --version | head -n 5 || true
  echo "[job] nvidia-smi before:"; if command -v nvidia-smi >/dev/null 2>&1; then nvidia-smi; else echo "nvidia-smi not found"; fi
  echo "[job] ffmpeg:"; ffmpeg -version | head -n 2 || true
  echo "[job] generating 20s audio"
} | tee "$LOG"
python3 "$JOB_DIR/make_audio.py" "$AUDIO" | tee -a "$LOG"

set +e
VIDKIT_RENDER_MODE="$MODE" \
VIDKIT_WIDTH="${VIDKIT_WIDTH:-1280}" \
VIDKIT_HEIGHT="${VIDKIT_HEIGHT:-720}" \
VIDKIT_FPS="${VIDKIT_FPS:-24}" \
VIDKIT_DURATION="${VIDKIT_DURATION:-20}" \
VIDKIT_SAMPLES="${VIDKIT_SAMPLES:-96}" \
VIDKIT_BENCHMARK_FRAMES="${VIDKIT_BENCHMARK_FRAMES:-48}" \
VIDKIT_CYCLES_DEVICE="${VIDKIT_CYCLES_DEVICE:-CUDA}" \
VIDKIT_ALLOW_CPU="${VIDKIT_ALLOW_CPU:-0}" \
  "$BLENDER_BIN" -b --python "$JOB_DIR/render_scene.py" -- "$OUT_DIR" 2>&1 | tee -a "$LOG"
render_status=${PIPESTATUS[0]}
set -e
{
  echo "[job] nvidia-smi after:"; if command -v nvidia-smi >/dev/null 2>&1; then nvidia-smi; else echo "nvidia-smi not found"; fi
} | tee -a "$LOG"
if [[ "$render_status" -ne 0 ]]; then
  echo "Render failed. Return this log for QA: $LOG" >&2
  exit "$render_status"
fi
if [[ "$MODE" == "benchmark" ]]; then
  echo "Benchmark complete. Inspect CPU/GPU utilization and sample frames in: $BENCH_DIR" | tee -a "$LOG"
  echo "If GPU carries the render and CPU is not pegged, run: $0 full" | tee -a "$LOG"
  exit 0
fi
ffmpeg -y -framerate "${VIDKIT_FPS:-24}" -i "$FRAMES_DIR/frame_%04d.png" -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" -c:v libx264 -pix_fmt yuv420p "$VIDEO_NO_AUDIO" 2>&1 | tee -a "$LOG"
ffmpeg -y -i "$VIDEO_NO_AUDIO" -i "$AUDIO" -shortest -c:v copy -c:a aac -b:a 192k "$FINAL_MP4" 2>&1 | tee -a "$LOG"
ffprobe -v error -show_entries format=duration,size:stream=index,codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels -of json "$FINAL_MP4" | tee "$PROBE"
echo "Rendered $FINAL_MP4"
echo "Return: $FINAL_MP4, $PROBE, $LOG"
