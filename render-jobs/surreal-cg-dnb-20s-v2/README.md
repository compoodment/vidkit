# surreal-cg-dnb-20s-v2

20-second 720p Blender/Cycles GPU render job inspired by late-90s/early-00s surreal glossy CG worlds.

Design goals:

- short iteration length: 20 seconds, not a 2-minute draft
- distinct scene grammar per shot, not repeated pans over reused objects
- GPU-offloaded render: explicit CUDA/OptiX, fail-fast if unavailable
- CPU-efficient scene structure: no frame-change handlers, no visibility churn, linked mesh duplicates/instancing-friendly repetition
- render image sequence first, then encode MP4 with generated jungle/DnB-ish audio

Shot plan:

1. candy desert shrine — low forward dolly through glossy candy architecture toward a chrome jellyfish tower
2. porray temple — vertical crane/roll through red columns with teal face masks and an iridescent glass orb
3. desert cable bones — ground-skimming tracking shot along chrome cable ribs toward black monoliths
4. green sky jungle — aerial swoop over bulb-canopy wetlands with manta silhouettes
5. chrome egg canyon — spiral ascent through black cliffs and reflective floating eggs

## Run

From repo root on a remote RTX-class Linux/WSL2 setup:

```bash
render-jobs/surreal-cg-dnb-20s-v2/run.sh benchmark
```

Check CPU/GPU utilization during the benchmark. If CPU is pegged while GPU is low, stop and return the log instead of running the full job.

If benchmark looks healthy:

```bash
render-jobs/surreal-cg-dnb-20s-v2/run.sh full
```

If Blender is not on PATH:

```bash
BLENDER_BIN="/path/to/blender" render-jobs/surreal-cg-dnb-20s-v2/run.sh benchmark
BLENDER_BIN="/path/to/blender" render-jobs/surreal-cg-dnb-20s-v2/run.sh full
```

Outputs:

- `outputs/surreal-cg-dnb-20s-v2/surreal-cg-dnb-20s-v2.mp4`
- `outputs/surreal-cg-dnb-20s-v2/surreal-cg-dnb-20s-v2.ffprobe.json`
- `outputs/surreal-cg-dnb-20s-v2/surreal-cg-dnb-20s-v2.render.log`
- `outputs/surreal-cg-dnb-20s-v2/frames/`

Environment overrides:

- `VIDKIT_CYCLES_DEVICE=CUDA|OPTIX|GPU|AUTO` default `CUDA`
- `VIDKIT_SAMPLES=96` default full samples
- `VIDKIT_WIDTH=1280`, `VIDKIT_HEIGHT=720`, `VIDKIT_FPS=24`, `VIDKIT_DURATION=20`
- `VIDKIT_BENCHMARK_FRAMES=48` default benchmark frame count
