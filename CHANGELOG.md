# Changelog

All notable changes to `video-compose` are recorded here.

This project does not have tagged releases yet. Entries are grouped by public commit until the first versioned release.

## Unreleased

- No unreleased changes yet.

## 2026-05-10 — Public bootstrap and polish

### Added

- Published the initial public toolkit in `compoodment/video-compose`.
- Added `tools/video-compose.py`, a dependency-light Python + ffmpeg scripted video composer.
- Added `tools/video-kit.py`, a practical ffmpeg helper for trimming, contact sheets, frames, GIFs, captions, fades, slideshows, remixing, and common transforms.
- Added `tools/video-compose-verify.py` for rendering/probing built-in templates.
- Added `tools/video-compose-selftest.py` for focused behavioral tests.
- Added local shell wrappers under `bin/`:
  - `video-compose`
  - `video-kit`
  - `video-compose-verify`
  - `video-compose-selftest`
- Added built-in templates:
  - `lower-third`
  - `motion-card`
  - `glitch-card`
  - `band-glitch`
  - `media-card`
  - `split-screen`
- Added bundled sample media at `examples/assets/sample.ppm` so templates and examples are self-contained.
- Added starter/example specs, including animation and motion-polish examples.
- Added GitHub Actions verification for compile, validation, selftests, and template render/probe checks.
- Added draft OpenClaw AgentSkill at `skill/SKILL.md`.

### Composer capabilities

- Generated scene primitives: `card`, `bars`, `particles`, `wave`, `grid`, `orbits`, and `typewriter`.
- Media/image scenes and layered compositing scenes.
- Layer types: `media`, `panel`, `text`, and `lower_third`.
- Layer placement, sizing, crop/contain/stretch fitting, borders, rounded masks, static opacity, and timing.
- Keyframed `x`, `y`, `opacity`, and media `scale` with easing.
- Generated alpha-mask opacity keyframes for media/panel layers, including compatibility with rounded masks.
- `animate` presets for common entrances/exits:
  - `fade`
  - `fade_in`
  - `fade_out`
  - `slide_left`
  - `slide_right`
  - `slide_up`
  - `slide_down`
  - media-only `pop`
- Generated audio sources: `silence`, `tone`, `noise`, and `pulse`.
- Top-level audio-bed mixing.
- Scene transitions: `fade`, `wipeleft`, `wiperight`, `slideleft`, `slideright`, `circleopen`, and `circleclose`.
- Glitch effects, including strong reusable `band_corrupt`-style corruption with protected regions.

### CLI ergonomics

- Added spec validation before rendering.
- Added `--validate-only` and `validate` command mode.
- Added template discovery/export commands:
  - `video-compose templates`
  - `video-compose show <template|spec>`
  - `video-compose init <template|demo> <out.json>`
- `init` exports portable starter specs and copies bundled sample assets beside them so generated starters validate outside the repo checkout.
- Extra positional arguments are rejected for command modes where they would otherwise hide typos.

### Fixed / hardened

- Made lower-third defaults safer: taller rounded panel, smaller default text, better padding, and readable wrapping.
- Replaced brittle ffmpeg time-expression opacity attempts with generated grayscale alpha-mask streams.
- Validates unsupported layer/keyframe/animation combinations instead of silently ignoring them.
- Added wrapper/non-repo behavior coverage in selftests.
- Ensured CI passes on public commits through `3a22cab`.

### Known limitations

- No tagged releases yet.
- Text layers are ASS subtitle events and do not support keyframed opacity/position through the layer keyframe system.
- Media `scale` keyframes are supported; panel scaling is intentionally not exposed yet.
- The project is still an early scripted motion-graphics toolkit, not an interactive editor.
