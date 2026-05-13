# surreal-jungle-dnb-720p

2-minute 720p procedural Blender video inspired by late-90s/early-00s surreal CG worlds: blue data tunnel, alien temples, orange/green jungle, desert mirage, checkerboard gallery, candy/snow shrine, biome collision, final ascension.

Audio: generated 174 BPM jungle/DnB-ish bed from `make_audio.py`.

Run from repo root on Vale's WSL2 RTX3060 setup:

```bash
render-jobs/surreal-jungle-dnb-720p/run.sh
```

If official Blender tarball is not on PATH:

```bash
BLENDER_BIN="/path/to/blender" render-jobs/surreal-jungle-dnb-720p/run.sh
```

Outputs:

- `outputs/surreal-jungle-dnb-720p/surreal-jungle-dnb-720p.mp4`
- `outputs/surreal-jungle-dnb-720p/surreal-jungle-dnb-720p.ffprobe.json`
- `outputs/surreal-jungle-dnb-720p/surreal-jungle-dnb-720p.render.log`
- `outputs/surreal-jungle-dnb-720p/frames/`

The script fails if no CUDA/OptiX-capable GPU is selected. Frame sequence output is intentional for resume/debug.
