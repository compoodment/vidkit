#!/usr/bin/env python3
import math, random, sys, wave, struct
from pathlib import Path

SR = 44100
DUR = 20.0
BPM = 174
BEAT = 60.0 / BPM
N = int(SR * DUR)
random.seed(240513)
L = [0.0] * N
R = [0.0] * N

def add(i, l, r=None):
    if 0 <= i < N:
        if r is None:
            r = l
        L[i] += l
        R[i] += r

def env(t, decay):
    return math.exp(-t / decay) if t >= 0 else 0.0

def kick(t0, amp=0.92):
    start = int(t0 * SR); length = int(0.34 * SR); phase = 0.0
    for n in range(length):
        i = start + n
        if i >= N: break
        t = n / SR
        f = 45 + 105 * math.exp(-t / 0.032)
        phase += 2 * math.pi * f / SR
        v = math.sin(phase) * env(t, 0.12) * amp
        v += math.sin(2 * math.pi * 35 * t) * env(t, 0.18) * amp * 0.28
        add(i, v)

def snare(t0, amp=0.72):
    start = int(t0 * SR); length = int(0.24 * SR); phase = 0.0; hp = 0.0
    for n in range(length):
        i = start + n
        if i >= N: break
        t = n / SR
        x = random.random() * 2 - 1
        noise = x - hp; hp = x
        phase += 2 * math.pi * 190 / SR
        v = (noise * env(t, 0.055) * 0.6 + math.sin(phase) * env(t, 0.09) * 0.45) * amp
        add(i, v * 0.96, v * 1.04)

def hat(t0, amp=0.2, decay=0.026, pan=0.0):
    start = int(t0 * SR); length = int(0.09 * SR); last = 0.0
    for n in range(length):
        i = start + n
        if i >= N: break
        t = n / SR
        x = random.random() * 2 - 1
        hp = x - last; last = x
        v = hp * env(t, decay) * amp
        add(i, v * (1 - pan), v * (1 + pan))

def reese(t0, dur, note=35, amp=0.34, wob=2.6):
    start = int(t0 * SR); length = int(dur * SR)
    f = 440 * 2 ** ((note - 69) / 12)
    p1 = p2 = 0.0; lp = 0.0
    for n in range(length):
        i = start + n
        if i >= N: break
        t = n / SR
        p1 = (p1 + f * 0.997 / SR) % 1.0
        p2 = (p2 + f * 1.006 / SR) % 1.0
        saw = (2 * p1 - 1) * 0.55 + (2 * p2 - 1) * 0.45
        sub = math.sin(2 * math.pi * (f / 2) * t)
        gate = 0.55 + 0.45 * math.sin(2 * math.pi * wob * t + 0.8)
        target = (saw * 0.48 + sub * 0.74) * gate
        cutoff = 0.035 + 0.045 * (0.5 + 0.5 * math.sin(2 * math.pi * 0.31 * t))
        lp += (target - lp) * cutoff
        fade = min(1.0, t / 0.35, (dur - t) / 0.45)
        add(i, lp * amp * fade * 0.9, lp * amp * fade * 1.1)

def pad(t0, dur, note=58, amp=0.12):
    start = int(t0 * SR); length = int(dur * SR)
    fs = [440 * 2 ** ((note + off - 69) / 12) for off in (0, 7, 12)]
    for n in range(length):
        i = start + n
        if i >= N: break
        t = n / SR
        v = sum(math.sin(2 * math.pi * f * t + j * 1.7) for j, f in enumerate(fs)) / len(fs)
        fade = min(1.0, t / 1.5, (dur - t) / 1.5)
        pan = math.sin(2 * math.pi * 0.08 * t) * 0.25
        add(i, v * amp * fade * (1 - pan), v * amp * fade * (1 + pan))

def stab(t0, note=72, amp=0.18):
    start = int(t0 * SR); length = int(0.22 * SR)
    f = 440 * 2 ** ((note - 69) / 12)
    for n in range(length):
        i = start + n
        if i >= N: break
        t = n / SR
        v = (math.sin(2 * math.pi * f * t) + 0.5 * math.sin(2 * math.pi * f * 2.01 * t)) * env(t, 0.08) * amp
        pan = -0.3 if int(t0 / BEAT) % 2 else 0.3
        add(i, v * (1 - pan), v * (1 + pan))

# Amen-ish 2-bar loop, compressed into a 20s sketch.
beats = int(DUR / BEAT) + 4
for b in range(beats):
    t = b * BEAT
    if b % 4 in (0, 3): kick(t)
    if b % 4 == 2: snare(t)
    if b % 8 in (5, 7): snare(t, 0.32)
    hat(t, 0.13, 0.022, -0.18)
    hat(t + BEAT * 0.5, 0.18, 0.03, 0.22)
    hat(t + BEAT * 0.75, 0.09, 0.018, 0.05)
    if b % 4 == 1: kick(t + BEAT * 0.55, 0.42)
    if b % 8 in (3, 6): stab(t + BEAT * 0.25, 72 + (b % 3) * 2)

reese(0, 20, 35, 0.32, 2.1)
reese(8, 12, 30, 0.24, 3.7)
pad(0, 20, 55, 0.09)

# soft limiter / normalize
peak = max(max(abs(x) for x in L), max(abs(x) for x in R), 1e-6)
gain = min(0.96 / peak, 1.8)
out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "jungle-dnb-20s.wav"
out.parent.mkdir(parents=True, exist_ok=True)
with wave.open(str(out), "w") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    for l, r in zip(L, R):
        l = math.tanh(l * gain * 1.35)
        r = math.tanh(r * gain * 1.35)
        w.writeframes(struct.pack("<hh", int(max(-1, min(1, l)) * 32767), int(max(-1, min(1, r)) * 32767)))
print(out)
