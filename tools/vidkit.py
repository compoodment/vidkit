#!/usr/bin/env python3
"""Dispatcher for the vidkit command-line toolkit."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "tools" / "vidkit-compose.py"
HELPER = ROOT / "tools" / "vidkit-helper.py"
VERIFY = ROOT / "tools" / "vidkit-verify.py"
SELFTEST = ROOT / "tools" / "vidkit-selftest.py"
BLENDER = ROOT / "tools" / "vidkit-blender.py"

HELP = """vidkit - small scripted video toolkit

Usage:
  vidkit compose <vidkit-compose args>
  vidkit helper <vidkit-helper args>
  vidkit verify
  vidkit selftest
  vidkit blender <vidkit-blender args>

Shortcuts:
  vidkit templates
  vidkit template:<name> out.mp4
  vidkit contact in.mp4 out.jpg
  vidkit qa in.mp4 --out qa-dir

Legacy wrappers remain available: video-compose, video-kit, video-compose-verify, video-compose-selftest.
"""

COMPOSE_SHORTCUTS = {"templates", "init", "show", "validate", "--validate-only", "demo"}
HELPER_SHORTCUTS = {
    "trim",
    "contact",
    "frame",
    "gif",
    "mux-audio",
    "burnsub",
    "crop",
    "scale",
    "rotate",
    "speed",
    "concat",
    "card",
    "caption",
    "fade",
    "slideshow",
    "remix",
    "qa",
}


def run(script: Path, args: list[str]) -> int:
    return subprocess.call([sys.executable, str(script), *args])


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else ""
    if cmd in {"", "-h", "--help", "help"}:
        print(HELP, end="")
        return 0
    if cmd == "compose":
        return run(COMPOSE, args[1:])
    if cmd in {"helper", "kit"}:
        return run(HELPER, args[1:])
    if cmd == "verify":
        return run(VERIFY, args[1:])
    if cmd == "selftest":
        return run(SELFTEST, args[1:])
    if cmd == "blender":
        return run(BLENDER, args[1:])
    if cmd in COMPOSE_SHORTCUTS or cmd.startswith("template:") or cmd.endswith(".json"):
        return run(COMPOSE, args)
    if cmd in HELPER_SHORTCUTS:
        return run(HELPER, args)
    print(f"vidkit: unknown command {cmd!r}", file=sys.stderr)
    print("try: vidkit --help", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
