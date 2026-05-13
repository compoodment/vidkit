# Vidkit

Vidkit is a small scripted video toolkit for AI assistants, automation, and command-line workflows.

It is not an interactive editor. It renders videos from structured specs and helper commands, then verifies the output with ffmpeg/ffprobe. The core toolchain is dependency-light and deterministic; optional Blender support adds real 3D scene rendering when a Blender binary is available.

Vidkit currently covers three lanes:

- **Compose**: JSON-driven motion graphics, generated scenes, layered media, text, lower-thirds, UI/fake-app scenes, transitions, audio cues, and audio beds.
- **Helper**: practical ffmpeg operations such as trim, contact sheets, frame extraction, GIF export, muxing, subtitles, scale/crop, title cards, fades, slideshows, remixes, and QA bundles.
- **Blender**: optional 3D scene specs that validate without Blender, emit Blender Python, or render through Blender/Cycles/EEVEE when installed.

## Requirements

Core compose/helper workflows:

- Python 3.11+
- `ffmpeg` and `ffprobe` on PATH
- no Python package dependencies

Optional 3D rendering:

- Blender on PATH, or pass `--blender /path/to/blender`
- for GPU renders, use a Blender build with CUDA/OptiX support and request the device explicitly

## Quick start

From the repository root:

```bash
python3 tools/vidkit.py templates
python3 tools/vidkit.py template:media-card out.mp4
python3 tools/vidkit.py init media-card starter.json
python3 tools/vidkit.py verify
python3 tools/vidkit.py selftest
```

Optional wrappers are included under `bin/`:

```bash
export PATH="$PWD/bin:$PATH"
vidkit templates
vidkit template:band-glitch glitch.mp4
vidkit qa glitch.mp4 --out artifacts/qa/glitch
vidkit-selftest
```

Legacy direct scripts remain available:

```bash
python3 tools/vidkit-compose.py templates
python3 tools/vidkit-helper.py contact input.mp4 contact.jpg
python3 tools/vidkit-verify.py
python3 tools/vidkit-selftest.py
```

## CLI layout

```bash
vidkit compose <vidkit-compose args>
vidkit helper <vidkit-helper args>
vidkit verify
vidkit selftest
vidkit blender <vidkit-blender args>
```

Common shortcuts:

```bash
vidkit templates
vidkit template:<name> out.mp4
vidkit contact in.mp4 out.jpg
vidkit qa in.mp4 --out qa-dir
```

## Compose templates

Built-in compose templates:

- `lower-third`
- `motion-card`
- `glitch-card`
- `band-glitch`
- `media-card`
- `split-screen`
- `chat-window`
- `application-form`

Discover, inspect, initialize, and validate templates:

```bash
vidkit templates
vidkit show template:split-screen
vidkit init split-screen starter.json
vidkit validate template:split-screen
vidkit --validate-only examples/vidkit.motion-polish-example.json
```

Render a custom spec:

```bash
vidkit examples/vidkit.motion-polish-example.json polish.mp4
```

## Compose spec overview

A minimal spec:

```json
{
  "size": "640x360",
  "fps": 24,
  "transition": {"type": "fade", "duration": 0.25},
  "scenes": []
}
```

Scene types:

- generated visuals: `card`, `bars`, `particles`, `wave`, `grid`, `orbits`, `typewriter`
- media: `image` / `media`
- compositing: `layered`
- utility timing/comedy: `beat`

Layer types in a `layered` scene:

- `media`: image/video layer with `source`, `fit`, sizing, and placement
- `sprite`: media-layer alias for image/video elements that move through a scene
- `panel`: colored rectangle layer for cards, UI, and backing plates
- `lower_third`: readable caption/lower-third preset
- `text`: subtitle/label event burned through ASS subtitles
- `shape`: reusable primitives expanded into panel/text layers
- `preset`: reusable UI/dialog/stamp treatments expanded into layers

Layer features:

- static or keyframed `opacity`
- static or keyframed media/sprite `scale`
- rounded masks via `radius`
- borders via `border`, `border_color`, `border_opacity`
- `start` / `end` timing
- `keyframes` for `time`, `x`, `y`, `opacity`, `scale`, and `ease`
- `animate` entrance/exit presets
- `sprite_animate` helper presets

Sprite path example:

```json
{
  "type": "sprite",
  "source": "examples/assets/sample.ppm",
  "width": 92,
  "height": 68,
  "path": {
    "type": "points",
    "ease": "in_out_cubic",
    "points": [
      {"time": 0.0, "x": 36, "y": 218},
      {"time": 1.4, "x": 286, "y": 92, "ease": "out_cubic"},
      {"time": 3.0, "x": 494, "y": 198}
    ]
  }
}
```

Layered camera example:

```json
{
  "type": "layered",
  "duration": 4,
  "camera": {
    "keyframes": [
      {"time": 0, "x": -20, "y": 0, "scale": 1.04},
      {"time": 4, "x": 24, "y": 12, "scale": 1.12}
    ],
    "shake": {"start": 2.2, "end": 2.8, "amount": 8, "frequency": 18}
  },
  "layers": []
}
```

Supported easing values include `linear`, `in_quad`, `out_quad`, `in_out_quad`, `in_cubic`, `out_cubic`, and `in_out_cubic`.

Animation presets include `fade`, `fade_in`, `fade_out`, `slide_left`, `slide_right`, `slide_up`, `slide_down`, `pop`, and `none`.

Sprite helper presets include `blink`, `bounce`, `jitter`, `squash`, `pop`, and `slap`.

Shape layers currently include `progress_bar`, `checkbox`, `arrow`, `cursor`, `speech_bubble`, `file_icon`, and `window`.

Preset layers currently include `error_dialog`, `stamp`, `meme_caption`, `file_label`, `terminal_prompt`, `form_field`, and `warning_banner`.

Transitions include `fade`, `wipeleft`, `wiperight`, `slideleft`, `slideright`, `circleopen`, and `circleclose`.

Generated audio includes `silence`, `tone`, `noise`, `pulse`, and `sfx`. SFX presets are deterministic utility cues, not production samples: `bonk`, `error_beep`, `whoosh`, `censor_beep`, `printer_panic`, and `meow_ish`.

Beat scenes expand into ordinary generated/layered scenes:

```json
{"type": "beat", "preset": "bonk", "duration": 0.75, "text": "BONK"}
```

Supported beat presets include `hard_cut_card`, `bonk`, `censor_meow`, `zoom_punch`, and `error_flash`.

## Blender backend

The Blender backend is for real 3D shots: cameras, lights, materials, geometry, smooth temporal motion, and optional GPU rendering.

It can validate and emit scripts without Blender installed:

```bash
vidkit blender templates
vidkit blender show template:glass-orbit-cathedral
vidkit blender init glass-orbit-cathedral scene.json
vidkit blender validate scene.json
vidkit blender script scene.json scene.py
```

Render with Blender:

```bash
vidkit blender render scene.json out.mp4 --blender /path/to/blender
```

For GPU/Cycles jobs, request the device explicitly and prefer image sequences for long renders:

```bash
vidkit blender render scene.json out.mp4 \
  --device cuda \
  --output-mode sequence \
  --frames-dir frames \
  --no-cpu-fallback
```

A GPU-intended job should fail if the requested GPU backend is unavailable. Do not accept silent CPU fallback for long renders.

Blender spec support currently includes:

- render size, FPS, duration, engine, world color
- camera and look-at/orbit paths
- lights
- objects: cube, sphere/UV sphere, ico sphere, plane, torus, cylinder, cone, text
- materials with color, emission, roughness, and metallic values
- simple end-state animation for location, rotation, and scale

Example:

```bash
vidkit blender validate examples/vidkit.blender-glass-orbit-cathedral.json
vidkit blender script examples/vidkit.blender-glass-orbit-cathedral.json scene.py
```

## Render jobs

`render-jobs/` contains deterministic handoff packets for remote or stronger render machines. A job folder usually includes:

- a `README.md` with exact run instructions
- a render script or scene spec
- a `run.sh` wrapper
- expected output paths

Run the job from the repo root and return the MP4, ffprobe JSON, and render log. Render jobs should be benchmarked before long full renders when GPU/CPU utilization matters.

## Examples

```bash
vidkit examples/vidkit.example.json example.mp4
vidkit examples/vidkit.lower-third-example.json lower-third.mp4
vidkit examples/vidkit.motion-example.json motion.mp4
vidkit examples/vidkit.motion-polish-example.json polish.mp4
vidkit examples/vidkit.animation-presets-example.json presets.mp4
vidkit examples/vidkit.camera-sprite-example.json camera-sprite.mp4
vidkit examples/vidkit.sprite-path-example.json sprite-path.mp4
vidkit examples/vidkit.shapes-presets-example.json shapes-presets.mp4
vidkit examples/vidkit.sfx-example.json sfx.mp4
vidkit examples/vidkit.comedy-beats-example.json comedy-beats.mp4
```

`examples/assets/sample.ppm` is bundled so examples and templates work without private local media.

## Helper tool

`tools/vidkit-helper.py` wraps practical ffmpeg tasks:

- trim
- contact sheets
- frame extraction
- GIF export
- mux audio
- burn subtitles
- crop/scale/rotate/speed/concat
- title cards and captions
- fades, slideshows, remixes
- QA bundles

QA example:

```bash
vidkit qa input.mp4 --out artifacts/qa/input
```

The QA bundle writes `probe.json`, `contact.jpg`, representative `frame-*.jpg` stills, `audio-levels.txt`, and `summary.json`. When an audio stream exists, `summary.json` marks it `effectively_silent` if `max_volume` is at or below `-50 dBFS` by default.

## Verification

Run the broad verifier:

```bash
vidkit verify
```

Run focused selftests:

```bash
vidkit selftest
```

The verifier validates and renders the built-in templates, probes H.264/AAC streams with `ffprobe`, and creates contact sheets for selected templates. The selftest covers template listing/export, validation, opacity keyframes, animation presets, SFX, beat presets, and Blender script/validation behavior.

## OpenClaw skill

A draft AgentSkill is included at `skill/SKILL.md` for local OpenClaw usage.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contributor standards, issue quality expectations, feature design guidance, and verification rules.

## Status

Vidkit is early and intentionally small. The core compose/helper tools are stable enough for scripted assistant workflows. The Blender backend and render-job workflow are experimental but usable for controlled 3D render handoffs.
