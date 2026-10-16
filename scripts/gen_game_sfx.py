#!/usr/bin/env python3
"""Synthesize tiny game SFX (WAV) for web + mobile. No external deps."""
import math
import os
import struct
import wave

SR = 44100
OUT_DIRS = [
    "/app/frontend/public/sfx",
    "/app/mobile/assets/sfx",
]


def _env(i, n, attack=0.01, release=0.25):
    t = i / SR
    dur = n / SR
    a = min(1.0, t / attack) if attack > 0 else 1.0
    rem = dur - t
    r = min(1.0, rem / release) if release > 0 else 1.0
    return max(0.0, a * r)


def tone(freq, dur, vol=0.5, attack=0.005, release=0.3, decay=0.0):
    n = int(SR * dur)
    out = []
    for i in range(n):
        t = i / SR
        d = math.exp(-decay * t) if decay else 1.0
        s = math.sin(2 * math.pi * freq * t)
        # a touch of 2nd harmonic for a bell-ish timbre
        s += 0.3 * math.sin(2 * math.pi * freq * 2 * t)
        out.append(s * vol * d * _env(i, n, attack, release))
    return out


def noise(dur, vol=0.4, attack=0.002, release=0.05, decay=18.0):
    import random
    rnd = random.Random(7)
    n = int(SR * dur)
    out = []
    for i in range(n):
        t = i / SR
        d = math.exp(-decay * t)
        out.append((rnd.uniform(-1, 1)) * vol * d * _env(i, n, attack, release))
    return out


def chirp(f0, f1, dur, vol=0.5):
    n = int(SR * dur)
    out = []
    for i in range(n):
        t = i / SR
        f = f0 + (f1 - f0) * (t / dur)
        out.append(math.sin(2 * math.pi * f * t) * vol * _env(i, n, 0.005, 0.12))
    return out


def mix_seq(segments):
    """segments = list of (start_sec, samples)."""
    total = max(int(s * SR) + len(buf) for s, buf in segments)
    acc = [0.0] * total
    for s, buf in segments:
        off = int(s * SR)
        for i, v in enumerate(buf):
            acc[off + i] += v
    peak = max((abs(x) for x in acc), default=1.0) or 1.0
    if peak > 1.0:
        acc = [x / peak for x in acc]
    return acc


def write_wav(name, samples):
    data = b"".join(struct.pack("<h", int(max(-1, min(1, s)) * 32767)) for s in samples)
    for d in OUT_DIRS:
        os.makedirs(d, exist_ok=True)
        with wave.open(os.path.join(d, name), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(data)
    print("wrote", name, len(samples) / SR, "s")


# win — bright ascending arpeggio C5 E5 G5 C6
write_wav("win.wav", mix_seq([
    (0.00, tone(523.25, 0.18, 0.5, decay=6)),
    (0.09, tone(659.25, 0.18, 0.5, decay=6)),
    (0.18, tone(783.99, 0.20, 0.55, decay=6)),
    (0.30, tone(1046.5, 0.45, 0.6, release=0.4, decay=4)),
]))

# spin — short mechanical tick
write_wav("spin.wav", mix_seq([
    (0.00, tone(1200, 0.05, 0.45, attack=0.001, release=0.03, decay=30)),
]))

# reveal — quick sparkle up-chirp
write_wav("reveal.wav", mix_seq([
    (0.00, chirp(900, 1700, 0.16, 0.45)),
    (0.08, tone(2100, 0.14, 0.3, release=0.12, decay=10)),
]))

# dice — two rattly noise bursts
write_wav("dice.wav", mix_seq([
    (0.00, noise(0.09, 0.5)),
    (0.12, noise(0.10, 0.45)),
    (0.24, noise(0.08, 0.4)),
]))

# lose — soft descending two-note
write_wav("lose.wav", mix_seq([
    (0.00, tone(440, 0.18, 0.4, decay=5)),
    (0.14, tone(330, 0.30, 0.4, release=0.25, decay=5)),
]))

print("done")
