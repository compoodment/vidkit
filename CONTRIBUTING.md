# Contributing to Vidkit

Vidkit is a small scripted video toolkit for AI assistants, command-line workflows, and fast creative iteration.

The goal is not to become a full editor. The goal is to make it easy to describe, render, inspect, and iterate on short composed videos with clear specs and repeatable outputs.

## Project taste

Good Vidkit features should create **creative leverage**: they should make new kinds of videos easier to build from reusable pieces.

Prefer features that help compose visuals from reusable parts:

- scenes
- layers
- sprites
- text treatments
- shapes
- camera moves
- transitions
- sound cues
- verification artifacts

Prefer reusable patterns over isolated effects.

## Non-negotiables

- **Scriptable first.** Vidkit is a CLI/spec renderer, not a GUI editor.
- **Dependency-light.** Prefer Python standard library plus `ffmpeg`/`ffprobe`. Add dependencies only when the value is substantial and the maintenance cost is acceptable.
- **Portable examples.** Public examples must run without private local media or machine-specific paths.
- **Readable specs.** A person should be able to inspect a spec and understand the video structure.
- **Verified output.** Rendering without errors is not enough when visual or audio quality matters.
- **Small changes.** Prefer focused, reviewable increments over broad rewrites.

## Issue quality standard

Issues are project memory. A good issue should let someone resume the work later without needing prior discussion context.

Feature issues should include:

1. **Problem / opportunity** — the creative or workflow gap.
2. **User-facing shape** — how the CLI/spec/API should feel to the caller.
3. **Examples** — a concrete command, spec snippet, or storyboard beat.
4. **Acceptance criteria** — observable requirements for calling the issue done.
5. **Verification** — commands, probes, contact sheets, frames, or audio checks expected before close.
6. **Non-goals** — what the issue intentionally does not solve.

Good title:

- `Add reusable comedy beat presets`

Weak title:

- `Improve videos`

If an issue cannot name its output or verification path, it is probably not ready to implement.

## Design checklist

Before implementing a feature, answer:

- What new thing can users make after this lands?
- Can it be expressed cleanly in JSON or a simple CLI command?
- Does it compose with existing scenes, layers, templates, and helper tools?
- Is it general enough to use in more than one project or workflow?
- What is the smallest public example that proves it?
- What validation errors should users see for bad input?
- What verification proves the output works?

If the answer is “write custom Python for one output,” it may belong in an example or artifact, not the core engine.

## Implementation standards

- Keep the core renderer understandable.
- Prefer explicit validation errors over silent fallback.
- Keep temporary/generated files under the relevant output or artifact directory.
- Avoid hidden global state. Specs should be portable when practical.
- Preserve existing examples/templates unless a breaking change is deliberate and documented.
- When adding a spec field, update validation, docs, and at least one example together.
- Keep randomness deterministic where practical. If randomness is part of the feature, expose a seed or keep it local to generated visuals.
- Do not bake private paths, project-specific taste, or one-off content into generic primitives.

## Examples and templates

User-facing features should usually include at least one of:

- a small example JSON under `examples/`
- a built-in template or template variant
- a focused self-test fixture
- a rendered verification artifact from `vidkit-verify`

Examples should be:

- public-safe
- dependency-light
- short enough to understand
- visually useful, not just technically valid

If an example exists only to exercise a field, keep it minimal. If it is meant to demonstrate a workflow, make the output look intentional.

## Verification expectations

Use the smallest meaningful gate for the change.

Common checks:

- `python3 -m compileall tools`
- JSON validation for spec/schema changes
- `python3 tools/vidkit-selftest.py` for renderer behavior
- `python3 tools/vidkit-verify.py` for template/render coverage
- `ffprobe` checks for video/audio streams
- contact sheets or representative frames for visual features
- audio level checks when sound matters
- `vidkit qa <input.mp4> --out <dir>` for a reusable probe/contact/frame/audio summary bundle

Important: an audio stream is not proof that audio is usable. If sound is part of the feature, check audibility/levels.

Important: an ffmpeg success exit is not proof that a visual feature is readable. If text/layout/composition matters, inspect frames or a contact sheet.

## Documentation expectations

Documentation should explain caller-facing behavior, not implementation history.

Update docs when a change affects:

- CLI commands
- JSON spec fields
- scene or layer capabilities
- templates
- helper commands
- verification workflow
- contributor or issue standards

Keep docs concise. Prefer one clear example over a long abstract explanation.

## Pull request standard

A good PR description includes:

- what changed
- why it changed
- how to try it
- what was verified
- visual/audio artifacts inspected, when relevant
- known gaps or follow-up issues

Do not claim a creative/video feature is done without either:

- a render artifact,
- a contact sheet or representative frame inspection,
- an audio-level check when sound matters,
- or a clear note explaining why visual/audio verification was not possible.

## Backlog hygiene

Keep the backlog useful:

- Split large ideas into coherent feature issues.
- Link related issues instead of duplicating context.
- Close or rewrite issues that no longer match the project direction.
- Promote patterns from experiments into issues only when they are likely to be reused.
- Prefer fewer high-quality issues over many vague placeholders.

## What not to add casually

Be careful with:

- heavyweight dependencies
- GUI/editor ambitions
- private local assets
- copyrighted media or sound packs
- broad plugin systems before the core API is stable
- features that only serve one output

Vidkit should stay small, inspectable, and useful.
