# glass-orbit-cathedral-rtx3060

Purpose: smoke-test the Blender backend on a remote RTX3060-class GPU machine at better quality than a CPU-only VPS.

Expected renderer:

- Official Blender build available as `blender` or passed via `BLENDER_BIN=/path/to/blender`. Avoid Ubuntu apt Blender for this job; it may lack CUDA/OptiX/OIDN support.
- Python 3 available as `python3`.
- `ffmpeg` and optional `ffprobe` available on PATH for sequence encoding and metadata.
- WSL2/host should expose RTX 3060 to Linux (`nvidia-smi` works inside WSL).
- 6GB VRAM should be enough for this starter scene.

Run from the repository root:

```bash
render-jobs/glass-orbit-cathedral-rtx3060/run.sh
```

Behavior:

- The scene requests Cycles CUDA with CPU fallback disabled.
- The generated script logs Blender/Cycles devices before rendering.
- The job renders an image sequence first, then encodes MP4 with ffmpeg. This avoids useless partial MP4 stubs and allows reruns to reuse completed frames.

Outputs:

- `outputs/glass-orbit-cathedral-rtx3060.mp4`
- `outputs/glass-orbit-cathedral-rtx3060.ffprobe.json`
- `outputs/glass-orbit-cathedral-rtx3060.render.log`
- `outputs/glass-orbit-cathedral-rtx3060-frames/` frame sequence

Return the MP4/probe/log for QA for QA/assembly. If render fails, return the `.render.log` and say whether the device log showed CUDA/OptiX or CPU only.
