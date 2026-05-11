#!/usr/bin/env python3
"""Render and probe the core vidkit templates.

Keeps verification repeatable while the composer evolves.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/vidkit/verify"
TEMPLATES = ["lower-third", "motion-card", "glitch-card", "band-glitch", "media-card", "split-screen", "chat-window", "application-form"]
CONTACTS = {"lower-third", "band-glitch", "split-screen", "chat-window", "application-form"}


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


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def ffprobe(path: Path) -> dict:
    out = run([
        bin_path("ffprobe"),
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=index,codec_name,codec_type,width,height",
        "-of",
        "json",
        str(path),
    ]).stdout
    return json.loads(out)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    summary: dict[str, dict] = {}
    for template in TEMPLATES:
        mp4 = OUT / f"{template}.mp4"
        run([wrapper_path("vidkit"), "--validate-only", f"template:{template}"])
        run([wrapper_path("vidkit"), f"template:{template}", str(mp4)])
        info = ffprobe(mp4)
        summary[template] = info
        streams = info.get("streams", [])
        has_video = any(s.get("codec_type") == "video" and s.get("width") == 640 and s.get("height") == 360 for s in streams)
        has_audio = any(s.get("codec_type") == "audio" for s in streams)
        if not has_video or not has_audio:
            raise SystemExit(f"bad streams for {template}: {streams}")
        if template in CONTACTS:
            run([bin_path("vidkit-helper"), "contact", str(mp4), str(OUT / f"{template}-contact.jpg"), "--interval", "0.8", "--cols", "4", "--scale", "240"])
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"verified {len(TEMPLATES)} templates -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
