#!/usr/bin/env python3
"""Small original video scene composer.

This is intentionally general: it renders simple scenes from a JSON spec using
Python-generated pixels plus ffmpeg assembly. Styles/presets should sit on top.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import subprocess
import sys
import textwrap
import tempfile
from pathlib import Path
from typing import Any


SCENE_TYPES = {"card", "bars", "particles", "wave", "grid", "orbits", "typewriter", "image", "media", "layered"}
LAYER_TYPES = {"media", "panel", "text", "lower_third", "shape", "preset"}
SHAPE_NAMES = {"progress_bar", "checkbox", "arrow", "cursor", "speech_bubble", "file_icon", "window"}
PRESET_NAMES = {"error_dialog", "stamp", "meme_caption", "file_label", "terminal_prompt", "form_field", "warning_banner"}
AUDIO_TYPES = {"none", "silence", "tone", "noise", "pulse", "sfx"}
SFX_PRESETS = {"bonk", "error_beep", "whoosh", "censor_beep", "printer_panic", "meow_ish"}
FIT_TYPES = {"contain", "cover", "stretch"}
CAMERA_TYPES = {"none", "zoom_in", "zoom_out", "pan", "shake"}
TRANSITION_TYPES = {"fade", "wipeleft", "wiperight", "slideleft", "slideright", "circleopen", "circleclose", "none"}
EASING_TYPES = {"linear", "none", "in_quad", "ease_in", "out_quad", "ease_out", "in_out_quad", "in_cubic", "out_cubic", "in_out_cubic"}
ANIMATION_PRESETS = {"fade", "fade_in", "fade_out", "slide_left", "slide_right", "slide_up", "slide_down", "pop", "none"}
TEMPLATE_NAMES = ("lower-third", "motion-card", "glitch-card", "band-glitch", "media-card", "split-screen")


def ffmpeg_bin(name: str | None = None) -> str:
    return name or shutil.which("ffmpeg") or str(Path.home() / ".local/bin/ffmpeg")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def bundled_asset(name: str) -> str:
    return str(repo_root() / "examples" / "assets" / name)


def ensure_tool(path: str, label: str = "ffmpeg") -> str:
    if shutil.which(path) or Path(path).exists():
        return path
    raise SystemExit(f"{label} not found: {path}")


def run(cmd: list[str], *, input_bytes: bytes | None = None) -> None:
    subprocess.run(cmd, input=input_bytes, check=True)


def parse_hex(color: str) -> tuple[int, int, int]:
    color = color.strip()
    named = {
        "black": "#000000",
        "white": "#ffffff",
        "red": "#ff3030",
        "green": "#00ff66",
        "blue": "#2090ff",
        "cyan": "#00d8ff",
        "magenta": "#ff4fd8",
        "purple": "#7c3cff",
    }
    color = named.get(color.lower(), color)
    if not color.startswith("#") or len(color) != 7:
        raise ValueError(f"unsupported color: {color}")
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


def blend(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)


def ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def ass_escape(text: str) -> str:
    return str(text).replace("{", "(").replace("}", ")").replace("\n", r"\N")


def wrap_text(text: str, chars: int | None = None) -> str:
    if not chars or chars <= 0:
        return text
    return "\n".join(textwrap.fill(line, width=chars) for line in str(text).splitlines())


def ass_color(value: str) -> str:
    value = str(value)
    names = {
        "white": "&HFFFFFF&",
        "black": "&H000000&",
        "cyan": "&HFFD800&",
        "magenta": "&HD84FFF&",
        "green": "&H66FF00&",
        "red": "&H3030FF&",
    }
    if value.lower() in names:
        return names[value.lower()]
    if value.startswith("#") and len(value) == 7:
        r = int(value[1:3], 16)
        g = int(value[3:5], 16)
        b = int(value[5:7], 16)
        return f"&H{b:02X}{g:02X}{r:02X}&"
    if value.startswith("&H") and not value.endswith("&"):
        return value + "&"
    return value


def ass_alpha(opacity: Any) -> str:
    value = max(0.0, min(1.0, float(opacity)))
    return f"&H{int(round((1.0 - value) * 255)):02X}&"


def esc_filter_path(path: Path) -> str:
    return str(path).replace("\\", r"\\").replace(":", r"\:").replace("'", r"\'")


def ffmpeg_color(value: str) -> str:
    value = str(value)
    if value.startswith("#") and len(value) == 7:
        return "0x" + value[1:]
    return value


def ffexpr(value: str) -> str:
    """Escape an ffmpeg expression for use inside a filter option."""
    return str(value).replace("\\", r"\\").replace(",", r"\,")


def rounded_rect_alpha_expr(width: int, height: int, radius: int) -> str:
    """Return a geq alpha expression for a rounded rectangle mask."""
    radius = max(0, min(int(radius), width // 2, height // 2))
    if radius <= 0:
        return "255"
    # Inside the straight center bands is opaque. In corners, test distance
    # from the corner circle centers. geq uses commas for function args, so
    # callers must quote this expression inside the filter graph.
    r = radius
    right = width - radius - 1
    bottom = height - radius - 1
    return (
        f"if(gte(X,{r})*lte(X,{right})+gte(Y,{r})*lte(Y,{bottom}),255,"
        f"if(lte((X-if(lt(X,{r}),{r},{right}))*(X-if(lt(X,{r}),{r},{right}))+"
        f"(Y-if(lt(Y,{r}),{r},{bottom}))*(Y-if(lt(Y,{r}),{r},{bottom})),{r*r}),255,0))"
    )


def apply_rounded_mask(filters: list[str], source_label: str, out_label: str, *, width: int, height: int, radius: int, fps: int, duration: float) -> None:
    if radius <= 0:
        filters.append(f"[{source_label}]format=rgba[{out_label}]")
        return
    mask_label = f"{out_label}mask"
    fmt_label = f"{out_label}fmt"
    expr = rounded_rect_alpha_expr(width, height, radius)
    filters.append(f"color=c=white:s={width}x{height}:r={fps}:d={duration},format=gray,geq=lum='{expr}'[{mask_label}]")
    filters.append(f"[{source_label}]format=rgba[{fmt_label}]")
    filters.append(f"[{fmt_label}][{mask_label}]alphamerge[{out_label}]")


def scene_duration(scene: dict[str, Any]) -> float:
    return float(scene.get("duration", 2.0))


def audio_source(scene: dict[str, Any], duration: float) -> str:
    audio = scene.get("audio") or {"type": "silence"}
    kind = audio.get("type", "silence")
    if kind in ("none", "silence"):
        return "anullsrc=channel_layout=mono:sample_rate=44100"
    if kind == "tone":
        frequency = float(audio.get("frequency", 220))
        volume = float(audio.get("volume", 0.08))
        return f"sine=frequency={frequency}:sample_rate=44100,volume={volume}"
    if kind == "noise":
        color = audio.get("color", "pink")
        amplitude = float(audio.get("amplitude", audio.get("volume", 0.025)))
        return f"anoisesrc=color={color}:amplitude={amplitude}:sample_rate=44100"
    if kind == "pulse":
        frequency = float(audio.get("frequency", 440))
        volume = float(audio.get("volume", 0.08))
        period = float(audio.get("period", 0.5))
        duty = float(audio.get("duty", 0.16))
        return f"sine=frequency={frequency}:sample_rate=44100,volume='{volume}*lt(mod(t,{period}),{duty})'"
    if kind == "sfx":
        return sfx_source(audio, duration)
    raise SystemExit(f"unknown audio type: {kind}")


def sfx_source(audio: dict[str, Any], duration: float) -> str:
    preset = str(audio.get("preset", "bonk"))
    volume = float(audio.get("volume", 1.0))
    dur = max(0.08, float(audio.get("duration", duration)))
    if preset == "bonk":
        peak = 0.42 * volume
        return f"sine=frequency=155:sample_rate=44100,volume='if(isnan(t),{peak},{peak}*exp(-10*t))':eval=frame,afade=t=out:st={max(0.04, dur - 0.18)}:d=0.18"
    if preset == "error_beep":
        return f"sine=frequency=880:sample_rate=44100,volume='{0.22 * volume}*(between(t,0,0.16)+between(t,0.26,0.42)+between(t,0.52,0.68))':eval=frame"
    if preset == "whoosh":
        return f"anoisesrc=color=pink:amplitude={0.20 * volume}:sample_rate=44100,highpass=f=260,lowpass=f=4200,afade=t=in:st=0:d={min(0.22, dur / 3)},afade=t=out:st={max(0.03, dur - 0.28)}:d=0.28"
    if preset == "censor_beep":
        return f"sine=frequency=1000:sample_rate=44100,volume={0.18 * volume},afade=t=in:st=0:d=0.015,afade=t=out:st={max(0.02, dur - 0.04)}:d=0.04"
    if preset == "printer_panic":
        return (
            f"sine=frequency=760:sample_rate=44100,volume='{0.13 * volume}*lt(mod(t,0.11),0.055)':eval=frame[ticks];"
            f"anoisesrc=color=white:amplitude={0.07 * volume}:sample_rate=44100,highpass=f=900,volume='lt(mod(t,0.17),0.035)':eval=frame[grit];"
            "[ticks][grit]amix=inputs=2:duration=longest:normalize=0"
        )
    if preset == "meow_ish":
        return (
            f"sine=frequency=520:sample_rate=44100,volume='{0.16 * volume}*between(t,0,0.32)':eval=frame[m1];"
            f"sine=frequency=690:sample_rate=44100,volume='{0.13 * volume}*between(t,0.18,0.52)':eval=frame[m2];"
            "[m1][m2]amix=inputs=2:duration=longest:normalize=0,afade=t=out:st=0.45:d=0.16"
        )
    raise SystemExit(f"unknown sfx preset: {preset}")


def fit_filter(width: int, height: int, fit: str, background: str = "black") -> str:
    if fit == "cover":
        return f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,crop={width}:{height},setsar=1"
    if fit == "stretch":
        return f"scale={width}:{height}:flags=lanczos,setsar=1"
    return f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={background},setsar=1"


def media_source_args(source: Path, duration: float, fps: int, mode: str) -> list[str]:
    if mode == "image":
        return ["-loop", "1", "-t", str(duration), "-i", str(source)]
    if mode == "video":
        return ["-stream_loop", "-1", "-t", str(duration), "-i", str(source)]
    suffix = source.suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".ppm", ".pgm"}:
        return ["-loop", "1", "-t", str(duration), "-i", str(source)]
    return ["-stream_loop", "-1", "-t", str(duration), "-i", str(source)]


def glitch_filter(effect: dict[str, Any] | bool) -> str:
    if not effect:
        return ""
    if effect is True:
        effect = {"amount": 1.0}
    amount = float(effect.get("amount", 1.0))
    noise = int(effect.get("noise", 18) * amount)
    hue = float(effect.get("hue", 10.0) * amount)
    contrast = float(effect.get("contrast", 1.18))
    filters = [f"noise=alls={noise}:allf=t+u", f"hue=h={hue}*sin(2*PI*t)", f"eq=contrast={contrast}:saturation=1.25"]
    return ",".join(filters)


def ease_expr(name: str, p: str) -> str:
    if name in ("linear", "none"):
        return p
    if name in ("in_quad", "ease_in"):
        return f"({p})*({p})"
    if name in ("out_quad", "ease_out"):
        return f"1-(1-({p}))*(1-({p}))"
    if name == "in_out_quad":
        return f"if(lt(({p}),0.5),2*({p})*({p}),1-pow(-2*({p})+2,2)/2)"
    if name == "in_cubic":
        return f"({p})*({p})*({p})"
    if name == "out_cubic":
        return f"1-pow(1-({p}),3)"
    if name == "in_out_cubic":
        return f"if(lt(({p}),0.5),4*({p})*({p})*({p}),1-pow(-2*({p})+2,3)/2)"
    raise SystemExit(f"unsupported easing: {name}")


def ease_value(name: str, p: float) -> float:
    p = max(0.0, min(1.0, p))
    if name in ("linear", "none"):
        return p
    if name in ("in_quad", "ease_in"):
        return p * p
    if name in ("out_quad", "ease_out"):
        return 1 - (1 - p) * (1 - p)
    if name == "in_out_quad":
        return 2 * p * p if p < 0.5 else 1 - ((-2 * p + 2) ** 2) / 2
    if name == "in_cubic":
        return p * p * p
    if name == "out_cubic":
        return 1 - ((1 - p) ** 3)
    if name == "in_out_cubic":
        return 4 * p * p * p if p < 0.5 else 1 - ((-2 * p + 2) ** 3) / 2
    raise SystemExit(f"unsupported easing: {name}")


def keyframed_expr(layer: dict[str, Any], prop: str, default: float | int, duration: float) -> str:
    keyframes = sorted(layer.get("keyframes") or [], key=lambda item: float(item.get("time", 0)))
    points = [(float(kf["time"]), float(kf[prop]), kf.get("ease", "linear")) for kf in keyframes if prop in kf]
    if not points:
        return str(default)
    if len(points) == 1:
        return str(points[0][1])
    for time_value, _, _ in points:
        if time_value < 0 or time_value > duration:
            raise SystemExit(f"keyframe for {prop} outside scene duration: {time_value}")
    expr = str(points[-1][1])
    for idx in range(len(points) - 2, -1, -1):
        t0, v0, _ = points[idx]
        t1, v1, ease = points[idx + 1]
        if t1 <= t0:
            raise SystemExit(f"keyframes for {prop} must have increasing times")
        p = f"clip((t-{t0})/{t1 - t0},0,1)"
        eased = ease_expr(ease, p)
        value = f"{v0}+({v1}-{v0})*({eased})"
        expr = f"if(lt(t,{t0}),{v0},if(lte(t,{t1}),{value},{expr}))"
    return expr


def has_keyframed_prop(layer: dict[str, Any], prop: str) -> bool:
    return any(prop in keyframe for keyframe in (layer.get("keyframes") or []))


def keyframed_value(layer: dict[str, Any], prop: str, default: float | int, t: float, duration: float) -> float:
    keyframes = sorted(layer.get("keyframes") or [], key=lambda item: float(item.get("time", 0)))
    points = [(float(kf["time"]), float(kf[prop]), kf.get("ease", "linear")) for kf in keyframes if prop in kf]
    if not points:
        return float(default)
    if len(points) == 1 or t <= points[0][0]:
        return float(points[0][1])
    if t >= points[-1][0]:
        return float(points[-1][1])
    for idx in range(len(points) - 1):
        t0, v0, _ = points[idx]
        t1, v1, ease = points[idx + 1]
        if t0 <= t <= t1:
            progress = (t - t0) / max(0.000001, t1 - t0)
            eased = ease_value(ease, progress)
            return v0 + (v1 - v0) * eased
    return float(points[-1][1])


def rounded_rect_mask(width: int, height: int, radius: int) -> bytes:
    radius = max(0, min(int(radius), width // 2, height // 2))
    if radius <= 0:
        return bytes([255]) * (width * height)
    right = width - radius - 1
    bottom = height - radius - 1
    rr = radius * radius
    mask = bytearray(width * height)
    for y in range(height):
        cy = radius if y < radius else bottom if y > bottom else y
        for x in range(width):
            cx = radius if x < radius else right if x > right else x
            if (x - cx) * (x - cx) + (y - cy) * (y - cy) <= rr:
                mask[y * width + x] = 255
    return bytes(mask)


def write_opacity_mask(path: Path, layer: dict[str, Any], *, width: int, height: int, radius: int, duration: float, fps: int) -> None:
    base = rounded_rect_mask(width, height, radius)
    frames = max(1, int(math.ceil(duration * fps)))
    default = float(layer.get("opacity", 1.0))
    with path.open("wb") as fh:
        for frame in range(frames):
            t = min(duration, frame / fps)
            opacity = max(0.0, min(1.0, keyframed_value(layer, "opacity", default, t, duration)))
            if opacity >= 0.999:
                fh.write(base)
            elif opacity <= 0.001:
                fh.write(bytes(len(base)))
            else:
                fh.write(bytes(int(pixel * opacity) for pixel in base))


def animation_config(layer: dict[str, Any]) -> dict[str, Any] | None:
    animate = layer.get("animate")
    if not animate:
        return None
    if isinstance(animate, str):
        if animate in ("none", "off"):
            return None
        if animate == "fade_out":
            return {"out": "fade"}
        if animate == "fade_in":
            return {"in": "fade"}
        return {"in": animate}
    if isinstance(animate, dict):
        return animate
    raise SystemExit("animate must be a string or object")


def add_keyframe_value(frames: list[dict[str, Any]], time_value: float, prop: str, value: float, ease: str | None = None) -> None:
    for frame in frames:
        if abs(float(frame.get("time", -9999)) - time_value) < 0.000001:
            frame[prop] = value
            if ease:
                frame.setdefault("ease", ease)
            return
    frame = {"time": time_value, prop: value}
    if ease:
        frame["ease"] = ease
    frames.append(frame)


def apply_animation_presets(layer: dict[str, Any], *, duration: float, w: int, h: int) -> dict[str, Any]:
    config = animation_config(layer)
    if not config:
        return layer

    out = dict(layer)
    frames = [dict(frame) for frame in (layer.get("keyframes") or [])]
    explicit_props = {key for frame in frames for key in frame if key in {"x", "y", "opacity", "scale"}}

    box_w = int(layer.get("width", w))
    box_h = int(layer.get("height", h))
    base_x = float(layer.get("x", (w - box_w) / 2))
    base_y = float(layer.get("y", (h - box_h) / 2))
    base_opacity = float(layer.get("opacity", 1.0))
    base_scale = float(layer.get("scale", 1.0))
    in_duration = min(duration, max(0.0, float(config.get("duration", config.get("in_duration", 0.5)))))
    out_duration = min(duration, max(0.0, float(config.get("out_duration", config.get("duration", 0.5)))))
    distance = float(config.get("distance", 48))
    in_ease = config.get("ease", config.get("in_ease", "out_cubic"))
    out_ease = config.get("out_ease", "in_cubic")

    def apply_in(preset: str) -> None:
        if preset in ("none", "off") or in_duration <= 0:
            return
        if preset not in ANIMATION_PRESETS:
            raise SystemExit(f"unsupported animation preset: {preset}")
        if preset in {"fade", "fade_in", "slide_left", "slide_right", "slide_up", "slide_down", "pop"} and "opacity" not in explicit_props:
            add_keyframe_value(frames, 0.0, "opacity", 0.0)
            add_keyframe_value(frames, in_duration, "opacity", base_opacity, in_ease)
        if preset == "slide_left" and "x" not in explicit_props:
            add_keyframe_value(frames, 0.0, "x", base_x - distance)
            add_keyframe_value(frames, in_duration, "x", base_x, in_ease)
        elif preset == "slide_right" and "x" not in explicit_props:
            add_keyframe_value(frames, 0.0, "x", base_x + distance)
            add_keyframe_value(frames, in_duration, "x", base_x, in_ease)
        elif preset == "slide_up" and "y" not in explicit_props:
            add_keyframe_value(frames, 0.0, "y", base_y - distance)
            add_keyframe_value(frames, in_duration, "y", base_y, in_ease)
        elif preset == "slide_down" and "y" not in explicit_props:
            add_keyframe_value(frames, 0.0, "y", base_y + distance)
            add_keyframe_value(frames, in_duration, "y", base_y, in_ease)
        elif preset == "pop" and "scale" not in explicit_props:
            add_keyframe_value(frames, 0.0, "scale", base_scale * 0.85)
            add_keyframe_value(frames, in_duration, "scale", base_scale, in_ease)

    def apply_out(preset: str) -> None:
        if preset in ("none", "off") or out_duration <= 0:
            return
        if preset not in ANIMATION_PRESETS:
            raise SystemExit(f"unsupported animation preset: {preset}")
        start = max(0.0, duration - out_duration)
        if preset in {"fade", "fade_out", "slide_left", "slide_right", "slide_up", "slide_down", "pop"} and "opacity" not in explicit_props:
            add_keyframe_value(frames, start, "opacity", base_opacity)
            add_keyframe_value(frames, duration, "opacity", 0.0, out_ease)
        if preset == "slide_left" and "x" not in explicit_props:
            add_keyframe_value(frames, start, "x", base_x)
            add_keyframe_value(frames, duration, "x", base_x - distance, out_ease)
        elif preset == "slide_right" and "x" not in explicit_props:
            add_keyframe_value(frames, start, "x", base_x)
            add_keyframe_value(frames, duration, "x", base_x + distance, out_ease)
        elif preset == "slide_up" and "y" not in explicit_props:
            add_keyframe_value(frames, start, "y", base_y)
            add_keyframe_value(frames, duration, "y", base_y - distance, out_ease)
        elif preset == "slide_down" and "y" not in explicit_props:
            add_keyframe_value(frames, start, "y", base_y)
            add_keyframe_value(frames, duration, "y", base_y + distance, out_ease)
        elif preset == "pop" and "scale" not in explicit_props:
            add_keyframe_value(frames, start, "scale", base_scale)
            add_keyframe_value(frames, duration, "scale", base_scale * 0.9, out_ease)

    in_preset = config.get("in", config.get("type"))
    if in_preset is None and not config.get("out"):
        in_preset = "fade"
    if in_preset is not None:
        apply_in(str(in_preset))
    if config.get("out"):
        apply_out(str(config["out"]))
    out["keyframes"] = sorted(frames, key=lambda frame: float(frame.get("time", 0)))
    return out


def layer_start_end(layer: dict[str, Any], duration: float) -> tuple[float, float]:
    return float(layer.get("start", 0)), float(layer.get("end", duration))


def offset_keyframes(layer: dict[str, Any], dx: float, dy: float) -> list[dict[str, Any]]:
    frames = []
    for keyframe in layer.get("keyframes") or []:
        frame = dict(keyframe)
        if "x" in frame:
            frame["x"] = float(frame["x"]) + dx
        if "y" in frame:
            frame["y"] = float(frame["y"]) + dy
        frames.append(frame)
    return frames


def expanded_common(layer: dict[str, Any], *, x: float, y: float, duration: float) -> dict[str, Any]:
    start, end = layer_start_end(layer, duration)
    out: dict[str, Any] = {"x": x, "y": y, "start": start, "end": end}
    if "opacity" in layer:
        out["opacity"] = layer["opacity"]
    if layer.get("animate"):
        out["animate"] = layer["animate"]
    if layer.get("keyframes"):
        out["keyframes"] = offset_keyframes(layer, x - float(layer.get("x", 0)), y - float(layer.get("y", 0)))
    return out


def panel_part(layer: dict[str, Any], *, duration: float, x: float, y: float, width: int, height: int, color: str, radius: int = 0, opacity: float | None = None, border: int = 0, border_color: str | None = None) -> dict[str, Any]:
    out = {
        "type": "panel",
        "width": max(1, int(width)),
        "height": max(1, int(height)),
        "panel_color": color,
        "radius": max(0, int(radius)),
        **expanded_common(layer, x=x, y=y, duration=duration),
    }
    if opacity is not None:
        out["opacity"] = opacity
    if border > 0:
        out["border"] = border
        out["border_color"] = border_color or layer.get("border_color", "white")
    return out


def text_part(layer: dict[str, Any], *, duration: float, text: str, x: float, y: float, size: int, color: str = "white", align: int = 5, wrap: int | None = None) -> dict[str, Any]:
    start, end = layer_start_end(layer, duration)
    out: dict[str, Any] = {
        "type": "text",
        "text": text,
        "x": int(x),
        "y": int(y),
        "size": int(size),
        "color": color,
        "align": align,
        "start": start,
        "end": end,
    }
    if "opacity" in layer:
        out["opacity"] = layer["opacity"]
    if wrap:
        out["wrap"] = wrap
    return out


def expand_shape_layer(layer: dict[str, Any], *, duration: float, scene_w: int, scene_h: int) -> list[dict[str, Any]]:
    shape = layer.get("shape") or layer.get("name")
    x = float(layer.get("x", 0))
    y = float(layer.get("y", 0))
    color = layer.get("color", layer.get("panel_color", "#00d8ff"))
    fill = layer.get("fill", color)
    background = layer.get("background", "#111827")
    border_color = layer.get("border_color", color)
    radius = int(layer.get("radius", 8))

    if shape == "progress_bar":
        width = int(layer.get("width", 220))
        height = int(layer.get("height", 18))
        value = max(0.0, min(1.0, float(layer.get("value", layer.get("progress", 0.5)))))
        pad = int(layer.get("pad", max(2, min(6, height // 5))))
        fill_width = max(1, int((width - pad * 2) * value))
        return [
            panel_part(layer, duration=duration, x=x, y=y, width=width, height=height, color=background, radius=radius, border=int(layer.get("border", 1)), border_color=border_color),
            panel_part(layer, duration=duration, x=x + pad, y=y + pad, width=fill_width, height=max(1, height - pad * 2), color=fill, radius=max(0, radius - pad)),
        ]

    if shape == "checkbox":
        size = int(layer.get("size", layer.get("width", layer.get("height", 28))))
        checked = bool(layer.get("checked", True))
        parts = [panel_part(layer, duration=duration, x=x, y=y, width=size, height=size, color=layer.get("background", "#0b1020"), radius=radius, border=int(layer.get("border", 2)), border_color=border_color)]
        if checked:
            parts.append(text_part(layer, duration=duration, text="X", x=x + size / 2, y=y + size / 2 - 2, size=max(14, int(size * 0.72)), color=color))
        return parts

    if shape == "arrow":
        width = int(layer.get("width", 120))
        height = int(layer.get("height", 28))
        thickness = int(layer.get("thickness", max(4, height // 5)))
        direction = layer.get("direction", "right")
        parts: list[dict[str, Any]] = []
        if direction in {"left", "right"}:
            shaft_w = max(1, width - height)
            shaft_x = x + (height if direction == "left" else 0)
            parts.append(panel_part(layer, duration=duration, x=shaft_x, y=y + (height - thickness) / 2, width=shaft_w, height=thickness, color=color, radius=thickness // 2))
            head = "<" if direction == "left" else ">"
            head_x = x + height / 2 if direction == "left" else x + width - height / 2
            parts.append(text_part(layer, duration=duration, text=head, x=head_x, y=y + height / 2 - 1, size=max(18, int(height * 1.25)), color=color))
        else:
            shaft_h = max(1, height - width)
            shaft_y = y + (width if direction == "up" else 0)
            parts.append(panel_part(layer, duration=duration, x=x + (width - thickness) / 2, y=shaft_y, width=thickness, height=shaft_h, color=color, radius=thickness // 2))
            head = "^" if direction == "up" else "v"
            head_y = y + width / 2 if direction == "up" else y + height - width / 2
            parts.append(text_part(layer, duration=duration, text=head, x=x + width / 2, y=head_y - 1, size=max(18, int(width * 1.15)), color=color))
        return parts

    if shape == "cursor":
        width = int(layer.get("width", 34))
        height = int(layer.get("height", 44))
        thickness = max(3, int(layer.get("thickness", width // 5)))
        return [
            panel_part(layer, duration=duration, x=x, y=y, width=thickness, height=height, color=color, radius=1, border=int(layer.get("border", 1)), border_color=layer.get("outline", "#000000")),
            panel_part(layer, duration=duration, x=x, y=y, width=width, height=thickness, color=color, radius=1),
            panel_part(layer, duration=duration, x=x + thickness, y=y + height - thickness, width=max(1, width - thickness), height=thickness, color=color, radius=1),
        ]

    if shape == "speech_bubble":
        width = int(layer.get("width", 240))
        height = int(layer.get("height", 96))
        tail = int(layer.get("tail", 18))
        parts = [panel_part(layer, duration=duration, x=x, y=y, width=width, height=height, color=fill, radius=radius, border=int(layer.get("border", 0)), border_color=border_color)]
        parts.append(panel_part(layer, duration=duration, x=x + int(width * 0.16), y=y + height - 1, width=tail, height=max(8, tail // 2), color=fill, radius=2))
        if layer.get("text"):
            parts.append(text_part(layer, duration=duration, text=wrap_text(layer.get("text", ""), layer.get("wrap", max(10, width // 12))), x=x + 18, y=y + 18, size=int(layer.get("size", 22)), color=layer.get("text_color", "#000000"), align=7))
        return parts

    if shape == "file_icon":
        width = int(layer.get("width", 84))
        height = int(layer.get("height", 108))
        fold = int(layer.get("fold", min(width, height) * 0.22))
        parts = [
            panel_part(layer, duration=duration, x=x, y=y, width=width, height=height, color=fill, radius=radius, border=int(layer.get("border", 2)), border_color=border_color),
            panel_part(layer, duration=duration, x=x + width - fold, y=y, width=fold, height=fold, color=layer.get("fold_color", "#d1d5db"), radius=1),
        ]
        if layer.get("label"):
            parts.append(text_part(layer, duration=duration, text=str(layer["label"]), x=x + width / 2, y=y + height * 0.62, size=int(layer.get("size", 18)), color=layer.get("text_color", "#111827")))
        return parts

    if shape == "window":
        width = int(layer.get("width", 320))
        height = int(layer.get("height", 190))
        chrome = int(layer.get("chrome", 30))
        parts = [
            panel_part(layer, duration=duration, x=x, y=y, width=width, height=height, color=fill, radius=radius, border=int(layer.get("border", 2)), border_color=border_color),
            panel_part(layer, duration=duration, x=x, y=y, width=width, height=chrome, color=layer.get("chrome_color", "#111827"), radius=radius),
        ]
        dot = max(4, chrome // 6)
        for idx, dot_color in enumerate(layer.get("dots", ["#ff5f57", "#febc2e", "#28c840"])):
            parts.append(panel_part(layer, duration=duration, x=x + 12 + idx * (dot * 3), y=y + (chrome - dot) / 2, width=dot, height=dot, color=dot_color, radius=dot))
        if layer.get("title"):
            parts.append(text_part(layer, duration=duration, text=str(layer["title"]), x=x + 48, y=y + chrome / 2 - 2, size=int(layer.get("title_size", 16)), color=layer.get("title_color", "white"), align=4))
        return parts

    raise SystemExit(f"unsupported shape: {shape}")


def expand_preset_layer(layer: dict[str, Any], *, duration: float, scene_w: int, scene_h: int) -> list[dict[str, Any]]:
    preset = layer.get("preset") or layer.get("name")
    x = float(layer.get("x", 0))
    y = float(layer.get("y", 0))
    width = int(layer.get("width", min(520, scene_w - int(x) - 24)))
    height = int(layer.get("height", 96))
    text = str(layer.get("text", layer.get("message", "")))

    if preset == "error_dialog":
        title = layer.get("title", "Error")
        button = layer.get("button", "OK")
        return [
            *expand_shape_layer({**layer, "type": "shape", "shape": "window", "width": width, "height": int(layer.get("height", 190)), "fill": layer.get("fill", "#f8fafc"), "border_color": layer.get("border_color", "#ef4444"), "chrome_color": "#991b1b", "title": title}, duration=duration, scene_w=scene_w, scene_h=scene_h),
            text_part(layer, duration=duration, text=wrap_text(text, layer.get("wrap", 34)), x=x + 28, y=y + 64, size=int(layer.get("size", 24)), color=layer.get("text_color", "#111827"), align=7),
            panel_part(layer, duration=duration, x=x + width - 92, y=y + int(layer.get("height", 190)) - 46, width=64, height=28, color=layer.get("button_color", "#2563eb"), radius=6),
            text_part(layer, duration=duration, text=str(button), x=x + width - 60, y=y + int(layer.get("height", 190)) - 32, size=16, color="white"),
        ]

    if preset == "stamp":
        stamp_text = str(layer.get("text", "APPROVED")).upper()
        return [
            panel_part(layer, duration=duration, x=x, y=y, width=width, height=height, color=layer.get("fill", "#000000"), radius=int(layer.get("radius", 6)), opacity=float(layer.get("fill_opacity", 0.0)), border=int(layer.get("border", 4)), border_color=layer.get("color", "#ef4444")),
            text_part(layer, duration=duration, text=stamp_text, x=x + width / 2, y=y + height / 2 - 2, size=int(layer.get("size", min(44, height * 0.48))), color=layer.get("color", "#ef4444")),
        ]

    if preset == "meme_caption":
        top = layer.get("top")
        bottom = layer.get("bottom", text)
        parts = []
        if top:
            parts.append(text_part(layer, duration=duration, text=str(top).upper(), x=x + width / 2, y=y, size=int(layer.get("size", 40)), color=layer.get("color", "white"), wrap=layer.get("wrap", max(14, width // 18))))
        if bottom:
            parts.append(text_part(layer, duration=duration, text=str(bottom).upper(), x=x + width / 2, y=y + height, size=int(layer.get("size", 40)), color=layer.get("color", "white"), wrap=layer.get("wrap", max(14, width // 18))))
        return parts

    if preset == "file_label":
        icon_w = int(layer.get("icon_width", 72))
        return [
            *expand_shape_layer({**layer, "type": "shape", "shape": "file_icon", "width": icon_w, "height": int(layer.get("icon_height", 88)), "label": layer.get("extension", "TXT")}, duration=duration, scene_w=scene_w, scene_h=scene_h),
            text_part(layer, duration=duration, text=text, x=x + icon_w + 14, y=y + 28, size=int(layer.get("size", 22)), color=layer.get("text_color", "white"), align=7, wrap=layer.get("wrap", 22)),
        ]

    if preset == "terminal_prompt":
        prompt = layer.get("prompt", "$")
        return [
            *expand_shape_layer({**layer, "type": "shape", "shape": "window", "width": width, "height": height, "fill": layer.get("fill", "#020617"), "chrome_color": "#111827", "title": layer.get("title", "terminal")}, duration=duration, scene_w=scene_w, scene_h=scene_h),
            text_part(layer, duration=duration, text=f"{prompt} {text}", x=x + 18, y=y + 48, size=int(layer.get("size", 22)), color=layer.get("text_color", "#22c55e"), align=7, wrap=layer.get("wrap", max(16, width // 12))),
        ]

    if preset == "form_field":
        label = str(layer.get("label", "Field"))
        value = str(layer.get("value", text))
        field_y = y + int(layer.get("label_gap", 28))
        return [
            text_part(layer, duration=duration, text=label, x=x, y=y, size=int(layer.get("label_size", 18)), color=layer.get("label_color", "#cbd5e1"), align=7),
            panel_part(layer, duration=duration, x=x, y=field_y, width=width, height=height, color=layer.get("fill", "#ffffff"), radius=int(layer.get("radius", 8)), border=int(layer.get("border", 2)), border_color=layer.get("border_color", "#94a3b8")),
            text_part(layer, duration=duration, text=value, x=x + 14, y=field_y + height / 2 - 2, size=int(layer.get("size", 22)), color=layer.get("text_color", "#111827"), align=4),
        ]

    if preset == "warning_banner":
        return [
            panel_part(layer, duration=duration, x=x, y=y, width=width, height=height, color=layer.get("fill", "#f59e0b"), radius=int(layer.get("radius", 10)), border=int(layer.get("border", 0)), border_color=layer.get("border_color", "#92400e")),
            text_part(layer, duration=duration, text=wrap_text(text, layer.get("wrap", max(20, width // 14))), x=x + 22, y=y + height / 2 - 2, size=int(layer.get("size", 24)), color=layer.get("text_color", "#111827"), align=4),
        ]

    raise SystemExit(f"unsupported preset: {preset}")


def expand_layers(layers: list[dict[str, Any]], *, duration: float, scene_w: int, scene_h: int) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for layer in layers:
        layer_type = layer.get("type") or ("media" if layer.get("source") else "panel")
        if layer_type == "shape":
            expanded.extend(expand_shape_layer(layer, duration=duration, scene_w=scene_w, scene_h=scene_h))
        elif layer_type == "preset":
            expanded.extend(expand_preset_layer(layer, duration=duration, scene_w=scene_w, scene_h=scene_h))
        else:
            expanded.append(layer)
    return expanded


def scene_transition(scene: dict[str, Any], default: dict[str, Any] | None) -> dict[str, Any] | None:
    transition = scene.get("transition", default)
    if not transition:
        return None
    if isinstance(transition, str):
        transition = {"type": transition}
    kind = transition.get("type", "fade")
    duration = float(transition.get("duration", 0.35))
    if kind == "none" or duration <= 0:
        return None
    allowed = {"fade", "wipeleft", "wiperight", "slideleft", "slideright", "circleopen", "circleclose"}
    if kind not in allowed:
        raise SystemExit(f"unsupported transition: {kind}")
    return {"type": kind, "duration": duration}


def write_ass(width: int, height: int, duration: float, events: list[dict[str, Any]], out: Path) -> None:
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Default,DejaVu Sans,48,&H00FFFFFF,&H00FFFFFF,&H00000000,&H99000000,1,0,0,0,100,100,0,0,1,2,1,5,40,40,40,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for event in events:
        text = ass_escape(event.get("text", ""))
        if not text:
            continue
        start = float(event.get("start", 0))
        end = float(event.get("end", duration))
        x = int(event.get("x", width // 2))
        y = int(event.get("y", height // 2))
        size = int(event.get("size", 48))
        raw_color = str(event.get("color", "&H00FFFFFF&"))
        color = ass_color(raw_color)
        align = int(event.get("align", 5))
        alpha = ass_alpha(event.get("opacity", 1.0))
        dark_text = raw_color.lower() in {"black", "#000000", "#111827", "#020617"}
        outline = float(event.get("outline", 0 if dark_text else 1))
        shadow = float(event.get("shadow", 0))
        outline_color = ass_color(event.get("outline_color", "white" if dark_text else "black"))
        override = rf"{{\an{align}\fs{size}\1c{color}\alpha{alpha}\3c{outline_color}\bord{outline:g}\shad{shadow:g}\pos({x},{y})}}"
        lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{override}{text}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def fill_gradient(buf: bytearray, w: int, h: int, a: tuple[int, int, int], b: tuple[int, int, int], pulse: float = 0.0) -> None:
    for y in range(h):
        t = y / max(1, h - 1)
        r, g, bl = blend(a, b, t)
        if pulse:
            r = min(255, int(r * (1 + pulse)))
            g = min(255, int(g * (1 + pulse)))
            bl = min(255, int(bl * (1 + pulse)))
        row = y * w * 3
        for x in range(w):
            i = row + x * 3
            buf[i] = r
            buf[i + 1] = g
            buf[i + 2] = bl


def rect(buf: bytearray, w: int, h: int, x: int, y: int, rw: int, rh: int, color: tuple[int, int, int], alpha: float = 1.0) -> None:
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(w, x + rw), min(h, y + rh)
    cr, cg, cb = color
    for yy in range(y0, y1):
        row = yy * w * 3
        for xx in range(x0, x1):
            i = row + xx * 3
            if alpha >= 1:
                buf[i], buf[i + 1], buf[i + 2] = cr, cg, cb
            else:
                buf[i] = int(buf[i] * (1 - alpha) + cr * alpha)
                buf[i + 1] = int(buf[i + 1] * (1 - alpha) + cg * alpha)
                buf[i + 2] = int(buf[i + 2] * (1 - alpha) + cb * alpha)


def circle(buf: bytearray, w: int, h: int, cx: int, cy: int, radius: int, color: tuple[int, int, int], alpha: float = 1.0) -> None:
    r2 = radius * radius
    x0, x1 = max(0, cx - radius), min(w - 1, cx + radius)
    y0, y1 = max(0, cy - radius), min(h - 1, cy + radius)
    for y in range(y0, y1 + 1):
        dy = y - cy
        row = y * w * 3
        for x in range(x0, x1 + 1):
            dx = x - cx
            if dx * dx + dy * dy <= r2:
                i = row + x * 3
                if alpha >= 1:
                    buf[i], buf[i + 1], buf[i + 2] = color
                else:
                    buf[i] = int(buf[i] * (1 - alpha) + color[0] * alpha)
                    buf[i + 1] = int(buf[i + 1] * (1 - alpha) + color[1] * alpha)
                    buf[i + 2] = int(buf[i + 2] * (1 - alpha) + color[2] * alpha)


def line(buf: bytearray, w: int, h: int, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        if 0 <= x0 < w and 0 <= y0 < h:
            i = (y0 * w + x0) * 3
            buf[i], buf[i + 1], buf[i + 2] = color
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def add_scanlines(buf: bytearray, w: int, h: int, strength: float = 0.18) -> None:
    for y in range(0, h, 3):
        row = y * w * 3
        for x in range(w):
            i = row + x * 3
            buf[i] = int(buf[i] * (1 - strength))
            buf[i + 1] = int(buf[i + 1] * (1 - strength))
            buf[i + 2] = int(buf[i + 2] * (1 - strength))


def add_noise(buf: bytearray, amount: int, rng: random.Random) -> None:
    if amount <= 0:
        return
    for i in range(0, len(buf), 3):
        n = rng.randint(-amount, amount)
        buf[i] = max(0, min(255, buf[i] + n))
        buf[i + 1] = max(0, min(255, buf[i + 1] + n))
        buf[i + 2] = max(0, min(255, buf[i + 2] + n))


def protected_rects(glitch: dict[str, Any] | bool) -> list[tuple[int, int, int, int]]:
    if not glitch or glitch is True:
        return []
    rects = []
    for item in glitch.get("protect", []) or []:
        rects.append((int(item.get("x", 0)), int(item.get("y", 0)), int(item.get("w", 0)), int(item.get("h", 0))))
    return rects


def intersects(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def apply_glitch(buf: bytearray, w: int, h: int, glitch: dict[str, Any] | bool, frame: int, t: float, rng: random.Random) -> None:
    if not glitch:
        return
    if glitch is True:
        glitch = {"amount": 1.0}
    mode = glitch.get("mode", "light")
    protected = protected_rects(glitch)
    amount = float(glitch.get("amount", 1.0))
    chance = float(glitch.get("chance", 0.22 if mode == "light" else 0.9))
    if rng.random() > chance:
        return
    max_shift = int(glitch.get("shift", 42 if mode == "light" else 160) * amount)
    bands = int(glitch.get("bands", 8 if mode == "light" else 90))
    palette = [
        (0, 255, 60),
        (24, 255, 109),
        (0, 234, 255),
        (0, 183, 255),
        (255, 0, 204),
        (255, 42, 168),
        (27, 0, 255),
        (91, 0, 214),
        (255, 32, 48),
        (2, 3, 10),
    ]
    for _ in range(max(1, bands)):
        y = rng.randrange(0, h)
        if mode == "band_corrupt":
            band_h = rng.choice([rng.randrange(4, 18), rng.randrange(18, 46)])
            x0 = rng.randrange(0, max(1, int(w * 0.38)))
            band_w = rng.randrange(max(24, int(w * 0.18)), w - x0 + 1)
        else:
            band_h = rng.randrange(2, max(3, int(h * 0.08)))
            x0 = 0
            band_w = w
        if any(intersects((x0, y, band_w, band_h), rect) for rect in protected):
            continue
        shift = rng.randrange(-max_shift, max_shift + 1) if max_shift > 0 else 0
        for yy in range(y, min(h, y + band_h)):
            row = yy * w * 3
            src = bytes(buf[row : row + w * 3])
            for x in range(x0, min(w, x0 + band_w)):
                sx = (x - shift) % w
                di = row + x * 3
                si = sx * 3
                buf[di : di + 3] = src[si : si + 3]
        if mode == "band_corrupt" and rng.random() < 0.72:
            color = rng.choice(palette)
            alpha = rng.uniform(0.25, 0.78)
            rect(buf, w, h, x0, y, band_w, band_h, color, alpha)
    if mode == "band_corrupt":
        blocks = int(glitch.get("blocks", 40) * amount)
        for _ in range(blocks):
            bw = rng.randrange(12, max(14, int(w * 0.14)))
            bh = rng.randrange(4, max(5, int(h * 0.08)))
            x = rng.randrange(0, max(1, w - bw))
            y = rng.randrange(0, max(1, h - bh))
            if any(intersects((x, y, bw, bh), rect) for rect in protected):
                continue
            rect(buf, w, h, x, y, bw, bh, rng.choice(palette), rng.uniform(0.35, 0.85))
        darks = int(glitch.get("dark_bands", 10) * amount)
        for _ in range(darks):
            y = rng.randrange(0, h)
            if any(intersects((0, y, w, 14), rect) for rect in protected):
                continue
            rect(buf, w, h, 0, y, w, rng.randrange(2, 14), (2, 3, 10), rng.uniform(0.55, 0.95))
    color_shift = int(glitch.get("rgb_shift", 3) * amount)
    if color_shift:
        original = bytes(buf)
        for y in range(h):
            row = y * w * 3
            for x in range(w):
                r_x = min(w - 1, max(0, x + color_shift))
                b_x = min(w - 1, max(0, x - color_shift))
                i = row + x * 3
                buf[i] = original[row + r_x * 3]
                buf[i + 2] = original[row + b_x * 3 + 2]


def scene_events(scene: dict[str, Any], w: int, h: int, duration: float) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if scene.get("type") == "typewriter":
        header = scene.get("header")
        if header:
            events.append({"text": header, "x": int(w * 0.08), "y": int(h * 0.12), "size": scene.get("header_size", 24), "align": 7, "color": "&H0000D8FF"})
        text = str(scene.get("text", ""))
        cps = max(1.0, float(scene.get("chars_per_second", 22)))
        start = float(scene.get("start", 0.25))
        step = max(1, int(scene.get("step", 2)))
        x = int(scene.get("x", w * 0.08))
        y = int(scene.get("y", h * 0.28))
        size = int(scene.get("size", 30))
        for n in range(step, len(text) + step, step):
            visible = text[: min(n, len(text))]
            t0 = start + max(0, n - step) / cps
            t1 = min(duration, start + n / cps)
            if t0 < duration:
                events.append({"text": visible + " █", "start": t0, "end": max(t1, t0 + 0.02), "x": x, "y": y, "size": size, "align": 7, "color": "&H00FFFFFF"})
        if text:
            events.append({"text": text, "start": min(duration, start + len(text) / cps), "end": duration, "x": x, "y": y, "size": size, "align": 7, "color": "&H00FFFFFF"})
        for cap in scene.get("captions", []):
            events.append(cap)
        return events

    if scene.get("type") in {"image", "media", "layered"} or scene.get("layers"):
        title = scene.get("title") or scene.get("text")
        subtitle = scene.get("subtitle")
        if title:
            events.append({"text": title, "x": w // 2, "y": int(h * 0.10), "size": scene.get("title_size", 38), "color": "&H00FFFFFF"})
        if subtitle:
            events.append({"text": subtitle, "x": w // 2, "y": int(h * 0.91), "size": scene.get("subtitle_size", 24), "color": "&H00D8FF00"})
        for layer in expand_layers(scene.get("layers") or [], duration=duration, scene_w=w, scene_h=h):
            if layer.get("type") == "text":
                events.append(
                    {
                        "text": wrap_text(layer.get("text", ""), layer.get("wrap")),
                        "start": layer.get("start", 0),
                        "end": layer.get("end", duration),
                        "x": layer.get("x", w // 2),
                        "y": layer.get("y", h // 2),
                        "size": layer.get("size", 36),
                        "color": layer.get("color", "&H00FFFFFF"),
                        "align": layer.get("align", 5),
                    }
                )
            elif layer.get("type") == "lower_third":
                x = int(layer.get("x", 52))
                y = int(layer.get("y", h - 132))
                events.append(
                    {
                        "text": wrap_text(layer.get("text", ""), layer.get("wrap", 34)),
                        "start": layer.get("start", 0),
                        "end": layer.get("end", duration),
                        "x": x + int(layer.get("text_x", 22)),
                        "y": y + int(layer.get("text_y", 18)),
                        "size": layer.get("size", 30),
                        "color": layer.get("text_color", "white"),
                        "align": layer.get("align", 7),
                    }
                )
        for cap in scene.get("captions", []):
            events.append(cap)
        return events

    title = scene.get("title") or scene.get("text")
    subtitle = scene.get("subtitle")
    if title:
        events.append({"text": title, "x": w // 2, "y": int(h * 0.42), "size": scene.get("title_size", 54), "color": "&H00FFFFFF"})
    if subtitle:
        events.append({"text": subtitle, "x": w // 2, "y": int(h * 0.58), "size": scene.get("subtitle_size", 28), "color": "&H00D8FF00"})
    for cap in scene.get("captions", []):
        events.append(cap)
    return events


def render_card(buf: bytearray, w: int, h: int, scene: dict[str, Any], t: float, rng: random.Random) -> None:
    bg1 = parse_hex(scene.get("background", "#050510"))
    bg2 = parse_hex(scene.get("background2", "#120724"))
    fill_gradient(buf, w, h, bg1, bg2, 0.03 * math.sin(t * math.pi * 2))
    accent = parse_hex(scene.get("accent", "#00d8ff"))
    rect(buf, w, h, 0, int(h * 0.72), w, 2, accent, 0.7)
    rect(buf, w, h, int(w * 0.14), int(h * 0.74), int(w * 0.72), 1, accent, 0.35)


def render_bars(buf: bytearray, w: int, h: int, scene: dict[str, Any], t: float, rng: random.Random) -> None:
    fill_gradient(buf, w, h, parse_hex(scene.get("background", "#03040b")), parse_hex(scene.get("background2", "#08021a")))
    items = scene.get("items") or [["alpha", 0.8], ["beta", 0.55], ["gamma", 0.35], ["delta", 0.7]]
    x = int(w * 0.18)
    y0 = int(h * 0.32)
    maxw = int(w * 0.64)
    gap = max(24, int(h * 0.09))
    colors = [parse_hex(c) for c in scene.get("colors", ["#00d8ff", "#ff4fd8", "#00ff66", "#a855ff"])]
    progress = min(1.0, t / max(0.001, scene.get("build", 1.0)))
    for idx, item in enumerate(items):
        label, value = item[0], float(item[1])
        yy = y0 + idx * gap
        rect(buf, w, h, x, yy, maxw, 14, (20, 20, 35), 0.9)
        wiggle = 0.03 * math.sin(t * 4 + idx)
        bw = int(maxw * max(0, min(1, value + wiggle)) * progress)
        rect(buf, w, h, x, yy, bw, 14, colors[idx % len(colors)], 0.95)
        if idx < len(str(label)) + 999:
            rect(buf, w, h, x - 12, yy, 4, 14, colors[idx % len(colors)], 0.8)


def render_particles(buf: bytearray, w: int, h: int, scene: dict[str, Any], t: float, rng: random.Random) -> None:
    fill_gradient(buf, w, h, parse_hex(scene.get("background", "#010204")), parse_hex(scene.get("background2", "#001018")))
    accent = parse_hex(scene.get("accent", "#00ff66"))
    count = int(scene.get("count", 90))
    for i in range(count):
        px = int((math.sin(i * 12.989 + t * 0.7) * 0.5 + 0.5) * w)
        py = int(((i * 37 + t * (20 + i % 11)) % h))
        size = 1 + (i % 3)
        rect(buf, w, h, px, py, size, size, accent, 0.45 + 0.35 * ((i % 5) / 5))
    for i in range(8):
        y = int((h * (i + 1) / 9) + math.sin(t * 1.7 + i) * 8)
        line(buf, w, h, 0, y, w - 1, y, accent,)


def render_wave(buf: bytearray, w: int, h: int, scene: dict[str, Any], t: float, rng: random.Random) -> None:
    fill_gradient(buf, w, h, parse_hex(scene.get("background", "#08020c")), parse_hex(scene.get("background2", "#02020a")))
    color = parse_hex(scene.get("accent", "#ff4fd8"))
    mid = h // 2
    last: tuple[int, int] | None = None
    for x in range(w):
        y = int(mid + math.sin(x * 0.035 + t * 5) * 42 + math.sin(x * 0.011 - t * 3) * 28)
        if last:
            line(buf, w, h, last[0], last[1], x, y, color)
        last = (x, y)
    rect(buf, w, h, 0, mid, w, 1, (255, 255, 255), 0.18)


def render_grid(buf: bytearray, w: int, h: int, scene: dict[str, Any], t: float, rng: random.Random) -> None:
    fill_gradient(buf, w, h, parse_hex(scene.get("background", "#01030a")), parse_hex(scene.get("background2", "#080414")))
    color = parse_hex(scene.get("accent", "#00d8ff"))
    spacing = int(scene.get("spacing", 42))
    horizon = int(h * float(scene.get("horizon", 0.62)))
    drift = (t * 35) % spacing
    for x in range(-spacing, w + spacing, spacing):
        line(buf, w, h, w // 2, horizon, int(x + drift), h - 1, color)
    for i in range(14):
        y = horizon + int((i / 13) ** 1.8 * (h - horizon))
        line(buf, w, h, 0, y, w - 1, y, color)
    rect(buf, w, h, 0, horizon, w, 2, color, 0.65)


def render_orbits(buf: bytearray, w: int, h: int, scene: dict[str, Any], t: float, rng: random.Random) -> None:
    fill_gradient(buf, w, h, parse_hex(scene.get("background", "#020206")), parse_hex(scene.get("background2", "#09021a")))
    cx, cy = w // 2, h // 2
    colors = [parse_hex(c) for c in scene.get("colors", ["#00d8ff", "#ff4fd8", "#00ff66"])]
    for idx, radius in enumerate(scene.get("radii", [45, 78, 116, 150])):
        color = colors[idx % len(colors)]
        steps = 96
        last: tuple[int, int] | None = None
        squash = 0.45 + idx * 0.08
        for s in range(steps + 1):
            a = 2 * math.pi * s / steps
            x = int(cx + math.cos(a) * radius)
            y = int(cy + math.sin(a) * radius * squash)
            if last:
                line(buf, w, h, last[0], last[1], x, y, color)
            last = (x, y)
        angle = t * (0.9 + idx * 0.25) + idx * 1.7
        dot_x = int(cx + math.cos(angle) * radius)
        dot_y = int(cy + math.sin(angle) * radius * squash)
        circle(buf, w, h, dot_x, dot_y, 5 + idx % 2, color, 0.95)
    circle(buf, w, h, cx, cy, 12, parse_hex(scene.get("core", "#ffffff")), 0.85)


def render_typewriter(buf: bytearray, w: int, h: int, scene: dict[str, Any], t: float, rng: random.Random) -> None:
    fill_gradient(buf, w, h, parse_hex(scene.get("background", "#020204")), parse_hex(scene.get("background2", "#050b12")))
    accent = parse_hex(scene.get("accent", "#00d8ff"))
    rect(buf, w, h, int(w * 0.055), int(h * 0.09), int(w * 0.89), int(h * 0.74), (0, 0, 0), 0.34)
    rect(buf, w, h, int(w * 0.055), int(h * 0.09), int(w * 0.89), 2, accent, 0.8)
    rect(buf, w, h, int(w * 0.055), int(h * 0.83), int(w * 0.89), 2, accent, 0.45)
    if int(t * 2) % 2 == 0:
        rect(buf, w, h, int(w * 0.08), int(h * 0.79), 10, 3, accent, 0.9)


def render_scene_frames(scene: dict[str, Any], w: int, h: int, fps: int) -> bytes:
    duration = float(scene.get("duration", 2.0))
    frames = max(1, int(round(duration * fps)))
    rng = random.Random(int(scene.get("seed", 1337)))
    chunks: list[bytes] = []
    kind = scene.get("type", "card")
    renderers = {
        "card": render_card,
        "bars": render_bars,
        "particles": render_particles,
        "wave": render_wave,
        "grid": render_grid,
        "orbits": render_orbits,
        "typewriter": render_typewriter,
    }
    renderer = renderers.get(kind)
    if renderer is None:
        raise SystemExit(f"unknown scene type: {kind}")
    for frame in range(frames):
        t = frame / fps
        buf = bytearray(w * h * 3)
        renderer(buf, w, h, scene, t, rng)
        if scene.get("scanlines", True):
            add_scanlines(buf, w, h, float(scene.get("scanline_strength", 0.14)))
        add_noise(buf, int(scene.get("noise", 4)), rng)
        apply_glitch(buf, w, h, scene.get("glitch"), frame, t, rng)
        chunks.append(bytes(buf))
    return b"".join(chunks)


def render_scene(scene: dict[str, Any], out: Path, *, w: int, h: int, fps: int, ffmpeg: str) -> None:
    if scene.get("type") == "layered" or scene.get("layers"):
        render_layered_scene(scene, out, w=w, h=h, fps=fps, ffmpeg=ffmpeg)
        return

    if scene.get("type") in {"image", "media"} and scene.get("source"):
        render_image_scene(scene, out, w=w, h=h, fps=fps, ffmpeg=ffmpeg)
        return

    duration = scene_duration(scene)
    raw = render_scene_frames(scene, w, h, fps)
    with tempfile.TemporaryDirectory(prefix="vidkit-scene-") as tmp:
        tmpdir = Path(tmp)
        base = tmpdir / "base.mp4"
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{w}x{h}",
            "-r",
            str(fps),
            "-i",
            "pipe:0",
            "-f",
            "lavfi",
            "-t",
            str(duration),
            "-i",
            audio_source(scene, duration),
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(base),
        ]
        run(cmd, input_bytes=raw)
        events = scene_events(scene, w, h, duration)
        if events:
            subs = tmpdir / "scene.ass"
            write_ass(w, h, duration, events, subs)
            run([
                ffmpeg,
                "-y",
                "-i",
                str(base),
                "-vf",
                f"subtitles={esc_filter_path(subs)}",
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(out),
            ])
        else:
            shutil.copy2(base, out)


def render_layered_scene(scene: dict[str, Any], out: Path, *, w: int, h: int, fps: int, ffmpeg: str) -> None:
    duration = scene_duration(scene)
    layers = expand_layers(scene.get("layers") or [], duration=duration, scene_w=w, scene_h=h)
    if not layers:
        raise SystemExit("layered scene needs at least one layer")
    background = scene.get("background", "black")

    prepared_layers: list[dict[str, Any]] = []
    for original in layers:
        layer = dict(original)
        if layer.get("type") == "lower_third":
            layer.setdefault("x", 52)
            layer.setdefault("y", h - 132)
            layer.setdefault("width", w - 104)
            layer.setdefault("height", 104)
            layer.setdefault("panel_color", "#000000")
            layer.setdefault("opacity", 0.94)
            layer.setdefault("border", 2)
            layer.setdefault("border_color", "#00d8ff")
            layer.setdefault("radius", 14)
        prepared_layers.append(apply_animation_presets(layer, duration=duration, w=w, h=h))
    layers = prepared_layers

    with tempfile.TemporaryDirectory(prefix="vidkit-layered-") as tmp:
        tmpdir = Path(tmp)
        base = tmpdir / "base.mp4"
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={background}:s={w}x{h}:r={fps}:d={duration}",
        ]
        media_inputs: dict[int, int] = {}
        alpha_inputs: dict[int, int] = {}
        next_input = 1
        for layer_index, layer in enumerate(layers):
            layer_type = layer.get("type") or ("media" if layer.get("source") else "panel")
            if layer_type in {"text", "panel", "lower_third"}:
                pass
            elif layer_type != "media":
                raise SystemExit(f"unsupported layer type: {layer_type}")
            else:
                source = Path(layer["source"]).expanduser()
                if not source.exists():
                    raise SystemExit(f"layer source not found: {source}")
                media_inputs[layer_index] = next_input
                next_input += 1
                cmd += media_source_args(source, duration, fps, layer.get("source_type", "auto"))
            if layer_type != "text" and has_keyframed_prop(layer, "opacity"):
                box_w = int(layer.get("width", w))
                box_h = int(layer.get("height", h))
                mask = tmpdir / f"alpha-{layer_index:03d}.gray"
                write_opacity_mask(mask, layer, width=box_w, height=box_h, radius=int(layer.get("radius", 0)), duration=duration, fps=fps)
                alpha_inputs[layer_index] = next_input
                next_input += 1
                cmd += ["-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{box_w}x{box_h}", "-r", str(fps), "-i", str(mask)]
        audio_index = next_input
        cmd += ["-f", "lavfi", "-t", str(duration), "-i", audio_source(scene, duration)]

        filters: list[str] = []
        base_label = "0:v"

        def add_panel_layer(base: str, layer: dict[str, Any], out_label: str, *, idx: int, width: int, height: int, x_expr: str, y_expr: str, start: float, end: float, color_key: str = "panel_color", alpha_input: int | None = None) -> str:
            color = ffmpeg_color(layer.get(color_key, layer.get("color", "black")))
            radius = int(layer.get("radius", 0))
            opacity_expr = str(float(layer.get("opacity", 1.0)))
            raw_label = f"{out_label}raw"
            shaped_label = f"{out_label}shape"
            alpha_label = f"{out_label}alpha"
            filters.append(f"color=c={color}:s={width}x{height}:r={fps}:d={duration},format=rgba[{raw_label}]")
            if alpha_input is not None:
                filters.append(f"[{raw_label}][{alpha_input}:v]alphamerge[{alpha_label}]")
            else:
                apply_rounded_mask(filters, raw_label, shaped_label, width=width, height=height, radius=radius, fps=fps, duration=duration)
                filters.append(f"[{shaped_label}]colorchannelmixer=aa='{ffexpr(opacity_expr)}'[{alpha_label}]")
            filters.append(f"[{base}][{alpha_label}]overlay=x='{x_expr}':y='{y_expr}':enable='between(t,{start},{end})':shortest=1[{out_label}]")
            return out_label

        for idx, layer in enumerate(layers, start=1):
            layer_type = layer.get("type") or ("media" if layer.get("source") else "panel")
            if layer_type == "text":
                continue
            if layer_type == "lower_third":
                layer_type = "panel"
            box_w = int(layer.get("width", w))
            box_h = int(layer.get("height", h))
            x_default = float(layer.get("x", (w - box_w) / 2))
            y_default = float(layer.get("y", (h - box_h) / 2))
            x_expr = keyframed_expr(layer, "x", x_default, duration)
            y_expr = keyframed_expr(layer, "y", y_default, duration)
            start = float(layer.get("start", 0))
            end = float(layer.get("end", duration))
            opacity_expr = str(float(layer.get("opacity", 1.0)))
            scale_expr = keyframed_expr(layer, "scale", float(layer.get("scale", 1.0)), duration)

            if layer_type == "panel":
                border = int(layer.get("border", 0))
                if border > 0:
                    border_label = f"pb{idx}"
                    border_layer = {
                        "color": layer.get("border_color", "white"),
                        "opacity": layer.get("border_opacity", 1.0),
                        "radius": int(layer.get("radius", 0)) + border,
                    }
                    add_panel_layer(base_label, border_layer, border_label, idx=idx, width=box_w + border * 2, height=box_h + border * 2, x_expr=f"({x_expr})-{border}", y_expr=f"({y_expr})-{border}", start=start, end=end, color_key="color")
                    base_label = border_label
                out_label = f"v{idx}"
                base_label = add_panel_layer(base_label, layer, out_label, idx=idx, width=box_w, height=box_h, x_expr=x_expr, y_expr=y_expr, start=start, end=end, alpha_input=alpha_inputs.get(idx - 1))
                continue

            fit = layer.get("fit", "contain")
            layer_filter = fit_filter(box_w, box_h, fit, layer.get("pad_color", "black"))
            layer_glitch = glitch_filter(layer.get("glitch"))
            if layer_glitch:
                layer_filter += f",{layer_glitch}"
            layer_filter += ",format=rgba"
            pre_layer_label = f"layer{idx}pre"
            input_index = media_inputs[idx - 1]
            filters.append(f"[{input_index}:v]{layer_filter}[{pre_layer_label}]")
            rounded_label = f"layer{idx}round"
            alpha_input = alpha_inputs.get(idx - 1)
            if alpha_input is not None:
                fmt_label = f"layer{idx}fmt"
                filters.append(f"[{pre_layer_label}]format=rgba[{fmt_label}]")
                filters.append(f"[{fmt_label}][{alpha_input}:v]alphamerge[{rounded_label}]")
            else:
                apply_rounded_mask(filters, pre_layer_label, rounded_label, width=box_w, height=box_h, radius=int(layer.get("radius", 0)), fps=fps, duration=duration)
            layer_label = f"layer{idx}"
            if alpha_input is not None:
                filters.append(f"[{rounded_label}]scale=w='{ffexpr(f'max(2,trunc(iw*({scale_expr})/2)*2)')}':h='{ffexpr(f'max(2,trunc(ih*({scale_expr})/2)*2)')}':eval=frame[{layer_label}]")
            else:
                filters.append(f"[{rounded_label}]colorchannelmixer=aa='{ffexpr(opacity_expr)}',scale=w='{ffexpr(f'max(2,trunc(iw*({scale_expr})/2)*2)')}':h='{ffexpr(f'max(2,trunc(ih*({scale_expr})/2)*2)')}':eval=frame[{layer_label}]")

            border = int(layer.get("border", 0))
            if border > 0:
                border_label = f"b{idx}"
                border_layer = {
                    "color": layer.get("border_color", "white"),
                    "opacity": layer.get("border_opacity", 1.0),
                    "radius": int(layer.get("radius", 0)) + border,
                }
                add_panel_layer(base_label, border_layer, border_label, idx=idx, width=box_w + border * 2, height=box_h + border * 2, x_expr=f"({x_expr})-{border}", y_expr=f"({y_expr})-{border}", start=start, end=end, color_key="color")
                base_label = border_label

            out_label = f"v{idx}"
            filters.append(f"[{base_label}][{layer_label}]overlay=x='{x_expr}':y='{y_expr}':enable='between(t,{start},{end})':shortest=1[{out_label}]")
            base_label = out_label

        if filters:
            cmd += ["-filter_complex", ";".join(filters), "-map", f"[{base_label}]"]
        else:
            cmd += ["-map", "0:v"]
        cmd += [
            "-map",
            f"{audio_index}:a",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(base),
        ]
        run(cmd)
        events = scene_events(scene, w, h, duration)
        if events:
            subs = tmpdir / "scene.ass"
            write_ass(w, h, duration, events, subs)
            run([
                ffmpeg,
                "-y",
                "-i",
                str(base),
                "-vf",
                f"subtitles={esc_filter_path(subs)}",
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(out),
            ])
        else:
            shutil.copy2(base, out)


def render_image_scene(scene: dict[str, Any], out: Path, *, w: int, h: int, fps: int, ffmpeg: str) -> None:
    duration = scene_duration(scene)
    source = Path(scene["source"]).expanduser()
    if not source.exists():
        raise SystemExit(f"media source not found: {source}")
    background = scene.get("background", "black")
    fit = scene.get("fit", "contain")
    box_w = int(scene.get("width", w))
    box_h = int(scene.get("height", h))
    x = int(scene.get("x", (w - box_w) / 2))
    y = int(scene.get("y", (h - box_h) / 2))
    border = int(scene.get("border", 0))
    border_color = scene.get("border_color", "white")
    camera = scene.get("camera") or {}
    camera_kind = camera.get("type", "none")

    with tempfile.TemporaryDirectory(prefix="vidkit-media-") as tmp:
        tmpdir = Path(tmp)
        base = tmpdir / "base.mp4"
        layer_filter = fit_filter(box_w, box_h, fit, scene.get("pad_color", "black"))
        if camera_kind == "zoom_in":
            zoom_to = float(camera.get("to", 1.16))
            frames = max(1, int(duration * fps))
            step = max(0.0, (zoom_to - 1.0) / frames)
            layer_filter = f"{layer_filter},zoompan=z='min(zoom+{step:.8f},{zoom_to})':d=1:s={box_w}x{box_h}:fps={fps}"
        elif camera_kind == "zoom_out":
            zoom_from = float(camera.get("from", 1.16))
            frames = max(1, int(duration * fps))
            step = max(0.0, (zoom_from - 1.0) / frames)
            layer_filter = f"{layer_filter},zoompan=z='max({zoom_from}-on*{step:.8f},1)':d=1:s={box_w}x{box_h}:fps={fps}"
        elif camera_kind == "pan":
            axis = camera.get("axis", "x")
            amount = float(camera.get("amount", 48))
            overscale_w = box_w + (int(abs(amount)) if axis == "x" else 0)
            overscale_h = box_h + (int(abs(amount)) if axis == "y" else 0)
            base_filter = fit_filter(overscale_w, overscale_h, fit, scene.get("pad_color", "black"))
            if axis == "y":
                crop = f"crop={box_w}:{box_h}:(iw-{box_w})/2:({abs(amount)}*t/{duration})"
            else:
                crop = f"crop={box_w}:{box_h}:({abs(amount)}*t/{duration}):(ih-{box_h})/2"
            layer_filter = f"{base_filter},{crop}"
        elif camera_kind == "shake":
            amount = int(camera.get("amount", 8))
            overscale_w = box_w + amount * 2
            overscale_h = box_h + amount * 2
            base_filter = fit_filter(overscale_w, overscale_h, fit, scene.get("pad_color", "black"))
            crop = f"crop={box_w}:{box_h}:{amount}+{amount}*sin(n*1.7):{amount}+{amount}*cos(n*1.3)"
            layer_filter = f"{base_filter},{crop}"

        scene_glitch = glitch_filter(scene.get("glitch"))
        if scene_glitch:
            layer_filter += f",{scene_glitch}"

        filters = []
        if border > 0:
            filters.append(f"[0:v]drawbox=x={x-border}:y={y-border}:w={box_w + border*2}:h={box_h + border*2}:color={border_color}:t=fill[bg]")
            bg_label = "bg"
        else:
            bg_label = "0:v"
        filters.append(f"[1:v]{layer_filter}[layer]")
        filters.append(f"[{bg_label}][layer]overlay={x}:{y}:shortest=1[v]")

        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={background}:s={w}x{h}:r={fps}:d={duration}",
            *media_source_args(source, duration, fps, scene.get("source_type", "auto")),
            "-f",
            "lavfi",
            "-t",
            str(duration),
            "-i",
            audio_source(scene, duration),
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[v]",
            "-map",
            "2:a",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(base),
        ]
        run(cmd)
        events = scene_events(scene, w, h, duration)
        if events:
            subs = tmpdir / "scene.ass"
            write_ass(w, h, duration, events, subs)
            run([
                ffmpeg,
                "-y",
                "-i",
                str(base),
                "-vf",
                f"subtitles={esc_filter_path(subs)}",
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(out),
            ])
        else:
            shutil.copy2(base, out)


def quote_concat_path(path: Path) -> str:
    return "file '" + str(path.resolve()).replace("'", "'\\''") + "'"


def concat(clips: list[Path], out: Path, ffmpeg: str) -> None:
    with tempfile.TemporaryDirectory(prefix="vidkit-concat-") as tmp:
        list_file = Path(tmp) / "clips.txt"
        list_file.write_text("\n".join(quote_concat_path(p) for p in clips) + "\n")
        run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", "-movflags", "+faststart", str(out)])


def concat_with_transitions(
    clips: list[Path],
    scenes: list[dict[str, Any]],
    out: Path,
    ffmpeg: str,
    default_transition: dict[str, Any] | None,
) -> None:
    if len(clips) == 1:
        shutil.copy2(clips[0], out)
        return

    transitions: list[dict[str, Any]] = []
    for idx in range(len(clips) - 1):
        transition = scene_transition(scenes[idx], default_transition) or {"type": "fade", "duration": 0.01}
        limit = max(0.01, min(scene_duration(scenes[idx]), scene_duration(scenes[idx + 1])) / 2)
        transition = dict(transition)
        transition["duration"] = min(float(transition["duration"]), limit)
        transitions.append(transition)

    cmd = [ffmpeg, "-y"]
    for clip in clips:
        cmd += ["-i", str(clip)]

    filters: list[str] = []
    video_label = "0:v"
    audio_label = "0:a"
    elapsed = scene_duration(scenes[0])
    for idx, transition in enumerate(transitions, start=1):
        duration = float(transition["duration"])
        xfade = transition["type"]
        offset = max(0.0, elapsed - duration)
        next_video = f"v{idx}"
        next_audio = f"a{idx}"
        filters.append(f"[{video_label}][{idx}:v]xfade=transition={xfade}:duration={duration}:offset={offset}[{next_video}]")
        filters.append(f"[{audio_label}][{idx}:a]acrossfade=d={duration}:c1=tri:c2=tri[{next_audio}]")
        video_label = next_video
        audio_label = next_audio
        elapsed += scene_duration(scenes[idx]) - duration

    cmd += [
        "-filter_complex",
        ";".join(filters),
        "-map",
        f"[{video_label}]",
        "-map",
        f"[{audio_label}]",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(out),
    ]
    run(cmd)


def estimated_total_duration(scenes: list[dict[str, Any]], default_transition: dict[str, Any] | None) -> float:
    total = sum(scene_duration(scene) for scene in scenes)
    for idx in range(len(scenes) - 1):
        transition = scene_transition(scenes[idx], default_transition)
        if transition:
            total -= min(float(transition["duration"]), min(scene_duration(scenes[idx]), scene_duration(scenes[idx + 1])) / 2)
    return max(0.01, total)


def apply_audio_bed(input_video: Path, out: Path, ffmpeg: str, audio_config: dict[str, Any], duration: float) -> None:
    bed = audio_config.get("bed")
    if not bed:
        shutil.copy2(input_video, out)
        return

    scene_volume = float(audio_config.get("scene_volume", 1.0))
    bed_volume = float(bed.get("volume", 0.25))
    cmd = [ffmpeg, "-y", "-i", str(input_video)]
    if bed.get("source"):
        source = Path(bed["source"]).expanduser()
        if not source.exists():
            raise SystemExit(f"audio bed source not found: {source}")
        if bed.get("loop", True):
            cmd += ["-stream_loop", "-1"]
        cmd += ["-i", str(source)]
    else:
        cmd += ["-f", "lavfi", "-i", audio_source({"audio": bed}, duration)]

    bed_filters = [f"volume={bed_volume}", f"atrim=0:{duration}", "asetpts=PTS-STARTPTS"]
    fade_in = float(bed.get("fade_in", 0))
    fade_out = float(bed.get("fade_out", 0))
    if fade_in > 0:
        bed_filters.append(f"afade=t=in:st=0:d={fade_in}")
    if fade_out > 0:
        bed_filters.append(f"afade=t=out:st={max(0, duration - fade_out)}:d={fade_out}")
    filter_complex = f"[0:a]volume={scene_volume}[scene];[1:a]{','.join(bed_filters)}[bed];[scene][bed]amix=inputs=2:duration=first:dropout_transition=0[a]"
    cmd += [
        "-filter_complex",
        filter_complex,
        "-map",
        "0:v:0",
        "-map",
        "[a]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        "-movflags",
        "+faststart",
        str(out),
    ]
    run(cmd)


def demo_spec() -> dict[str, Any]:
    return {
        "size": "640x360",
        "fps": 24,
        "transition": {"type": "fade", "duration": 0.35},
        "scenes": [
            {"type": "card", "duration": 1.8, "title": "COMPOSE", "subtitle": "now with transitions + generated audio", "background": "#050510", "background2": "#18051f", "accent": "#00d8ff", "noise": 3, "audio": {"type": "tone", "frequency": 164, "volume": 0.045}, "transition": {"type": "wipeleft", "duration": 0.4}},
            {"type": "grid", "duration": 2.2, "title": "space / layout", "subtitle": "animated grids, not borrowed frames", "accent": "#00d8ff", "noise": 4, "audio": {"type": "pulse", "frequency": 440, "volume": 0.045, "period": 0.45, "duty": 0.08}},
            {"type": "orbits", "duration": 2.4, "title": "motion systems", "subtitle": "circles, paths, particles, timing", "noise": 5, "audio": {"type": "tone", "frequency": 246.94, "volume": 0.04}, "transition": {"type": "circleopen", "duration": 0.45}},
            {"type": "bars", "duration": 2.4, "title": "data shapes", "subtitle": "rectangles + values + animation", "items": [["scene", 0.85], ["overlay", 0.67], ["motion", 0.74], ["export", 0.95]], "noise": 5, "audio": {"type": "noise", "color": "pink", "amplitude": 0.012}},
            {"type": "typewriter", "duration": 4.0, "header": "vidkit | generated monologue", "text": "This is closer: text, motion, shapes, timing, cuts, and sound generated here. Styles can come later.", "chars_per_second": 28, "noise": 5, "audio": {"type": "pulse", "frequency": 660, "volume": 0.035, "period": 0.18, "duty": 0.035}, "transition": {"type": "slideright", "duration": 0.4}},
            {"type": "wave", "duration": 2.2, "title": "next: media layers", "subtitle": "images / clips / masks / richer motion", "accent": "#ff4fd8", "noise": 6, "audio": {"type": "tone", "frequency": 110, "volume": 0.04}},
        ],
    }


def template_spec(name: str) -> dict[str, Any]:
    if name == "lower-third":
        return {
            "size": "640x360",
            "fps": 24,
            "transition": {"type": "fade", "duration": 0.2},
            "scenes": [
                {
                    "type": "layered",
                    "duration": 4.0,
                    "background": "#02030a",
                    "audio": {"type": "tone", "frequency": 164, "volume": 0.035},
                    "layers": [
                        {
                            "type": "media",
                            "source": bundled_asset("sample.ppm"),
                            "source_type": "image",
                            "fit": "cover",
                            "width": 640,
                            "height": 360,
                            "x": 0,
                            "y": 0,
                            "opacity": 0.75,
                        },
                        {
                            "type": "lower_third",
                            "text": "Lower-third text layer with automatic wrapping",
                            "wrap": 36,
                            "start": 0.45,
                            "end": 3.65,
                        },
                    ],
                }
            ],
        }
    if name == "motion-card":
        return {
            "size": "640x360",
            "fps": 24,
            "audio": {"bed": {"type": "tone", "frequency": 96, "volume": 0.03, "fade_in": 0.5, "fade_out": 0.5}},
            "scenes": [
                {
                    "type": "layered",
                    "duration": 4.0,
                    "background": "#050510",
                    "layers": [
                        {"type": "panel", "x": 80, "y": 90, "width": 480, "height": 160, "color": "#000000", "opacity": 0.55, "border": 3, "border_color": "#ff4fd8", "keyframes": [{"time": 0, "x": 40}, {"time": 0.8, "x": 80, "ease": "out_cubic"}]},
                        {"type": "text", "text": "Motion card template\nkeyframed panel + wrapped text", "x": 112, "y": 126, "size": 34, "align": 7, "wrap": 28},
                    ],
                }
            ],
        }
    if name == "glitch-card":
        return {
            "size": "640x360",
            "fps": 24,
            "transition": {"type": "fade", "duration": 0.2},
            "scenes": [
                {"type": "card", "duration": 1.2, "title": "GLITCH", "subtitle": "effect pass", "background": "#050510", "background2": "#170011", "accent": "#ff4fd8", "glitch": {"amount": 1.4, "chance": 0.65, "shift": 54, "rgb_shift": 5}, "audio": {"type": "noise", "color": "pink", "amplitude": 0.018}},
                {
                    "type": "layered",
                    "duration": 3.2,
                    "background": "#02030a",
                    "audio": {"type": "pulse", "frequency": 660, "volume": 0.035, "period": 0.18, "duty": 0.04},
                    "layers": [
                        {"type": "media", "source": bundled_asset("sample.ppm"), "source_type": "image", "fit": "cover", "width": 420, "height": 236, "x": 110, "y": 62, "border": 5, "border_color": "#00d8ff", "glitch": {"amount": 1.0, "noise": 20, "hue": 18}},
                        {"type": "lower_third", "text": "Glitch is an effect, not the whole style", "wrap": 36, "start": 0.5, "end": 3.0},
                    ],
                },
            ],
        }
    if name == "band-glitch":
        return {
            "size": "640x360",
            "fps": 24,
            "transition": {"type": "fade", "duration": 0.18},
            "scenes": [
                {
                    "type": "orbits",
                    "duration": 2.4,
                    "title": "BAND CORRUPT",
                    "subtitle": "chunky horizontal slice glitch",
                    "background": "#02030a",
                    "background2": "#120018",
                    "noise": 12,
                    "glitch": {"mode": "band_corrupt", "amount": 1.35, "chance": 1.0, "bands": 130, "blocks": 65, "shift": 190, "rgb_shift": 18, "dark_bands": 16, "protect": [{"x": 36, "y": 32, "w": 568, "h": 96}]},
                    "audio": {"type": "noise", "color": "pink", "amplitude": 0.024},
                },
                {
                    "type": "layered",
                    "duration": 2.8,
                    "background": "#02030a",
                    "audio": {"type": "pulse", "frequency": 720, "volume": 0.04, "period": 0.16, "duty": 0.045},
                    "layers": [
                        {"type": "media", "source": bundled_asset("sample.ppm"), "source_type": "image", "fit": "cover", "width": 640, "height": 360, "x": 0, "y": 0, "glitch": {"amount": 1.6, "noise": 46, "hue": 32, "contrast": 1.35}},
                        {"type": "lower_third", "text": "Strong band corruption is now a reusable effect", "wrap": 42, "start": 0.35, "end": 2.55},
                    ],
                },
            ],
        }
    if name == "media-card":
        return {
            "size": "640x360",
            "fps": 24,
            "transition": {"type": "fade", "duration": 0.22},
            "scenes": [
                {
                    "type": "layered",
                    "duration": 4.2,
                    "background": "#02030a",
                    "audio": {"type": "tone", "frequency": 146, "volume": 0.035},
                    "layers": [
                        {"type": "panel", "x": 34, "y": 34, "width": 572, "height": 292, "color": "#000000", "opacity": 0.55, "border": 3, "border_color": "#00d8ff"},
                        {"type": "media", "source": bundled_asset("sample.ppm"), "source_type": "image", "fit": "cover", "width": 360, "height": 210, "x": 58, "y": 66, "border": 4, "border_color": "#ff4fd8"},
                        {"type": "text", "text": "Media card\nprotected text zone", "x": 444, "y": 94, "size": 32, "align": 7, "wrap": 16, "color": "white"},
                        {"type": "text", "text": "Useful default: clip on the left, readable copy on the right.", "x": 444, "y": 178, "size": 22, "align": 7, "wrap": 22, "color": "cyan"},
                    ],
                }
            ],
        }
    if name == "split-screen":
        return {
            "size": "640x360",
            "fps": 24,
            "transition": {"type": "fade", "duration": 0.2},
            "scenes": [
                {
                    "type": "layered",
                    "duration": 4.0,
                    "background": "#050510",
                    "audio": {"type": "pulse", "frequency": 420, "volume": 0.03, "period": 0.35, "duty": 0.06},
                    "layers": [
                        {"type": "media", "source": bundled_asset("sample.ppm"), "source_type": "image", "fit": "cover", "width": 286, "height": 210, "x": 36, "y": 72, "border": 4, "border_color": "#00d8ff"},
                        {"type": "media", "source": bundled_asset("sample.ppm"), "source_type": "image", "fit": "cover", "width": 286, "height": 210, "x": 318, "y": 72, "border": 4, "border_color": "#ff4fd8"},
                        {"type": "lower_third", "text": "Split-screen template with protected lower-third", "wrap": 42, "start": 0.4, "end": 3.7},
                    ],
                }
            ],
        }
    raise SystemExit(f"unknown template: {name} (try {', '.join(TEMPLATE_NAMES)})")


def portable_spec(spec: Any) -> Any:
    if isinstance(spec, dict):
        return {key: portable_spec(value) for key, value in spec.items()}
    if isinstance(spec, list):
        return [portable_spec(value) for value in spec]
    if isinstance(spec, str):
        assets = repo_root() / "examples" / "assets"
        try:
            path = Path(spec)
            if path.is_absolute() and path.is_relative_to(assets):
                return str(Path("examples/assets") / path.relative_to(assets))
        except ValueError:
            pass
    return spec


def bundled_asset_refs(spec: Any) -> list[Path]:
    refs: list[Path] = []
    assets = repo_root() / "examples" / "assets"
    if isinstance(spec, dict):
        for value in spec.values():
            refs.extend(bundled_asset_refs(value))
    elif isinstance(spec, list):
        for value in spec:
            refs.extend(bundled_asset_refs(value))
    elif isinstance(spec, str):
        try:
            path = Path(spec)
            if path.is_absolute() and path.is_relative_to(assets):
                refs.append(path)
        except ValueError:
            pass
    return refs


def copy_bundled_assets(spec: dict[str, Any], destination_root: Path) -> None:
    assets = repo_root() / "examples" / "assets"
    for source in bundled_asset_refs(spec):
        relative = source.relative_to(assets)
        destination = destination_root / "examples" / "assets" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def source_spec(source: str) -> dict[str, Any]:
    if source == "demo":
        return demo_spec()
    if source.startswith("template:"):
        return template_spec(source.split(":", 1)[1])
    if source in TEMPLATE_NAMES:
        return template_spec(source)
    return load_spec(Path(source))


def print_json(spec: dict[str, Any]) -> None:
    print(json.dumps(portable_spec(spec), indent=2))


def parse_size(value: str | tuple[int, int]) -> tuple[int, int]:
    if isinstance(value, tuple):
        return value
    if "x" not in value:
        raise SystemExit("size must look like 1280x720")
    a, b = value.lower().split("x", 1)
    return int(a), int(b)


def load_spec(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_positive_number(errors: list[str], path: str, value: Any, *, allow_zero: bool = False) -> None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        errors.append(f"{path} must be a number")
        return
    if allow_zero:
        if number < 0:
            errors.append(f"{path} must be >= 0")
    elif number <= 0:
        errors.append(f"{path} must be > 0")


def validate_size(errors: list[str], path: str, value: Any) -> None:
    text = str(value)
    if "x" not in text.lower():
        errors.append(f"{path} must look like 1280x720")
        return
    a, b = text.lower().split("x", 1)
    try:
        width, height = int(a), int(b)
    except ValueError:
        errors.append(f"{path} dimensions must be integers")
        return
    if width <= 0 or height <= 0:
        errors.append(f"{path} dimensions must be > 0")


def validate_color(errors: list[str], path: str, value: Any) -> None:
    if value is None:
        return
    text = str(value)
    if text.startswith("&H") or text.startswith("0x"):
        return
    try:
        parse_hex(text)
    except ValueError:
        # ffmpeg has many named colors; allow plain names rather than rejecting
        # valid ffmpeg input. Reject obviously malformed hex strings.
        if text.startswith("#"):
            errors.append(f"{path} invalid color: {text}")


def validate_audio(errors: list[str], path: str, audio: Any) -> None:
    if audio is None:
        return
    if not isinstance(audio, dict):
        errors.append(f"{path} must be an object")
        return
    kind = audio.get("type", "silence")
    if kind not in AUDIO_TYPES:
        errors.append(f"{path}.type unsupported audio type: {kind}")
    if kind == "sfx":
        preset = audio.get("preset", "bonk")
        if preset not in SFX_PRESETS:
            errors.append(f"{path}.preset unsupported sfx preset: {preset}")
        for field in ("volume", "duration"):
            if field in audio:
                validate_positive_number(errors, f"{path}.{field}", audio[field])
    if audio.get("source"):
        source = Path(audio["source"]).expanduser()
        if not source.exists():
            errors.append(f"{path}.source not found: {source}")


def validate_transition(errors: list[str], path: str, transition: Any) -> None:
    if not transition:
        return
    if isinstance(transition, str):
        kind = transition
        duration = 0.35
    elif isinstance(transition, dict):
        kind = transition.get("type", "fade")
        duration = transition.get("duration", 0.35)
    else:
        errors.append(f"{path} must be a string or object")
        return
    if kind not in TRANSITION_TYPES:
        errors.append(f"{path}.type unsupported transition: {kind}")
    validate_positive_number(errors, f"{path}.duration", duration, allow_zero=True)


def validate_keyframes(errors: list[str], path: str, owner: dict[str, Any], duration: float, *, allowed_props: set[str]) -> None:
    keyframes = owner.get("keyframes") or []
    if not isinstance(keyframes, list):
        errors.append(f"{path}.keyframes must be a list")
        return
    seen_times: list[float] = []
    for idx, keyframe in enumerate(keyframes):
        kpath = f"{path}.keyframes[{idx}]"
        if not isinstance(keyframe, dict):
            errors.append(f"{kpath} must be an object")
            continue
        if "time" not in keyframe:
            errors.append(f"{kpath}.time is required")
            continue
        try:
            time_value = float(keyframe["time"])
        except (TypeError, ValueError):
            errors.append(f"{kpath}.time must be a number")
            continue
        if time_value < 0 or time_value > duration:
            errors.append(f"{kpath}.time outside scene duration 0..{duration}")
        seen_times.append(time_value)
        ease = keyframe.get("ease", "linear")
        if ease not in EASING_TYPES:
            errors.append(f"{kpath}.ease unsupported easing: {ease}")
        for key in keyframe:
            if key not in {"time", "ease", "x", "y", "opacity", "scale"}:
                errors.append(f"{kpath}.{key} unsupported keyframe property")
        for prop in ("x", "y", "opacity", "scale"):
            if prop in keyframe:
                if prop not in allowed_props:
                    errors.append(f"{kpath}.{prop} is not supported on this layer type")
                    continue
                try:
                    value = float(keyframe[prop])
                except (TypeError, ValueError):
                    errors.append(f"{kpath}.{prop} must be a number")
                    continue
                if prop == "scale" and value <= 0:
                    errors.append(f"{kpath}.scale must be > 0")
                if prop == "opacity" and not 0 <= value <= 1:
                    errors.append(f"{kpath}.opacity should be between 0 and 1")
    if seen_times != sorted(seen_times):
        errors.append(f"{path}.keyframes must be in increasing time order")


def validate_animation(errors: list[str], path: str, layer: dict[str, Any], *, layer_type: str, allowed_props: set[str]) -> None:
    animate = layer.get("animate")
    if not animate:
        return
    if layer_type not in {"media", "panel", "lower_third"}:
        errors.append(f"{path}.animate is not supported for {layer_type} layers")
        return
    if isinstance(animate, str):
        if animate not in ANIMATION_PRESETS and animate != "off":
            errors.append(f"{path}.animate unsupported preset: {animate}")
        if animate == "pop" and layer_type != "media":
            errors.append(f"{path}.animate pop uses scale and is only supported for media layers")
        return
    if not isinstance(animate, dict):
        errors.append(f"{path}.animate must be a string or object")
        return
    known = {"type", "in", "out", "duration", "in_duration", "out_duration", "distance", "ease", "in_ease", "out_ease"}
    for key in animate:
        if key not in known:
            errors.append(f"{path}.animate.{key} unsupported animation option")
    for key in ("type", "in", "out"):
        if key in animate and animate[key] not in ANIMATION_PRESETS and animate[key] != "off":
            errors.append(f"{path}.animate.{key} unsupported preset: {animate[key]}")
    if animate.get("in") == "fade_out" or animate.get("type") == "fade_out":
        errors.append(f"{path}.animate.in cannot use fade_out; use fade/fade_in for entrance or set animate.out")
    if animate.get("out") == "fade_in":
        errors.append(f"{path}.animate.out cannot use fade_in; use fade/fade_out for exit")
    for key in ("duration", "in_duration", "out_duration", "distance"):
        if key in animate:
            validate_positive_number(errors, f"{path}.animate.{key}", animate[key], allow_zero=(key != "distance"))
    for key in ("ease", "in_ease", "out_ease"):
        if key in animate and animate[key] not in EASING_TYPES:
            errors.append(f"{path}.animate.{key} unsupported easing: {animate[key]}")
    if layer_type != "media" and any(preset in {"pop"} for preset in (animate.get("type"), animate.get("in"), animate.get("out"))):
        errors.append(f"{path}.animate pop uses scale and is only supported for media layers")


def validate_shape_layer(errors: list[str], path: str, layer: dict[str, Any]) -> None:
    shape = layer.get("shape") or layer.get("name")
    if not shape:
        errors.append(f"{path}.shape is required for shape layers")
        return
    if shape not in SHAPE_NAMES:
        errors.append(f"{path}.shape unsupported shape: {shape}")
        return
    if shape == "progress_bar":
        value = layer.get("value", layer.get("progress", 0.5))
        try:
            value_number = float(value)
            if not 0 <= value_number <= 1:
                errors.append(f"{path}.value should be between 0 and 1")
        except (TypeError, ValueError):
            errors.append(f"{path}.value must be a number")
    if shape == "checkbox" and "checked" in layer and not isinstance(layer["checked"], bool):
        errors.append(f"{path}.checked must be a boolean")
    if shape == "arrow":
        direction = layer.get("direction", "right")
        if direction not in {"left", "right", "up", "down"}:
            errors.append(f"{path}.direction unsupported arrow direction: {direction}")
    if shape in {"speech_bubble", "file_icon", "window"}:
        for field in ("fill", "background", "text_color", "title_color", "chrome_color", "fold_color"):
            validate_color(errors, f"{path}.{field}", layer.get(field))


def validate_preset_layer(errors: list[str], path: str, layer: dict[str, Any]) -> None:
    preset = layer.get("preset") or layer.get("name")
    if not preset:
        errors.append(f"{path}.preset is required for preset layers")
        return
    if preset not in PRESET_NAMES:
        errors.append(f"{path}.preset unsupported preset: {preset}")
        return
    needs_text = {"error_dialog", "stamp", "file_label", "terminal_prompt", "warning_banner"}
    if preset in needs_text and not (layer.get("text") or layer.get("message")):
        errors.append(f"{path}.text is required for {preset} presets")
    if preset == "meme_caption" and not (layer.get("top") or layer.get("bottom") or layer.get("text")):
        errors.append(f"{path}.top, {path}.bottom, or {path}.text is required for meme_caption presets")
    if preset == "form_field" and not (layer.get("label") or layer.get("text") or layer.get("value")):
        errors.append(f"{path}.label, {path}.value, or {path}.text is required for form_field presets")
    for field in ("fill", "button_color", "text_color", "label_color", "border_color", "color"):
        validate_color(errors, f"{path}.{field}", layer.get(field))


def validate_layer(errors: list[str], path: str, layer: Any, *, scene_duration_value: float) -> None:
    if not isinstance(layer, dict):
        errors.append(f"{path} must be an object")
        return
    layer_type = layer.get("type") or ("media" if layer.get("source") else "panel")
    if layer_type not in LAYER_TYPES:
        errors.append(f"{path}.type unsupported layer type: {layer_type}")
        return
    start = layer.get("start", 0)
    end = layer.get("end", scene_duration_value)
    validate_positive_number(errors, f"{path}.start", start, allow_zero=True)
    validate_positive_number(errors, f"{path}.end", end, allow_zero=False)
    try:
        if float(start) >= float(end):
            errors.append(f"{path}.start must be before end")
        if float(end) > scene_duration_value:
            errors.append(f"{path}.end exceeds scene duration {scene_duration_value}")
    except (TypeError, ValueError):
        pass
    if layer_type == "media":
        source = layer.get("source")
        if not source:
            errors.append(f"{path}.source is required for media layers")
        else:
            source_path = Path(source).expanduser()
            if not source_path.exists():
                errors.append(f"{path}.source not found: {source_path}")
        fit = layer.get("fit", "contain")
        if fit not in FIT_TYPES:
            errors.append(f"{path}.fit unsupported fit: {fit}")
    for field in ("width", "height"):
        if field in layer:
            validate_positive_number(errors, f"{path}.{field}", layer[field])
    for field in ("border", "radius"):
        if field in layer:
            validate_positive_number(errors, f"{path}.{field}", layer[field], allow_zero=True)
    if "opacity" in layer:
        validate_positive_number(errors, f"{path}.opacity", layer["opacity"], allow_zero=True)
        try:
            if float(layer["opacity"]) > 1:
                errors.append(f"{path}.opacity should be between 0 and 1")
        except (TypeError, ValueError):
            pass
    if "scale" in layer:
        validate_positive_number(errors, f"{path}.scale", layer["scale"])
    validate_color(errors, f"{path}.color", layer.get("color"))
    validate_color(errors, f"{path}.panel_color", layer.get("panel_color"))
    validate_color(errors, f"{path}.border_color", layer.get("border_color"))
    validate_color(errors, f"{path}.background", layer.get("background"))
    validate_color(errors, f"{path}.fill", layer.get("fill"))
    if layer_type == "shape":
        validate_shape_layer(errors, path, layer)
    elif layer_type == "preset":
        validate_preset_layer(errors, path, layer)
    if layer_type == "media":
        allowed_keyframe_props = {"x", "y", "opacity", "scale"}
    elif layer_type in {"panel", "lower_third"}:
        allowed_keyframe_props = {"x", "y", "opacity"}
    elif layer_type == "shape":
        allowed_keyframe_props = {"opacity"}
    else:
        allowed_keyframe_props = set()
    validate_animation(errors, path, layer, layer_type=layer_type, allowed_props=allowed_keyframe_props)
    if layer.get("keyframes") and not allowed_keyframe_props:
        errors.append(f"{path}.keyframes are not supported for {layer_type} layers; use media/panel layers for animated properties")
    else:
        validate_keyframes(errors, path, layer, scene_duration_value, allowed_props=allowed_keyframe_props)


def validate_scene(errors: list[str], path: str, scene: Any) -> None:
    if not isinstance(scene, dict):
        errors.append(f"{path} must be an object")
        return
    kind = scene.get("type", "card")
    if kind not in SCENE_TYPES:
        errors.append(f"{path}.type unsupported scene type: {kind}")
    duration = scene.get("duration", 2.0)
    validate_positive_number(errors, f"{path}.duration", duration)
    try:
        duration_value = float(duration)
    except (TypeError, ValueError):
        duration_value = 0.0
    validate_audio(errors, f"{path}.audio", scene.get("audio"))
    validate_transition(errors, f"{path}.transition", scene.get("transition"))
    validate_color(errors, f"{path}.background", scene.get("background"))
    validate_color(errors, f"{path}.background2", scene.get("background2"))
    validate_color(errors, f"{path}.accent", scene.get("accent"))
    if kind in {"image", "media"}:
        source = scene.get("source")
        if not source:
            errors.append(f"{path}.source is required for media scenes")
        else:
            source_path = Path(source).expanduser()
            if not source_path.exists():
                errors.append(f"{path}.source not found: {source_path}")
        fit = scene.get("fit", "contain")
        if fit not in FIT_TYPES:
            errors.append(f"{path}.fit unsupported fit: {fit}")
        camera = scene.get("camera") or {}
        if isinstance(camera, dict):
            camera_kind = camera.get("type", "none")
            if camera_kind not in CAMERA_TYPES:
                errors.append(f"{path}.camera.type unsupported camera: {camera_kind}")
        else:
            errors.append(f"{path}.camera must be an object")
    layers = scene.get("layers") or []
    if kind == "layered" and not layers:
        errors.append(f"{path}.layers needs at least one layer")
    if layers and not isinstance(layers, list):
        errors.append(f"{path}.layers must be a list")
    elif isinstance(layers, list):
        for idx, layer in enumerate(layers):
            validate_layer(errors, f"{path}.layers[{idx}]", layer, scene_duration_value=duration_value)


def validate_spec(spec: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    validate_size(errors, "size", spec.get("size", "1280x720"))
    validate_positive_number(errors, "fps", spec.get("fps", 24))
    validate_transition(errors, "transition", spec.get("transition"))
    scenes = spec.get("scenes") or []
    if not isinstance(scenes, list) or not scenes:
        errors.append("scenes must be a non-empty list")
    elif isinstance(scenes, list):
        for idx, scene in enumerate(scenes):
            validate_scene(errors, f"scenes[{idx}]", scene)
    audio = spec.get("audio") or {}
    if audio:
        if not isinstance(audio, dict):
            errors.append("audio must be an object")
        else:
            validate_audio(errors, "audio.bed", audio.get("bed"))
    return errors


def assert_valid_spec(spec: dict[str, Any]) -> None:
    errors = validate_spec(spec)
    if errors:
        raise SystemExit("validation failed:\n" + "\n".join(f"- {error}" for error in errors))


def render_spec(spec: dict[str, Any], out: Path, ffmpeg: str) -> None:
    assert_valid_spec(spec)
    w, h = parse_size(spec.get("size", "1280x720"))
    fps = int(spec.get("fps", 24))
    scenes = spec.get("scenes") or []
    if not scenes:
        raise SystemExit("spec has no scenes")
    with tempfile.TemporaryDirectory(prefix="vidkit-") as tmp:
        tmpdir = Path(tmp)
        clips: list[Path] = []
        for idx, scene in enumerate(scenes):
            clip = tmpdir / f"scene-{idx:03d}.mp4"
            render_scene(scene, clip, w=w, h=h, fps=fps, ffmpeg=ffmpeg)
            clips.append(clip)
        default_transition = spec.get("transition")
        has_transitions = bool(default_transition) or any(scene.get("transition") for scene in scenes)
        assembled = tmpdir / "assembled.mp4"
        if has_transitions:
            concat_with_transitions(clips, scenes, assembled, ffmpeg, default_transition)
        else:
            concat(clips, assembled, ffmpeg)
        audio_config = spec.get("audio") or {}
        if audio_config.get("bed"):
            apply_audio_bed(assembled, out, ffmpeg, audio_config, estimated_total_duration(scenes, default_transition))
        else:
            shutil.copy2(assembled, out)


def main() -> int:
    p = argparse.ArgumentParser(description="Render small original videos from scene specs.")
    p.add_argument("source", help="JSON scene spec, 'demo', 'template:<name>', or command: templates/init/show/validate")
    p.add_argument("out", type=Path, nargs="?")
    p.add_argument("extra", type=Path, nargs="?")
    p.add_argument("--validate-only", action="store_true", help="validate the spec and exit without rendering")
    p.add_argument("--ffmpeg", default=ffmpeg_bin())
    args = p.parse_args()
    source = args.source

    if source in {"templates", "list-templates"}:
        if args.out is not None or args.extra is not None:
            raise SystemExit("usage: vidkit templates")
        print("\n".join(TEMPLATE_NAMES))
        return 0

    if source == "init":
        if args.out is None or args.extra is None:
            raise SystemExit("usage: vidkit init <template-name|demo> <out.json>")
        spec = source_spec(str(args.out))
        assert_valid_spec(spec)
        args.extra.parent.mkdir(parents=True, exist_ok=True)
        args.extra.write_text(json.dumps(portable_spec(spec), indent=2) + "\n", encoding="utf-8")
        copy_bundled_assets(spec, args.extra.parent)
        print(f"wrote {args.extra}")
        return 0

    if source == "show":
        if args.out is None:
            raise SystemExit("usage: vidkit show <spec|demo|template:name|template-name>")
        if args.extra is not None:
            raise SystemExit("usage: vidkit show <spec|demo|template:name|template-name>")
        spec = source_spec(str(args.out))
        assert_valid_spec(spec)
        print_json(spec)
        return 0

    if source == "validate":
        if args.out is None:
            raise SystemExit("usage: vidkit validate <spec|demo|template:name>")
        if args.extra is not None:
            raise SystemExit("usage: vidkit validate <spec|demo|template:name>")
        source = str(args.out)
        args.validate_only = True
        args.out = None
    if args.extra is not None:
        raise SystemExit("too many arguments")
    spec = source_spec(source)
    assert_valid_spec(spec)
    if args.validate_only:
        print("valid")
        return 0
    if args.out is None:
        raise SystemExit("output path required unless --validate-only is set")
    ffmpeg = ensure_tool(args.ffmpeg)
    render_spec(spec, args.out, ffmpeg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
