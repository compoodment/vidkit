#!/usr/bin/env python3
"""Tiny ffmpeg helper for the common video edits we keep wanting.

Commands:
  trim      - cut a clip
  contact   - generate a thumbnail sheet
  frame     - extract a still frame
  gif       - export an animated GIF
  mux-audio - attach an audio track to a video
  burnsub   - burn subtitles into a video
  crop      - crop a clip
  scale     - resize a clip
  rotate    - rotate or flip a clip
  speed     - change playback speed
  concat    - join clips together
  card      - generate a text/title-card video
  caption   - burn a text caption onto a clip
  fade      - add video/audio fade in/out
  slideshow - turn images into a simple timed video
  remix     - make a short glitchy edit from one clip
  qa        - write a quick inspection bundle for a clip
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def ffmpeg_bin(name: str | None = None) -> str:
    if name:
        return name
    return shutil.which("ffmpeg") or str(Path.home() / ".local/bin/ffmpeg")


def ensure_tool(path: str, label: str = "ffmpeg") -> str:
    if shutil.which(path) or Path(path).exists():
        return path
    raise SystemExit(f"{label} not found: {path}")


def ffprobe_bin(name: str | None = None) -> str:
    if name:
        return name
    return shutil.which("ffprobe") or str(Path.home() / ".local/bin/ffprobe")


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def run_capture(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def esc_filter_path(path: Path) -> str:
    return str(path).replace("\\", r"\\").replace(":", r"\:").replace("'", r"\'")


def parse_size(value: str) -> tuple[int, int]:
    if "x" not in value:
        raise argparse.ArgumentTypeError("size must look like 1280x720")
    w, h = value.lower().split("x", 1)
    return int(w), int(h)


def ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


def build_atempo_chain(factor: float) -> str:
    if factor <= 0:
        raise argparse.ArgumentTypeError("speed factor must be > 0")
    if abs(factor - 1.0) < 1e-6:
        return "atempo=1.0"
    parts: list[str] = []
    remaining = factor
    while remaining > 2.0:
        parts.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        parts.append("atempo=0.5")
        remaining /= 0.5
    parts.append(f"atempo={remaining:.6f}")
    return ",".join(parts)


def quote_concat_path(path: Path) -> str:
    return "file '" + str(path.resolve()).replace("'", "'\\''") + "'"


def write_ass_caption(
    text: str,
    duration: float,
    font_size: int,
    out: Path,
    *,
    width: int = 1280,
    height: int = 720,
    position: str = "bottom",
    margin: int = 52,
) -> None:
    safe = text.replace("{", "(").replace("}", ")").replace("\n", r"\N")
    alignment = {"bottom": 2, "center": 5, "top": 8}[position]
    out.write_text(
        f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H99000000,1,0,0,0,100,100,0,0,4,0,0,{alignment},60,60,{margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,{ass_time(duration)},Default,,0,0,0,,{safe}
""",
        encoding="utf-8",
    )


def probe_duration(path: Path, ffprobe: str | None = None) -> float:
    probe = ensure_tool(ffprobe_bin(ffprobe), label="ffprobe")
    out = subprocess.run(
        [probe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()
    return float(out)


def probe_json(path: Path, ffprobe: str | None = None) -> dict:
    probe = ensure_tool(ffprobe_bin(ffprobe), label="ffprobe")
    out = run_capture([
        probe,
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(path),
    ]).stdout
    return json.loads(out)


def has_audio(path: Path, ffprobe: str | None = None) -> bool:
    probe = ensure_tool(ffprobe_bin(ffprobe), label="ffprobe")
    cmd = [probe, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)]
    out = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, text=True).stdout.strip()
    return bool(out)


def parse_volumedetect(stderr: str) -> dict[str, float | None]:
    result: dict[str, float | None] = {"mean_volume_db": None, "max_volume_db": None}
    for key, label in (("mean_volume_db", "mean_volume"), ("max_volume_db", "max_volume")):
        match = re.search(rf"{label}:\s*(-?(?:inf|\d+(?:\.\d+)?)) dB", stderr)
        if match:
            result[key] = float("-inf") if match.group(1) == "-inf" else float(match.group(1))
    return result


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--ffmpeg", default=ffmpeg_bin(), help="ffmpeg executable")


def cmd_trim(args: argparse.Namespace) -> int:
    ffmpeg = ensure_tool(args.ffmpeg)
    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        args.start,
        "-to",
        args.end,
        "-i",
        str(args.input),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-r",
        str(args.fps),
        "-movflags",
        "+faststart",
        "-vf",
        "setpts=PTS-STARTPTS",
        "-af",
        "asetpts=PTS-STARTPTS",
        str(args.out),
    ]
    run(cmd)
    return 0


def cmd_contact(args: argparse.Namespace) -> int:
    ffmpeg = ensure_tool(args.ffmpeg)
    cols = args.cols
    rows = args.rows or max(1, math.ceil(args.count / cols))
    scale = args.scale
    vf = f"fps=1/{args.interval},scale={scale}:-1:flags=lanczos,tile={cols}x{rows}"
    cmd = [ffmpeg, "-y", "-i", str(args.input), "-frames:v", "1", "-update", "1", "-vf", vf, str(args.out)]
    run(cmd)
    return 0


def cmd_frame(args: argparse.Namespace) -> int:
    ffmpeg = ensure_tool(args.ffmpeg)
    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        args.time,
        "-i",
        str(args.input),
        "-frames:v",
        "1",
        "-update",
        "1",
        "-q:v",
        str(args.quality),
        str(args.out),
    ]
    run(cmd)
    return 0


def cmd_gif(args: argparse.Namespace) -> int:
    ffmpeg = ensure_tool(args.ffmpeg)
    with tempfile.TemporaryDirectory(prefix="gif-palette-") as tmp:
        tmpdir = Path(tmp)
        palette = tmpdir / "palette.png"
        chain = []
        if args.start:
            chain.append(f"trim=start={args.start}:duration={args.duration}")
            chain.append("setpts=PTS-STARTPTS")
        elif args.duration:
            chain.append(f"trim=duration={args.duration}")
            chain.append("setpts=PTS-STARTPTS")
        chain.extend([f"fps={args.fps}", f"scale={args.width}:-1:flags=lanczos"])
        palettegen = ",".join(chain + ["palettegen"])
        paletteuse_graph = f"[0:v]{','.join(chain)}[v0];[v0][1:v]paletteuse=dither={args.dither}[v]"

        source = [ffmpeg, "-y"]
        if args.start:
            source += ["-ss", args.start]
        source += ["-i", str(args.input)]
        run(source + ["-vf", palettegen, "-frames:v", "1", "-update", "1", str(palette)])
        final = [ffmpeg, "-y"]
        if args.start:
            final += ["-ss", args.start]
        final += ["-i", str(args.input), "-i", str(palette), "-filter_complex", paletteuse_graph, "-map", "[v]", str(args.out)]
        run(final)
    return 0


def cmd_mux_audio(args: argparse.Namespace) -> int:
    ffmpeg = ensure_tool(args.ffmpeg)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(args.video),
        "-i",
        str(args.audio),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        args.audio_codec,
        "-shortest",
        "-movflags",
        "+faststart",
        str(args.out),
    ]
    run(cmd)
    return 0


def cmd_burnsub(args: argparse.Namespace) -> int:
    ffmpeg = ensure_tool(args.ffmpeg)
    vf = f"subtitles={esc_filter_path(args.subs)}"
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(args.input),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        str(args.out),
    ]
    run(cmd)
    return 0


def cmd_crop(args: argparse.Namespace) -> int:
    ffmpeg = ensure_tool(args.ffmpeg)
    x = args.x if args.x is not None else f"(in_w-{args.width})/2"
    y = args.y if args.y is not None else f"(in_h-{args.height})/2"
    vf = f"crop={args.width}:{args.height}:{x}:{y}"
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(args.input),
        "-vf",
        vf,
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
        str(args.out),
    ]
    run(cmd)
    return 0


def cmd_scale(args: argparse.Namespace) -> int:
    ffmpeg = ensure_tool(args.ffmpeg)
    width, height = args.size
    if args.fit == "stretch":
        vf = f"scale={width}:{height}:flags=lanczos"
    elif args.fit == "cover":
        vf = f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,crop={width}:{height}"
    else:
        vf = f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={args.pad_color}"
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(args.input),
        "-vf",
        vf,
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
        str(args.out),
    ]
    run(cmd)
    return 0


def cmd_rotate(args: argparse.Namespace) -> int:
    ffmpeg = ensure_tool(args.ffmpeg)
    filters = {
        "cw": "transpose=1",
        "ccw": "transpose=2",
        "180": "hflip,vflip",
        "hflip": "hflip",
        "vflip": "vflip",
    }
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(args.input),
        "-vf",
        filters[args.mode],
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
        str(args.out),
    ]
    run(cmd)
    return 0


def cmd_speed(args: argparse.Namespace) -> int:
    ffmpeg = ensure_tool(args.ffmpeg)
    vf = f"setpts=PTS/{args.factor}"
    af = build_atempo_chain(args.factor)
    cmd = [ffmpeg, "-y", "-i", str(args.input), "-map", "0:v:0", "-vf", vf, "-c:v", "libx264"]
    if has_audio(args.input):
        cmd += ["-map", "0:a?", "-af", af, "-c:a", "aac"]
    cmd += ["-movflags", "+faststart", str(args.out)]
    run(cmd)
    return 0


def cmd_concat(args: argparse.Namespace) -> int:
    ffmpeg = ensure_tool(args.ffmpeg)
    with tempfile.TemporaryDirectory(prefix="vidkit-helper-concat-") as tmp:
        list_file = Path(tmp) / "clips.txt"
        list_file.write_text("\n".join(quote_concat_path(p) for p in args.inputs) + "\n")
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
        ]
        if args.fps:
            cmd += ["-r", str(args.fps)]
        cmd += ["-movflags", "+faststart", str(args.out)]
        run(cmd)
    return 0


def cmd_card(args: argparse.Namespace) -> int:
    ffmpeg = ensure_tool(args.ffmpeg)
    width, height = args.size
    with tempfile.TemporaryDirectory(prefix="vidkit-helper-card-") as tmp:
        subs = Path(tmp) / "card.ass"
        write_ass_caption(
            args.text,
            args.duration,
            args.font_size,
            subs,
            width=width,
            height=height,
            position=args.position,
            margin=args.margin,
        )
        vf = f"subtitles={esc_filter_path(subs)}"
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={args.background}:s={width}x{height}:r={args.fps}:d={args.duration}",
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(args.out),
        ]
        run(cmd)
    return 0


def cmd_caption(args: argparse.Namespace) -> int:
    ffmpeg = ensure_tool(args.ffmpeg)
    duration = args.duration or probe_duration(args.input)
    width, height = args.size
    with tempfile.TemporaryDirectory(prefix="vidkit-helper-caption-") as tmp:
        subs = Path(tmp) / "caption.ass"
        write_ass_caption(
            args.text,
            duration,
            args.font_size,
            subs,
            width=width,
            height=height,
            position=args.position,
            margin=args.margin,
        )
        vf = f"subtitles={esc_filter_path(subs)}"
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(args.input),
            "-vf",
            vf,
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
            str(args.out),
        ]
        run(cmd)
    return 0


def cmd_fade(args: argparse.Namespace) -> int:
    ffmpeg = ensure_tool(args.ffmpeg)
    duration = args.duration or probe_duration(args.input)
    filters = []
    if args.fade_in > 0:
        filters.append(f"fade=t=in:st=0:d={args.fade_in}")
    if args.fade_out > 0:
        start = max(0.0, duration - args.fade_out)
        filters.append(f"fade=t=out:st={start}:d={args.fade_out}")
    vf = ",".join(filters) if filters else "null"
    cmd = [ffmpeg, "-y", "-i", str(args.input), "-map", "0:v:0", "-vf", vf, "-c:v", "libx264"]
    if has_audio(args.input):
        afilters = []
        if args.fade_in > 0:
            afilters.append(f"afade=t=in:st=0:d={args.fade_in}")
        if args.fade_out > 0:
            start = max(0.0, duration - args.fade_out)
            afilters.append(f"afade=t=out:st={start}:d={args.fade_out}")
        cmd += ["-map", "0:a?", "-af", ",".join(afilters) if afilters else "anull", "-c:a", "aac"]
    cmd += ["-movflags", "+faststart", str(args.out)]
    run(cmd)
    return 0


def cmd_slideshow(args: argparse.Namespace) -> int:
    ffmpeg = ensure_tool(args.ffmpeg)
    width, height = args.size
    with tempfile.TemporaryDirectory(prefix="vidkit-helper-slideshow-") as tmp:
        tmpdir = Path(tmp)
        clips: list[Path] = []
        for idx, image in enumerate(args.images):
            clip = tmpdir / f"slide-{idx:03d}.mp4"
            vf = f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={args.background},setsar=1"
            run([
                ffmpeg,
                "-y",
                "-loop",
                "1",
                "-t",
                str(args.duration_per_image),
                "-i",
                str(image),
                "-vf",
                vf,
                "-r",
                str(args.fps),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(clip),
            ])
            clips.append(clip)
        list_file = tmpdir / "slides.txt"
        list_file.write_text("\n".join(quote_concat_path(p) for p in clips) + "\n")
        run([
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(args.out),
        ])
    return 0


def cmd_remix(args: argparse.Namespace) -> int:
    ffmpeg = ensure_tool(args.ffmpeg)
    width, height = args.size
    vf_parts = [
        f"trim=duration={args.duration}",
        "setpts=PTS-STARTPTS",
        f"fps={args.fps}",
        f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos",
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black",
        "setsar=1",
        f"eq=contrast={args.contrast}:saturation={args.saturation}",
        f"hue=h={args.hue}*sin(2*PI*t)",
        f"noise=alls={args.noise}:allf=t+u",
    ]
    vf = ",".join(vf_parts)
    with tempfile.TemporaryDirectory(prefix="vidkit-helper-remix-") as tmp:
        tmpdir = Path(tmp)
        if args.text:
            caption = tmpdir / "caption.ass"
            write_ass_caption(args.text, args.duration, args.font_size, caption)
            vf = f"{vf},subtitles={esc_filter_path(caption)}"
        cmd = [ffmpeg, "-y"]
        if args.start:
            cmd += ["-ss", args.start]
        cmd += ["-i", str(args.input), "-map", "0:v:0", "-vf", vf]
        cmd += [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
        ]
        if has_audio(args.input):
            cmd += ["-map", "0:a?", "-af", "volume=0.8,atempo=1.0", "-c:a", "aac", "-shortest"]
        cmd += [str(args.out)]
        run(cmd)
    return 0


def cmd_qa(args: argparse.Namespace) -> int:
    ffmpeg = ensure_tool(args.ffmpeg)
    probe = ensure_tool(ffprobe_bin(args.ffprobe), label="ffprobe")
    args.out.mkdir(parents=True, exist_ok=True)

    probe_data = probe_json(args.input, probe)
    (args.out / "probe.json").write_text(json.dumps(probe_data, indent=2) + "\n", encoding="utf-8")
    duration = float((probe_data.get("format") or {}).get("duration") or probe_duration(args.input, probe))
    streams = probe_data.get("streams") or []
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]

    contact = args.out / "contact.jpg"
    rows = max(1, math.ceil(args.contact_count / args.contact_cols))
    interval = max(0.1, duration / max(1, args.contact_count))
    run([
        ffmpeg,
        "-y",
        "-i",
        str(args.input),
        "-frames:v",
        "1",
        "-update",
        "1",
        "-vf",
        f"fps=1/{interval},scale={args.contact_scale}:-1:flags=lanczos,tile={args.contact_cols}x{rows}",
        str(contact),
    ])

    frame_paths: list[str] = []
    frame_count = max(1, args.frames)
    for idx in range(frame_count):
        fraction = (idx + 1) / (frame_count + 1)
        timestamp = max(0.0, min(duration, duration * fraction))
        frame_path = args.out / f"frame-{idx + 1:02d}.jpg"
        run([
            ffmpeg,
            "-y",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            str(args.input),
            "-frames:v",
            "1",
            "-update",
            "1",
            "-q:v",
            "2",
            str(frame_path),
        ])
        frame_paths.append(frame_path.name)

    audio_report = args.out / "audio-levels.txt"
    audio_levels: dict[str, float | None] = {"mean_volume_db": None, "max_volume_db": None}
    audio_status = "no_audio_stream"
    effectively_silent = False
    if audio_streams:
        level_cmd = [
            ffmpeg,
            "-hide_banner",
            "-i",
            str(args.input),
            "-map",
            "0:a:0",
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ]
        completed = subprocess.run(level_cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        audio_report.write_text(completed.stderr, encoding="utf-8")
        audio_levels = parse_volumedetect(completed.stderr)
        max_volume = audio_levels.get("max_volume_db")
        effectively_silent = max_volume is None or max_volume == float("-inf") or max_volume <= args.silence_threshold
        audio_status = "effectively_silent" if effectively_silent else "audible"
    else:
        audio_report.write_text("no audio stream detected\n", encoding="utf-8")

    summary = {
        "input": str(args.input),
        "duration": duration,
        "video_streams": len(video_streams),
        "audio_streams": len(audio_streams),
        "audio_status": audio_status,
        "effectively_silent": effectively_silent,
        "silence_threshold_db": args.silence_threshold,
        "mean_volume_db": audio_levels.get("mean_volume_db"),
        "max_volume_db": audio_levels.get("max_volume_db"),
        "artifacts": {
            "probe": "probe.json",
            "contact": contact.name,
            "frames": frame_paths,
            "audio_report": audio_report.name,
        },
    }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"wrote QA bundle: {args.out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Tiny ffmpeg helper for video edits.")
    sp = p.add_subparsers(dest="cmd", required=True)

    t = sp.add_parser("trim", help="cut a clip")
    t.add_argument("input", type=Path)
    t.add_argument("start", help="start time, e.g. 00:00:05.0")
    t.add_argument("end", help="end time, e.g. 00:00:12.5")
    t.add_argument("out", type=Path)
    t.add_argument("--fps", type=int, default=24, help="output fps")
    add_common(t)
    t.set_defaults(func=cmd_trim)

    c = sp.add_parser("contact", help="generate a thumbnail sheet")
    c.add_argument("input", type=Path)
    c.add_argument("out", type=Path)
    c.add_argument("--interval", type=float, default=5.0, help="seconds between thumbnails")
    c.add_argument("--count", type=int, default=12, help="approximate thumbnails to sample")
    c.add_argument("--cols", type=int, default=4, help="columns in the sheet")
    c.add_argument("--rows", type=int, default=0, help="rows in the sheet; 0 means auto")
    c.add_argument("--scale", type=int, default=320, help="thumbnail width")
    add_common(c)
    c.set_defaults(func=cmd_contact)

    f = sp.add_parser("frame", help="extract a still frame")
    f.add_argument("input", type=Path)
    f.add_argument("out", type=Path)
    f.add_argument("--time", default="00:00:01.0", help="frame timestamp")
    f.add_argument("--quality", type=int, default=2, help="jpeg quality (lower is better)")
    add_common(f)
    f.set_defaults(func=cmd_frame)

    g = sp.add_parser("gif", help="export an animated GIF")
    g.add_argument("input", type=Path)
    g.add_argument("out", type=Path)
    g.add_argument("--start", default="", help="optional start time")
    g.add_argument("--duration", type=float, default=4.0, help="gif duration")
    g.add_argument("--fps", type=int, default=12)
    g.add_argument("--width", type=int, default=640)
    g.add_argument("--dither", default="sierra2_4a")
    add_common(g)
    g.set_defaults(func=cmd_gif)

    m = sp.add_parser("mux-audio", help="attach an audio track to a video")
    m.add_argument("video", type=Path)
    m.add_argument("audio", type=Path)
    m.add_argument("out", type=Path)
    m.add_argument("--audio-codec", default="aac")
    add_common(m)
    m.set_defaults(func=cmd_mux_audio)

    s = sp.add_parser("burnsub", help="burn subtitles into a video")
    s.add_argument("input", type=Path)
    s.add_argument("subs", type=Path)
    s.add_argument("out", type=Path)
    add_common(s)
    s.set_defaults(func=cmd_burnsub)

    r = sp.add_parser("crop", help="crop a clip")
    r.add_argument("input", type=Path)
    r.add_argument("out", type=Path)
    r.add_argument("width", type=int, help="crop width")
    r.add_argument("height", type=int, help="crop height")
    r.add_argument("--x", default=None, help="crop x offset; default is centered")
    r.add_argument("--y", default=None, help="crop y offset; default is centered")
    add_common(r)
    r.set_defaults(func=cmd_crop)

    sc = sp.add_parser("scale", help="resize a clip")
    sc.add_argument("input", type=Path)
    sc.add_argument("out", type=Path)
    sc.add_argument("size", type=parse_size, help="output size, e.g. 1280x720")
    sc.add_argument("--fit", choices=["contain", "cover", "stretch"], default="contain")
    sc.add_argument("--pad-color", default="black", help="pad color for contain mode")
    add_common(sc)
    sc.set_defaults(func=cmd_scale)

    ro = sp.add_parser("rotate", help="rotate or flip a clip")
    ro.add_argument("input", type=Path)
    ro.add_argument("out", type=Path)
    ro.add_argument("mode", choices=["cw", "ccw", "180", "hflip", "vflip"])
    add_common(ro)
    ro.set_defaults(func=cmd_rotate)

    p2 = sp.add_parser("speed", help="change playback speed")
    p2.add_argument("input", type=Path)
    p2.add_argument("out", type=Path)
    p2.add_argument("factor", type=float, help="speed factor, e.g. 0.5 or 1.5 or 2.0")
    add_common(p2)
    p2.set_defaults(func=cmd_speed)

    co = sp.add_parser("concat", help="join clips together")
    co.add_argument("out", type=Path)
    co.add_argument("inputs", nargs="+", type=Path, help="clips to join, in order")
    co.add_argument("--fps", type=int, default=0, help="optional output fps")
    add_common(co)
    co.set_defaults(func=cmd_concat)

    ca = sp.add_parser("card", help="generate a text/title-card video")
    ca.add_argument("out", type=Path)
    ca.add_argument("text", help="text to show; use quotes")
    ca.add_argument("--duration", type=float, default=3.0)
    ca.add_argument("--size", type=parse_size, default=(1280, 720), help="output size, e.g. 1280x720")
    ca.add_argument("--fps", type=int, default=24)
    ca.add_argument("--background", default="black")
    ca.add_argument("--font-size", type=int, default=64)
    ca.add_argument("--position", choices=["top", "center", "bottom"], default="center")
    ca.add_argument("--margin", type=int, default=52)
    add_common(ca)
    ca.set_defaults(func=cmd_card)

    cap = sp.add_parser("caption", help="burn a text caption onto a clip")
    cap.add_argument("input", type=Path)
    cap.add_argument("out", type=Path)
    cap.add_argument("text", help="text to show; use quotes")
    cap.add_argument("--duration", type=float, default=0.0, help="caption duration; default probes input duration")
    cap.add_argument("--size", type=parse_size, default=(1280, 720), help="subtitle layout size")
    cap.add_argument("--font-size", type=int, default=48)
    cap.add_argument("--position", choices=["top", "center", "bottom"], default="bottom")
    cap.add_argument("--margin", type=int, default=52)
    add_common(cap)
    cap.set_defaults(func=cmd_caption)

    fa = sp.add_parser("fade", help="add video/audio fade in/out")
    fa.add_argument("input", type=Path)
    fa.add_argument("out", type=Path)
    fa.add_argument("--fade-in", type=float, default=0.35)
    fa.add_argument("--fade-out", type=float, default=0.35)
    fa.add_argument("--duration", type=float, default=0.0, help="input duration; default probes input duration")
    add_common(fa)
    fa.set_defaults(func=cmd_fade)

    sl = sp.add_parser("slideshow", help="turn images into a simple timed video")
    sl.add_argument("out", type=Path)
    sl.add_argument("images", nargs="+", type=Path)
    sl.add_argument("--duration-per-image", type=float, default=2.0)
    sl.add_argument("--size", type=parse_size, default=(1280, 720), help="output size, e.g. 1280x720")
    sl.add_argument("--fps", type=int, default=24)
    sl.add_argument("--background", default="black")
    add_common(sl)
    sl.set_defaults(func=cmd_slideshow)

    re = sp.add_parser("remix", help="make a short glitchy edit from one clip")
    re.add_argument("input", type=Path)
    re.add_argument("out", type=Path)
    re.add_argument("--start", default="", help="optional start time")
    re.add_argument("--duration", type=float, default=6.0)
    re.add_argument("--size", type=parse_size, default=(1280, 720), help="output size, e.g. 1280x720")
    re.add_argument("--fps", type=int, default=24)
    re.add_argument("--text", default="HELPFUL NOISE", help="caption text")
    re.add_argument("--font-size", type=int, default=48)
    re.add_argument("--contrast", type=float, default=1.35)
    re.add_argument("--saturation", type=float, default=1.65)
    re.add_argument("--hue", type=float, default=22.0, help="animated hue swing amount")
    re.add_argument("--noise", type=int, default=16, help="video noise strength")
    add_common(re)
    re.set_defaults(func=cmd_remix)

    qa = sp.add_parser("qa", help="write a quick inspection bundle for a clip")
    qa.add_argument("input", type=Path)
    qa.add_argument("--out", required=True, type=Path, help="output directory for probe, frames, contact sheet, and summary")
    qa.add_argument("--frames", type=int, default=3, help="representative frame count")
    qa.add_argument("--contact-count", type=int, default=12, help="approximate contact sheet thumbnails")
    qa.add_argument("--contact-cols", type=int, default=4, help="contact sheet columns")
    qa.add_argument("--contact-scale", type=int, default=240, help="contact thumbnail width")
    qa.add_argument("--silence-threshold", type=float, default=-50.0, help="max_volume dBFS at or below this is effectively silent")
    qa.add_argument("--ffprobe", default=ffprobe_bin(), help="ffprobe executable")
    add_common(qa)
    qa.set_defaults(func=cmd_qa)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
