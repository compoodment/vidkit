#!/usr/bin/env python3
"""Lightweight behavioral tests for vidkit."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def bin_path(name: str) -> str:
    local = ROOT / "tools" / f"{name}.py"
    if local.exists():
        return str(local)
    return shutil.which(name) or str(Path.home() / f".local/bin/{name}")


def wrapper_path(name: str) -> str:
    wrapper = ROOT / "bin" / name
    if wrapper.exists():
        return str(wrapper)
    return bin_path(name)


def run(cmd: list[str], *, check: bool = True, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, check=check, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def write_json(path: Path, spec: dict) -> None:
    path.write_text(json.dumps(spec, indent=2), encoding="utf-8")


def average_frame(video: Path, timestamp: float) -> float:
    raw = subprocess.check_output([
        bin_path("ffmpeg"),
        "-v",
        "error",
        "-ss",
        str(timestamp),
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-",
    ])
    return sum(raw) / len(raw)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="vidkit-selftest-") as tmp:
        tmpdir = Path(tmp)

        templates = run([wrapper_path("vidkit"), "templates"]).stdout.splitlines()
        if "media-card" not in templates or "split-screen" not in templates:
            raise SystemExit(f"template list selftest failed: {templates}")
        initialized = tmpdir / "initialized.json"
        run([wrapper_path("vidkit"), "init", "media-card", str(initialized)])
        run([wrapper_path("vidkit"), "--validate-only", str(initialized)])
        shown = run([wrapper_path("vidkit"), "show", "template:media-card"]).stdout
        if "examples/assets/sample.ppm" not in shown:
            raise SystemExit("template show selftest failed: expected portable sample asset path")
        failed = run([wrapper_path("vidkit"), "templates", "unexpected"], check=False)
        if failed.returncode == 0:
            raise SystemExit("extra-argument selftest failed")

        external = tmpdir / "external"
        external.mkdir()
        run([wrapper_path("vidkit"), "init", "media-card", "starter.json"], cwd=external)
        run([wrapper_path("vidkit"), "--validate-only", "starter.json"], cwd=external)
        if not (external / "examples" / "assets" / "sample.ppm").exists():
            raise SystemExit("wrapper init asset-copy selftest failed")

        opacity_spec = {
            "size": "160x90",
            "fps": 10,
            "scenes": [
                {
                    "type": "layered",
                    "duration": 1.2,
                    "background": "#000000",
                    "audio": {"type": "silence"},
                    "layers": [
                        {
                            "type": "panel",
                            "x": 0,
                            "y": 0,
                            "width": 160,
                            "height": 90,
                            "panel_color": "#ffffff",
                            "opacity": 1.0,
                            "keyframes": [
                                {"time": 0.0, "opacity": 0.0},
                                {"time": 1.0, "opacity": 1.0},
                            ],
                        }
                    ],
                }
            ],
        }
        opacity_path = tmpdir / "opacity.json"
        opacity_video = tmpdir / "opacity.mp4"
        write_json(opacity_path, opacity_spec)
        run([wrapper_path("vidkit"), "--validate-only", str(opacity_path)])
        run([wrapper_path("vidkit"), str(opacity_path), str(opacity_video)])
        start_avg = average_frame(opacity_video, 0.0)
        late_avg = average_frame(opacity_video, 1.0)
        if not (start_avg < 5 and late_avg > 240):
            raise SystemExit(f"opacity selftest failed: start={start_avg:.2f} late={late_avg:.2f}")

        animate_spec = {
            "size": "160x90",
            "fps": 10,
            "scenes": [
                {
                    "type": "layered",
                    "duration": 1.5,
                    "background": "#000000",
                    "audio": {"type": "silence"},
                    "layers": [
                        {
                            "type": "panel",
                            "x": 32,
                            "y": 24,
                            "width": 96,
                            "height": 42,
                            "panel_color": "#00d8ff",
                            "radius": 8,
                            "animate": {"in": "slide_up", "out": "fade", "duration": 0.35, "distance": 18},
                        }
                    ],
                }
            ],
        }
        animate_path = tmpdir / "animate.json"
        animate_video = tmpdir / "animate.mp4"
        write_json(animate_path, animate_spec)
        run([wrapper_path("vidkit"), "--validate-only", str(animate_path)])
        run([wrapper_path("vidkit"), str(animate_path), str(animate_video)])
        animate_start = average_frame(animate_video, 0.0)
        animate_mid = average_frame(animate_video, 0.8)
        if not (animate_start < 5 and animate_mid > 20):
            raise SystemExit(f"animation preset selftest failed: start={animate_start:.2f} mid={animate_mid:.2f}")

        shapes_spec = {
            "size": "180x120",
            "fps": 10,
            "scenes": [
                {
                    "type": "layered",
                    "duration": 1.0,
                    "background": "#08111f",
                    "audio": {"type": "silence"},
                    "layers": [
                        {"type": "shape", "shape": "progress_bar", "x": 12, "y": 16, "width": 110, "height": 14, "value": 0.6, "fill": "#22c55e"},
                        {"type": "shape", "shape": "checkbox", "x": 136, "y": 10, "size": 24, "checked": True, "color": "#22c55e"},
                        {"type": "preset", "preset": "warning_banner", "x": 12, "y": 72, "width": 156, "height": 32, "text": "shape preset"},
                    ],
                }
            ],
        }
        shapes_path = tmpdir / "shapes.json"
        shapes_video = tmpdir / "shapes.mp4"
        write_json(shapes_path, shapes_spec)
        run([wrapper_path("vidkit"), "--validate-only", str(shapes_path)])
        run([wrapper_path("vidkit"), str(shapes_path), str(shapes_video)])
        shapes_avg = average_frame(shapes_video, 0.5)
        if shapes_avg < 20:
            raise SystemExit(f"shape/preset render selftest failed: avg={shapes_avg:.2f}")

        invalid_text = {
            "size": "160x90",
            "scenes": [{"type": "layered", "duration": 1, "layers": [{"type": "text", "text": "bad", "keyframes": [{"time": 0, "opacity": 0}]}]}],
        }
        invalid_text_path = tmpdir / "invalid-text.json"
        write_json(invalid_text_path, invalid_text)
        failed = run([wrapper_path("vidkit"), "--validate-only", str(invalid_text_path)], check=False)
        if failed.returncode == 0 or "keyframes are not supported" not in (failed.stdout + failed.stderr):
            raise SystemExit("invalid text keyframe selftest failed")

        invalid_animate = {
            "size": "160x90",
            "scenes": [{"type": "layered", "duration": 1, "layers": [{"type": "panel", "animate": "teleport"}]}],
        }
        invalid_animate_path = tmpdir / "invalid-animate.json"
        write_json(invalid_animate_path, invalid_animate)
        failed = run([wrapper_path("vidkit"), "--validate-only", str(invalid_animate_path)], check=False)
        if failed.returncode == 0 or "unsupported preset" not in (failed.stdout + failed.stderr):
            raise SystemExit("invalid animate preset selftest failed")

        invalid_panel_pop = {
            "size": "160x90",
            "scenes": [{"type": "layered", "duration": 1, "layers": [{"type": "panel", "animate": "pop"}]}],
        }
        invalid_panel_pop_path = tmpdir / "invalid-panel-pop.json"
        write_json(invalid_panel_pop_path, invalid_panel_pop)
        failed = run([wrapper_path("vidkit"), "--validate-only", str(invalid_panel_pop_path)], check=False)
        if failed.returncode == 0 or "media layers" not in (failed.stdout + failed.stderr):
            raise SystemExit("invalid panel pop selftest failed")

        invalid_shape = {
            "size": "160x90",
            "scenes": [{"type": "layered", "duration": 1, "layers": [{"type": "shape", "shape": "spinner"}]}],
        }
        invalid_shape_path = tmpdir / "invalid-shape.json"
        write_json(invalid_shape_path, invalid_shape)
        failed = run([wrapper_path("vidkit"), "--validate-only", str(invalid_shape_path)], check=False)
        if failed.returncode == 0 or "unsupported shape" not in (failed.stdout + failed.stderr):
            raise SystemExit("invalid shape selftest failed")

        invalid_preset = {
            "size": "160x90",
            "scenes": [{"type": "layered", "duration": 1, "layers": [{"type": "preset", "preset": "warning_banner"}]}],
        }
        invalid_preset_path = tmpdir / "invalid-preset.json"
        write_json(invalid_preset_path, invalid_preset)
        failed = run([wrapper_path("vidkit"), "--validate-only", str(invalid_preset_path)], check=False)
        if failed.returncode == 0 or "text is required" not in (failed.stdout + failed.stderr):
            raise SystemExit("invalid preset selftest failed")

    print("selftest passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
