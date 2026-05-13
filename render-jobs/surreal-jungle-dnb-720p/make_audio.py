#!/usr/bin/env python3
import math, random, wave, struct
from pathlib import Path

SR=44100
DUR=120.0
BPM=174
BEAT=60.0/BPM
N=int(SR*DUR)
random.seed(1337)

# Stereo float buffers
L=[0.0]*N
R=[0.0]*N

def add(i, l, r=None):
    if 0 <= i < N:
        if r is None: r=l
        L[i]+=l; R[i]+=r

def env_exp(t, decay):
    return math.exp(-t/decay) if t>=0 else 0

def add_kick(t0, amp=0.95):
    start=int(t0*SR); length=int(0.36*SR)
    phase=0.0
    for n in range(length):
        i=start+n
        if i>=N: break
        t=n/SR
        f=48 + 95*math.exp(-t/0.035)
        phase += 2*math.pi*f/SR
        v=math.sin(phase)*env_exp(t,0.12)*amp
        v += math.sin(2*math.pi*38*t)*env_exp(t,0.22)*0.25*amp
        add(i,v,v)

def add_snare(t0, amp=0.75):
    start=int(t0*SR); length=int(0.24*SR)
    phase=0.0
    for n in range(length):
        i=start+n
        if i>=N: break
        t=n/SR
        noise=(random.random()*2-1)*env_exp(t,0.07)
        phase += 2*math.pi*185/SR
        tone=math.sin(phase)*env_exp(t,0.09)
        crack=(random.random()*2-1)*env_exp(t,0.018)
        v=(noise*0.55+tone*0.38+crack*0.22)*amp
        add(i,v*0.95,v*1.05)

def add_hat(t0, amp=0.22, decay=0.035, pan=0.0):
    start=int(t0*SR); length=int(0.11*SR)
    last=0.0
    for n in range(length):
        i=start+n
        if i>=N: break
        t=n/SR
        x=random.random()*2-1
        hp=x-last; last=x
        v=hp*env_exp(t,decay)*amp
        add(i,v*(1-pan),v*(1+pan))

def add_ghost(t0, amp=0.18):
    add_snare(t0, amp)

def add_reese(t0, dur, note=36, amp=0.34, wob=2.0):
    start=int(t0*SR); length=int(dur*SR)
    f=440*2**((note-69)/12)
    p1=p2=0.0
    lp=0.0
    for n in range(length):
        i=start+n
        if i>=N: break
        t=n/SR
        # detuned saw-ish waves with moving lowpass amplitude
        p1=(p1+f*0.997/SR)%1.0; p2=(p2+f*1.006/SR)%1.0
        saw=(2*p1-1)*0.55+(2*p2-1)*0.45
        sub=math.sin(2*math.pi*(f/2)*t)
        gate=0.55+0.45*math.sin(2*math.pi*wob*t+0.7)
        target=(saw*0.55+sub*0.7)*gate
        lp += (target-lp)*(0.018+0.032*gate)
        fade=min(1,t/0.02,(dur-t)/0.08 if dur-t>0 else 0)
        v=lp*amp*fade
        add(i,v*0.9,v*1.1)

def add_pad(t0,dur,note=60,amp=0.08,pan=0.0):
    start=int(t0*SR); length=int(dur*SR)
    f=440*2**((note-69)/12)
    for n in range(length):
        i=start+n
        if i>=N: break
        t=n/SR
        fade=min(1,t/2.5,(dur-t)/2.5 if dur-t>0 else 0)
        trem=0.65+0.35*math.sin(2*math.pi*0.13*t)
        v=(math.sin(2*math.pi*f*t)+0.45*math.sin(2*math.pi*(f*1.5)*t))*amp*fade*trem
        add(i,v*(1-pan),v*(1+pan))

def add_riser(t0,dur,amp=0.18):
    start=int(t0*SR); length=int(dur*SR)
    for n in range(length):
        i=start+n
        if i>=N: break
        t=n/SR; u=t/dur
        f=220+1800*u*u
        v=math.sin(2*math.pi*f*t)*(u**1.7)*amp + (random.random()*2-1)*(u**2)*0.05
        pan=math.sin(2*math.pi*0.4*t)*0.55
        add(i,v*(1-pan),v*(1+pan))

# arrangement
bars=int(DUR/(BEAT*4))
# pads/chords every 16 bars
for b in range(0,bars,16):
    t=b*4*BEAT
    for note,pan in [(48,-0.25),(55,0.2),(62,0.0)]: add_pad(t,16*4*BEAT,note,0.045,pan)

# breakbeat pattern with jungle syncopation
for bar in range(bars):
    base=bar*4*BEAT
    active = not (bar%32 in [0,1] and bar>0)  # tiny breakdown openings
    if active:
        add_kick(base+0*BEAT)
        add_snare(base+1*BEAT)
        add_kick(base+1.75*BEAT,0.55)
        add_snare(base+3*BEAT)
        if bar%4 in [1,3]: add_kick(base+2.45*BEAT,0.45)
        if bar%8==7: add_ghost(base+3.55*BEAT,0.16)
    else:
        add_hat(base+0.5*BEAT,0.12,0.08)
        add_riser(base,4*BEAT,0.08)
    # hats/shuffles
    for s in range(8):
        swing=0.018 if s%2 else 0
        add_hat(base+s*0.5*BEAT+swing,0.13+0.05*(s%2),0.025, pan=(-0.35 if s%2 else 0.25))
    for s in [1.5,2.75,3.25]: add_hat(base+s*BEAT,0.09,0.018,pan=0.4)
    # bass phrases
    if active:
        seq=[36,36,39,34,36,43,41,34]
        for j,note in enumerate(seq):
            add_reese(base+j*0.5*BEAT,0.45*BEAT,note,0.20+0.05*(bar%4==2),wob=2+(bar%8)*0.12)
    if bar%16==15: add_riser(base+2*BEAT,2*BEAT,0.18)

# master soft clip/normalize
peak=0.001
for a,b in zip(L,R): peak=max(peak,abs(a),abs(b))
gain=0.92/peak
out=Path('artifacts/video-compose/surreal-jungle-dnb/jungle-dnb-bed.wav')
out.parent.mkdir(parents=True,exist_ok=True)
with wave.open(str(out),'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    for l,r in zip(L,R):
        # saturate
        l=math.tanh(l*gain*1.15); r=math.tanh(r*gain*1.15)
        w.writeframes(struct.pack('<hh', int(max(-1,min(1,l))*32767), int(max(-1,min(1,r))*32767)))
print(out)
