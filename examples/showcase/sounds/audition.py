"""Audition clip of the showcase sounds (repo venv; sounds/README.md, A8).

Every sound dry, one after the other, loudness-matched to -23 LUFS so that they can be compared,
with its name on screen: loops play for 5 s (with their seam in the middle), one-shots as they
are (the footsteps as a walk, one step every 0.5 s; a one-shot shorter than 1 s four times, 0.6 s
apart). Writes ``<out>/audition.wav`` and, with
ffmpeg, ``<out>/audition.mp4``.

    .venv/bin/python examples/showcase/sounds/audition.py [--out out/showcase/sounds] [NAME ...]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pyloudnorm
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont

RATE = 48000
TARGET_LUFS = -23.0
GAP_S = 0.8
LOOP_S = 5.0


def load(path: Path) -> np.ndarray:
    x, rate = sf.read(path, always_2d=True)
    assert rate == RATE, path
    return x if x.shape[1] == 2 else np.repeat(x, 2, axis=1)


def segment(out: Path, name: str, loop: bool) -> np.ndarray:
    if name == "footsteps":
        steps = [load(out / f"footstep_{i}.wav") for i in range(1, 5)]
        x = np.zeros((int(8 * 0.5 * RATE + RATE), 2))
        for i in range(8):
            s = steps[i % 4]
            a = int(i * 0.5 * RATE)
            x[a:a + len(s)] += s
        return x
    x = load(out / f"{name}.wav")
    if not loop and len(x) < RATE:  # a short one-shot (a hit) four times, 0.6 s apart
        hits = np.zeros((int(3 * 0.6 * RATE) + len(x) + RATE // 2, 2))
        for i in range(4):
            hits[int(i * 0.6 * RATE):int(i * 0.6 * RATE) + len(x)] += x
        return hits
    if loop:  # the loop's end joined to its start, the seam in the middle of the excerpt
        n = int(LOOP_S * RATE)
        idx = (np.arange(n) - n // 2) % len(x)
        x = x[idx]
    return x


def slide(path: Path, title: str, note: str) -> None:
    img = Image.new("RGB", (1280, 720), (18, 22, 29))
    d = ImageDraw.Draw(img)
    bold = ImageFont.truetype("DejaVuSans-Bold.ttf", 72)
    small = ImageFont.truetype("DejaVuSans.ttf", 34)
    d.text((110, 280), title, font=bold, fill=(243, 240, 234))
    d.text((110, 390), note, font=small, fill=(245, 165, 36))
    img.save(path)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", default="out/showcase/sounds")
    p.add_argument("names", nargs="*")
    a = p.parse_args()
    out = Path(a.out)
    facts = {**json.loads((out / "make.json").read_text()), **json.loads((out / "fetch.json").read_text())}
    names = a.names or [n for n in facts if not n.startswith("footstep_") and n not in ("sine_1k", "noise_pink", "click")]
    if not a.names:
        names.append("footsteps")
    meter = pyloudnorm.Meter(RATE)
    parts, cues, t = [], [], 0.0
    for name in names:
        loop = facts.get(name, {}).get("loop", False)
        x = segment(out, name, loop)
        x *= 10 ** ((TARGET_LUFS - meter.integrated_loudness(x)) / 20)
        source = facts.get(name, facts.get("footstep_1", {})).get("page", "synthesized (make.py)")
        cues.append((t, len(x) / RATE + GAP_S, name, f"{'loop' if loop else 'one-shot'} · {source}"))
        parts += [x, np.zeros((int(GAP_S * RATE), 2))]
        t += len(x) / RATE + GAP_S
    audio = np.concatenate(parts)
    peak = np.abs(audio).max()
    if peak > 0.89:
        audio *= 0.89 / peak
    wav = out / "audition.wav"
    sf.write(wav, audio, RATE, subtype="PCM_24")
    print(f"wrote {wav}: {len(audio) / RATE:.1f} s, {len(names)} sounds at {TARGET_LUFS} LUFS each")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return
    with tempfile.TemporaryDirectory() as tmp:
        lines = []
        for i, (_, dur, name, note) in enumerate(cues):
            png = Path(tmp) / f"{i:03d}.png"
            slide(png, name, note)
            lines += [f"file '{png}'", f"duration {dur:.3f}"]
        lines.append(f"file '{png}'")
        (Path(tmp) / "list.txt").write_text("\n".join(lines) + "\n")
        mp4 = out / "audition.mp4"
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(Path(tmp) / "list.txt"),
                        "-i", str(wav), "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-c:a", "aac", "-b:a", "256k",
                        "-shortest", str(mp4)], check=True)
        print(f"wrote {mp4}")


if __name__ == "__main__":
    main()
