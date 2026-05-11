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


def audio_stream_count(video: Path) -> int:
    out = subprocess.check_output([
        bin_path("ffprobe"),
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=index",
        "-of",
        "csv=p=0",
        str(video),
    ], text=True)
    return len([line for line in out.splitlines() if line.strip()])


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="vidkit-selftest-") as tmp:
        tmpdir = Path(tmp)

        templates = run([wrapper_path("vidkit"), "templates"]).stdout.splitlines()
        if "media-card" not in templates or "split-screen" not in templates or "chat-window" not in templates or "application-form" not in templates:
            raise SystemExit(f"template list selftest failed: {templates}")
        initialized = tmpdir / "initialized.json"
        run([wrapper_path("vidkit"), "init", "media-card", str(initialized)])
        run([wrapper_path("vidkit"), "--validate-only", str(initialized)])
        shown = run([wrapper_path("vidkit"), "show", "template:media-card"]).stdout
        if "examples/assets/sample.ppm" not in shown:
            raise SystemExit("template show selftest failed: expected portable sample asset path")
        chat_shown = run([wrapper_path("vidkit"), "show", "template:chat-window"]).stdout
        if "team-chat" not in chat_shown:
            raise SystemExit("new template show selftest failed")
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

        camera_sprite_example = ROOT / "examples" / "vidkit.camera-sprite-example.json"
        camera_sprite_video = tmpdir / "camera-sprite.mp4"
        run([wrapper_path("vidkit"), "--validate-only", str(camera_sprite_example)])
        run([wrapper_path("vidkit"), str(camera_sprite_example), str(camera_sprite_video)])
        camera_sprite_avg = average_frame(camera_sprite_video, 2.8)
        if camera_sprite_avg < 15:
            raise SystemExit(f"camera/sprite example selftest failed: avg={camera_sprite_avg:.2f}")

        sprite_path_example = ROOT / "examples" / "vidkit.sprite-path-example.json"
        sprite_path_video = tmpdir / "sprite-path.mp4"
        run([wrapper_path("vidkit"), "--validate-only", str(sprite_path_example)])
        run([wrapper_path("vidkit"), str(sprite_path_example), str(sprite_path_video)])
        sprite_path_avg = average_frame(sprite_path_video, 1.7)
        if sprite_path_avg < 25:
            raise SystemExit(f"sprite path example selftest failed: avg={sprite_path_avg:.2f}")

        invalid_sprite_source = {
            "size": "160x90",
            "scenes": [{"type": "layered", "duration": 1, "layers": [{"type": "sprite"}]}],
        }
        invalid_sprite_source_path = tmpdir / "invalid-sprite-source.json"
        write_json(invalid_sprite_source_path, invalid_sprite_source)
        failed = run([wrapper_path("vidkit"), "--validate-only", str(invalid_sprite_source_path)], check=False)
        if failed.returncode == 0 or "source is required for sprite layers" not in (failed.stdout + failed.stderr):
            raise SystemExit("invalid sprite source selftest failed")

        missing_sprite_file = {
            "size": "160x90",
            "scenes": [{"type": "layered", "duration": 1, "layers": [{"type": "sprite", "source": "examples/assets/not-here.png"}]}],
        }
        missing_sprite_file_path = tmpdir / "missing-sprite-file.json"
        write_json(missing_sprite_file_path, missing_sprite_file)
        failed = run([wrapper_path("vidkit"), "--validate-only", str(missing_sprite_file_path)], check=False)
        if failed.returncode == 0 or "source not found" not in (failed.stdout + failed.stderr):
            raise SystemExit("missing sprite file selftest failed")

        invalid_sprite_path = {
            "size": "160x90",
            "scenes": [
                {
                    "type": "layered",
                    "duration": 1,
                    "layers": [
                        {
                            "type": "sprite",
                            "source": "examples/assets/sample.ppm",
                            "path": {"type": "curve", "points": [{"time": 0, "x": 0, "y": 0}]},
                        }
                    ],
                }
            ],
        }
        invalid_sprite_path_path = tmpdir / "invalid-sprite-path.json"
        write_json(invalid_sprite_path_path, invalid_sprite_path)
        failed = run([wrapper_path("vidkit"), "--validate-only", str(invalid_sprite_path_path)], check=False)
        if failed.returncode == 0 or "unsupported path type" not in (failed.stdout + failed.stderr):
            raise SystemExit("invalid sprite path type selftest failed")

        invalid_sprite_points = {
            "size": "160x90",
            "scenes": [
                {
                    "type": "layered",
                    "duration": 1,
                    "layers": [
                        {
                            "type": "sprite",
                            "source": "examples/assets/sample.ppm",
                            "path": {"type": "points", "points": [{"time": 1.2, "x": 0}]},
                        }
                    ],
                }
            ],
        }
        invalid_sprite_points_path = tmpdir / "invalid-sprite-points.json"
        write_json(invalid_sprite_points_path, invalid_sprite_points)
        failed = run([wrapper_path("vidkit"), "--validate-only", str(invalid_sprite_points_path)], check=False)
        combined = failed.stdout + failed.stderr
        if failed.returncode == 0 or "path.points[0].y is required" not in combined or "outside scene duration" not in combined:
            raise SystemExit("invalid sprite path points selftest failed")

        invalid_sprite = {
            "size": "160x90",
            "scenes": [{"type": "layered", "duration": 1, "layers": [{"type": "media", "source": "examples/assets/sample.ppm", "sprite_animate": "teleport"}]}],
        }
        invalid_sprite_path = tmpdir / "invalid-sprite.json"
        write_json(invalid_sprite_path, invalid_sprite)
        failed = run([wrapper_path("vidkit"), "--validate-only", str(invalid_sprite_path)], check=False)
        if failed.returncode == 0 or "unsupported sprite animation preset" not in (failed.stdout + failed.stderr):
            raise SystemExit("invalid sprite animation selftest failed")

        invalid_camera = {
            "size": "160x90",
            "scenes": [{"type": "layered", "duration": 1, "camera": {"keyframes": [{"time": 0, "scale": 1}, {"time": 1.2, "scale": 1.1}]}, "layers": [{"type": "panel"}]}],
        }
        invalid_camera_path = tmpdir / "invalid-camera.json"
        write_json(invalid_camera_path, invalid_camera)
        failed = run([wrapper_path("vidkit"), "--validate-only", str(invalid_camera_path)], check=False)
        if failed.returncode == 0 or "outside scene duration" not in (failed.stdout + failed.stderr):
            raise SystemExit("invalid camera keyframe selftest failed")

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

        sfx_example = ROOT / "examples" / "vidkit.sfx-example.json"
        sfx_video = tmpdir / "sfx.mp4"
        run([wrapper_path("vidkit"), "--validate-only", str(sfx_example)])
        run([wrapper_path("vidkit"), str(sfx_example), str(sfx_video)])
        if audio_stream_count(sfx_video) < 1:
            raise SystemExit("sfx example selftest failed: expected audio stream")

        beats_example = ROOT / "examples" / "vidkit.comedy-beats-example.json"
        beats_video = tmpdir / "beats.mp4"
        run([wrapper_path("vidkit"), "--validate-only", str(beats_example)])
        run([wrapper_path("vidkit"), str(beats_example), str(beats_video)])
        if audio_stream_count(beats_video) < 1:
            raise SystemExit("beat example selftest failed: expected audio stream")

        invalid_beat_preset = {
            "size": "160x90",
            "scenes": [{"type": "beat", "duration": 0.5, "preset": "rimshot"}],
        }
        invalid_beat_preset_path = tmpdir / "invalid-beat-preset.json"
        write_json(invalid_beat_preset_path, invalid_beat_preset)
        failed = run([wrapper_path("vidkit"), "--validate-only", str(invalid_beat_preset_path)], check=False)
        if failed.returncode == 0 or "unsupported beat preset" not in (failed.stdout + failed.stderr):
            raise SystemExit("invalid beat preset selftest failed")

        invalid_beat_field = {
            "size": "160x90",
            "scenes": [{"type": "beat", "duration": 0.5, "preset": "bonk", "storyboard": []}],
        }
        invalid_beat_field_path = tmpdir / "invalid-beat-field.json"
        write_json(invalid_beat_field_path, invalid_beat_field)
        failed = run([wrapper_path("vidkit"), "--validate-only", str(invalid_beat_field_path)], check=False)
        if failed.returncode == 0 or "unsupported beat option" not in (failed.stdout + failed.stderr):
            raise SystemExit("invalid beat option selftest failed")

        invalid_sfx = {
            "size": "160x90",
            "scenes": [{"type": "card", "duration": 0.5, "audio": {"type": "sfx", "preset": "airhorn"}}],
        }
        invalid_sfx_path = tmpdir / "invalid-sfx.json"
        write_json(invalid_sfx_path, invalid_sfx)
        failed = run([wrapper_path("vidkit"), "--validate-only", str(invalid_sfx_path)], check=False)
        if failed.returncode == 0 or "unsupported sfx preset" not in (failed.stdout + failed.stderr):
            raise SystemExit("invalid sfx preset selftest failed")

        qa_dir = tmpdir / "qa"
        run([wrapper_path("vidkit"), "qa", str(sfx_video), "--out", str(qa_dir), "--frames", "2"])
        expected_qa = ["probe.json", "contact.jpg", "frame-01.jpg", "frame-02.jpg", "audio-levels.txt", "summary.json"]
        missing = [name for name in expected_qa if not (qa_dir / name).exists()]
        if missing:
            raise SystemExit(f"qa selftest failed: missing {missing}")
        summary = json.loads((qa_dir / "summary.json").read_text(encoding="utf-8"))
        if summary.get("audio_status") != "audible" or summary.get("effectively_silent"):
            raise SystemExit(f"qa selftest failed: unexpected audio summary {summary}")

        silent_spec = {
            "size": "160x90",
            "fps": 10,
            "scenes": [{"type": "card", "duration": 0.5, "title": "quiet", "audio": {"type": "silence"}}],
        }
        silent_path = tmpdir / "silent.json"
        silent_video = tmpdir / "silent.mp4"
        silent_qa = tmpdir / "silent-qa"
        write_json(silent_path, silent_spec)
        run([wrapper_path("vidkit"), str(silent_path), str(silent_video)])
        run([wrapper_path("vidkit"), "qa", str(silent_video), "--out", str(silent_qa), "--frames", "1"])
        silent_summary = json.loads((silent_qa / "summary.json").read_text(encoding="utf-8"))
        if silent_summary.get("audio_status") != "effectively_silent" or not silent_summary.get("effectively_silent"):
            raise SystemExit(f"qa silent selftest failed: unexpected audio summary {silent_summary}")

    print("selftest passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
