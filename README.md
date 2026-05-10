# video-compose

A tiny scripted motion-graphics/video assembly toolkit for AI assistants and command-line workflows.

It is not an interactive editor. It renders videos from JSON scene specs using Python + ffmpeg: generated visuals, media layers, text/lower-thirds, transitions, audio, keyframes, rounded masks, and glitch effects.

## Requirements

- Python 3.11+
- `ffmpeg` and `ffprobe` on PATH

No Python package dependencies are required.

## Quick start

```bash
python3 tools/video-compose.py templates
python3 tools/video-compose.py template:media-card out.mp4
python3 tools/video-compose.py init media-card starter.json
python3 tools/video-compose-verify.py
```

Optional local wrappers are included under `bin/`:

```bash
export PATH="$PWD/bin:$PATH"
video-compose template:band-glitch glitch.mp4
video-compose-selftest
```

Core templates:

- `lower-third`
- `motion-card`
- `glitch-card`
- `band-glitch`
- `media-card`
- `split-screen`

## Custom specs

Render a JSON spec:

```bash
python3 tools/video-compose.py examples/video-compose.lower-third-example.json out.mp4
```

Discover/export/validate without rendering:

```bash
python3 tools/video-compose.py templates
python3 tools/video-compose.py show template:split-screen
python3 tools/video-compose.py init split-screen starter.json
python3 tools/video-compose.py --validate-only examples/video-compose.motion-polish-example.json
# or
python3 tools/video-compose.py validate template:split-screen
```

Specs can define generated scenes, layered media, text/panels, keyframes, transitions, generated audio, and audio-bed mixing. `init` writes a starter JSON file and copies bundled sample assets beside it so the starter validates outside the repo checkout.

## Spec sketch

Top-level fields:

```json
{
  "size": "640x360",
  "fps": 24,
  "transition": {"type": "fade", "duration": 0.25},
  "scenes": []
}
```

Scene types:

- generated: `card`, `bars`, `particles`, `wave`, `grid`, `orbits`, `typewriter`
- media: `image` / `media`
- compositing: `layered`

Layer types in a `layered` scene:

- `media`: image/video layer with `source`, `fit`, `width`, `height`, `x`, `y`
- `panel`: colored rectangle layer, useful for title cards and UI shapes
- `lower_third`: panel preset plus text event defaults
- `text`: subtitle/label event rendered through ASS subtitles

Media and panel layers support:

- `opacity`: static or keyframed, `0..1`
- `scale`: static or keyframed, media layers only for now
- `radius`: rounded mask radius in pixels
- `border`, `border_color`, `border_opacity`
- `start` / `end` timing
- `keyframes`: `time`, `x`, `y`, `opacity`, `scale`, `ease`
- `animate`: preset entrance/exit animation

Supported easing values: `linear`, `in_quad`, `out_quad`, `in_out_quad`, `in_cubic`, `out_cubic`, `in_out_cubic` plus `ease_in`/`ease_out` aliases.

Animation presets can be a string or object:

```json
{"animate": {"in": "pop", "out": "fade", "duration": 0.5}}
```

Supported presets: `fade`, `fade_in`, `fade_out`, `slide_left`, `slide_right`, `slide_up`, `slide_down`, `pop`, and `none`. `pop` uses scale, so it is media-only; slide/fade presets work on media and panel/lower-third layers.

Transitions: `fade`, `wipeleft`, `wiperight`, `slideleft`, `slideright`, `circleopen`, `circleclose`.

Generated audio: `silence`, `tone`, `noise`, `pulse`. A top-level audio bed can mix generated or source audio under the rendered scenes.

## Examples

```bash
python3 tools/video-compose.py examples/video-compose.example.json example.mp4
python3 tools/video-compose.py examples/video-compose.motion-example.json motion.mp4
python3 tools/video-compose.py examples/video-compose.motion-polish-example.json polish.mp4
python3 tools/video-compose.py examples/video-compose.animation-presets-example.json presets.mp4
```

`examples/assets/sample.ppm` is bundled so the examples and templates work without private local media.

## Helper tool

`tools/video-kit.py` provides practical ffmpeg helpers: trim, contact sheets, frame extraction, GIF export, mux audio, burn subtitles, crop/scale/rotate/speed/concat, title cards, captions, fades, slideshow, and remix.

## Verification

```bash
python3 tools/video-compose-verify.py
```

The verifier validates and renders the six built-in templates, probes H.264/AAC streams with `ffprobe`, and creates contact sheets for selected templates. `tools/video-compose-selftest.py` adds focused behavioral checks for template listing/export, validation, opacity keyframes, and animation presets.

## OpenClaw skill

A draft AgentSkill is included at `skill/SKILL.md` for local OpenClaw usage.

## Status

Early and intentionally small. Built to stay dependency-light and assistant-friendly.
