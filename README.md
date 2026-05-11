# vidkit

A tiny scripted motion-graphics/video assembly toolkit for AI assistants and command-line workflows.

It is not an interactive editor. It renders videos from JSON scene specs using Python + ffmpeg: generated visuals, media layers, text/lower-thirds, transitions, audio, keyframes, rounded masks, and glitch effects.

## Requirements

- Python 3.11+
- `ffmpeg` and `ffprobe` on PATH

No Python package dependencies are required.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contributor standards, issue quality expectations, feature design guidance, and verification rules.

## Quick start

```bash
python3 tools/vidkit-compose.py templates
python3 tools/vidkit-compose.py template:media-card out.mp4
python3 tools/vidkit-compose.py init media-card starter.json
python3 tools/vidkit-verify.py
```

Optional local wrappers are included under `bin/`:

```bash
export PATH="$PWD/bin:$PATH"
vidkit template:band-glitch glitch.mp4
vidkit-selftest
```

Core templates:

- `lower-third`
- `motion-card`
- `glitch-card`
- `band-glitch`
- `media-card`
- `split-screen`
- `chat-window`
- `application-form`

## Custom specs

Render a JSON spec:

```bash
python3 tools/vidkit-compose.py examples/vidkit.lower-third-example.json out.mp4
```

Discover/export/validate without rendering:

```bash
python3 tools/vidkit-compose.py templates
python3 tools/vidkit-compose.py show template:split-screen
python3 tools/vidkit-compose.py init split-screen starter.json
python3 tools/vidkit-compose.py --validate-only examples/vidkit.motion-polish-example.json
# or
python3 tools/vidkit-compose.py validate template:split-screen
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
- utility beats: `beat`

Layer types in a `layered` scene:

- `media`: image/video layer with `source`, `fit`, `width`, `height`, `x`, `y`
- `sprite`: clearer media-layer alias for image/video elements that move through a scene
- `panel`: colored rectangle layer, useful for title cards and UI shapes
- `lower_third`: panel preset plus text event defaults
- `text`: subtitle/label event rendered through ASS subtitles
- `shape`: reusable primitives expanded into panel/text layers
- `preset`: reusable text/dialog/stamp treatments expanded into panel/text/shape layers

Media, sprite, and panel layers support:

- `opacity`: static or keyframed, `0..1`
- `scale`: static or keyframed, media/sprite layers only for now
- `radius`: rounded mask radius in pixels
- `border`, `border_color`, `border_opacity`
- `start` / `end` timing
- `keyframes`: `time`, `x`, `y`, `opacity`, `scale`, `ease`
- `animate`: preset entrance/exit animation
- `sprite_animate`: media-layer helper animation presets expanded into the same keyframe path

Sprite layers require `source` and otherwise render like media layers. They can use ordinary `keyframes`, or a `path` object that expands to `x`/`y` keyframes before rendering:

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

`path` currently supports only `type: "points"`. Points must be in increasing time order and within the scene duration. Use either `path` or explicit `keyframes` on a layer, not both.

Supported easing values: `linear`, `in_quad`, `out_quad`, `in_out_quad`, `in_cubic`, `out_cubic`, `in_out_cubic` plus `ease_in`/`ease_out` aliases.

Animation presets can be a string or object:

```json
{"animate": {"in": "pop", "out": "fade", "duration": 0.5}}
```

Supported presets: `fade`, `fade_in`, `fade_out`, `slide_left`, `slide_right`, `slide_up`, `slide_down`, `pop`, and `none`. `pop` uses scale, so it is media-only; slide/fade presets work on media and panel/lower-third layers.

Layered scenes can define a scene-level `camera` object. Camera keyframes support `x`, `y`, and `scale`; optional `shake` supports `start`, `end`, `amount`, and `frequency`. The camera transform is applied to the composed non-text video before ASS subtitles and text layers are burned in, so ASS text remains screen-fixed and readable where practical. Non-text backing panels still move with the camera.

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

Media layers can use `sprite_animate` as a string, object, or list of objects. Supported helper presets are `blink`, `bounce`, `jitter`, `squash`, `pop`, and `slap`; unsupported names fail validation. These helpers add keyframes unless the same property already has explicit keyframes.

Shape layers use `"type": "shape"` with a `"shape"` name. First-pass shapes are `progress_bar`, `checkbox`, `arrow`, `cursor`, `speech_bubble`, `file_icon`, and `window`. Common fields include `x`, `y`, `width`, `height`, `start`, `end`, `opacity`, `color`, `fill`, `background`, `border_color`, and `radius`; shape-specific fields include `value` for `progress_bar`, `checked` for `checkbox`, `direction` for `arrow`, and `text` for `speech_bubble`.

Preset layers use `"type": "preset"` with a `"preset"` name. First-pass presets are `error_dialog`, `stamp`, `meme_caption`, `file_label`, `terminal_prompt`, `form_field`, and `warning_banner`. Presets are validated by name and require obvious text fields, then expand into existing shape/panel/text layers before render.

Transitions: `fade`, `wipeleft`, `wiperight`, `slideleft`, `slideright`, `circleopen`, `circleclose`.

Generated audio: `silence`, `tone`, `noise`, `pulse`, `sfx`. A top-level audio bed can mix generated or source audio under the rendered scenes. SFX presets are deterministic generated utility cues, not samples or production music: `bonk`, `error_beep`, `whoosh`, `censor_beep`, `printer_panic`, and `meow_ish`.

Beat scenes are short reusable comedy beats that expand into ordinary generated/layered scenes before rendering. Use `"type": "beat"` with a `"preset"` plus simple text/color/audio overrides. Supported beat presets are `hard_cut_card`, `bonk`, `censor_meow`, `zoom_punch`, and `error_flash`.

```json
{"type": "beat", "preset": "bonk", "duration": 0.75, "text": "BONK"}
```

Each beat has a generated utility sound by default; set `"audio": {"type": "silence"}` or provide another generated audio object to override it.

## Examples

```bash
python3 tools/vidkit-compose.py examples/vidkit.example.json example.mp4
python3 tools/vidkit-compose.py examples/vidkit.motion-example.json motion.mp4
python3 tools/vidkit-compose.py examples/vidkit.motion-polish-example.json polish.mp4
python3 tools/vidkit-compose.py examples/vidkit.animation-presets-example.json presets.mp4
python3 tools/vidkit-compose.py examples/vidkit.camera-sprite-example.json camera-sprite.mp4
python3 tools/vidkit-compose.py examples/vidkit.sprite-path-example.json sprite-path.mp4
python3 tools/vidkit-compose.py examples/vidkit.shapes-presets-example.json shapes-presets.mp4
python3 tools/vidkit-compose.py examples/vidkit.sfx-example.json sfx.mp4
python3 tools/vidkit-compose.py examples/vidkit.comedy-beats-example.json comedy-beats.mp4
```

`examples/assets/sample.ppm` is bundled so the examples and templates work without private local media.

## Helper tool

`tools/vidkit-helper.py` provides practical ffmpeg helpers: trim, contact sheets, frame extraction, GIF export, mux audio, burn subtitles, crop/scale/rotate/speed/concat, title cards, captions, fades, slideshow, remix, and QA bundles.

```bash
python3 tools/vidkit.py qa input.mp4 --out artifacts/qa/input
```

The QA bundle writes `probe.json`, `contact.jpg`, representative `frame-*.jpg` stills, `audio-levels.txt` from `volumedetect`, and `summary.json`. When an audio stream exists, `summary.json` marks it `effectively_silent` if `max_volume` is at or below `-50 dBFS` by default.

## Verification

```bash
python3 tools/vidkit-verify.py
```

The verifier validates and renders the built-in templates, probes H.264/AAC streams with `ffprobe`, and creates contact sheets for selected templates. `tools/vidkit-selftest.py` adds focused behavioral checks for template listing/export, validation, opacity keyframes, animation presets, SFX, and beat presets.

## OpenClaw skill

A draft AgentSkill is included at `skill/SKILL.md` for local OpenClaw usage.

## Status

Early and intentionally small. Built to stay dependency-light and assistant-friendly.
