"""Make the sound clips of the project page in site/audio/ (run in the repo venv).

One clip per card of the page's "What you hear" section: the pass of the card's showcase section in
which its effect is on (``out/showcase/<section>``, built by ``examples/showcase``), cut sample-exact
the way the showcase assembly cuts a clip. Off passes, which the sections keep only as references for
their checks, are never used. Each clip gets one fixed gain to -18 LUFS integrated (the sections'
reference level), so that the page's players are about equally loud; within a clip nothing is
normalized or limited, so its level changes are the engine's. The gain is lowered where the clip's
true peak would rise above -1.5 dBTP, which leaves room for the MP3 encoder (VBR about 190 kbit/s,
48 kHz stereo). The decoded MP3's loudness and true peak are measured and printed.

``hero-city``, under the title picture, is the start of the mix of the film the picture is a frame of
(``HERO_S``: the roof deck the picture shows, then the dive into the canyon). The mix lives outside this
repository, so it is passed by path with ``--hero-mix WAV``; its report next to it gives the frame
rate and the first frame. Its edges are faded (``HERO_FADE_S``), since the film's sound runs on.

Usage::

    .venv/bin/python tools/make_site_audio.py [--only doppler,reverb | --only none] [--showcase DIR]
        [--hero-mix WAV]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pyloudnorm
import soundfile as sf

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "examples" / "showcase")]

import assemble  # noqa: E402
from cuts import Clip  # noqa: E402

from soundstage.engine import mix  # noqa: E402

AUDIO = REPO / "site" / "audio"
CLIPS = {  # page clip: the pass of the showcase section shown on its card
    "distance": Clip("distance", "air"),
    "screen": Clip("screen", "screen"),
    "doppler": Clip("doppler", "siren"),
    "delay": Clip("delay", "physical"),
    "occlusion": Clip("occlusion", "bike"),
    "reverb": Clip("reverb", "church"),
    "directivity": Clip("directivity", "cones"),
    "around": Clip("around", "lap"),
    "cuts": Clip("cuts", "per_camera"),
    "city": Clip("city", "night"),
}
HERO_S = (0.0, 10.0)
"""Seconds of the title picture's film from its first frame; the picture is frame 45 (1.5 s)."""
HERO_FADE_S = (0.3, 1.0)
TARGET_LUFS = -18.0
CEILING_DBTP = -1.5


def db(x: float) -> float:
    return 20 * np.log10(max(x, 1e-12))


def make(name: str, clip: Clip) -> str:
    """Cut, level and encode one clip of the showcase; return a line of measurements."""
    part = assemble.Part(clip, None)
    problems = [p for p in part.problems() if "picture" not in p and "frame" not in p]
    if problems:
        raise SystemExit(f"{name}: " + "; ".join(problems))
    rate = part.man["sample_rate"]
    body, _ = part.sound(rate)
    return encode(name, f"{clip.key}:{clip.pass_key}", body, rate)


def make_hero(mix_wav: Path) -> str:
    """Cut ``HERO_S`` from the title picture's film mix, fade its edges, level and encode it."""
    rep = json.loads(mix_wav.with_suffix(".report.json").read_text())
    rate = rep["sample_rate"]
    if rep["frames"][0] != 1:
        raise SystemExit(f"{mix_wav}: the mix starts at frame {rep['frames'][0]}, not at the film's first frame")
    a, b = (round(t * rate) for t in HERO_S)
    body, _ = sf.read(mix_wav, start=a, stop=b, always_2d=True)
    n_in, n_out = (int(t * rate) for t in HERO_FADE_S)
    body[:n_in] *= np.sin(np.linspace(0, np.pi / 2, n_in))[:, None] ** 2
    body[-n_out:] *= np.cos(np.linspace(0, np.pi / 2, n_out))[:, None] ** 2
    return encode("hero-city", f"{mix_wav.name} {HERO_S[0]:g}-{HERO_S[1]:g} s", body, rate)


def encode(name: str, what: str, body: np.ndarray, rate: int) -> str:
    """Bring ``body`` to the target loudness under the peak cap and write site/audio/<name>.mp3."""
    meter = pyloudnorm.Meter(rate)
    lufs = meter.integrated_loudness(body)
    peak = db(mix.true_peak(body).max())
    gain_db = min(TARGET_LUFS - lufs, CEILING_DBTP - peak)
    out = AUDIO / f"{name}.mp3"
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "clip.wav"
        sf.write(wav, body * 10 ** (gain_db / 20), rate, subtype="FLOAT")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-map_metadata", "-1",
                        "-c:a", "libmp3lame", "-q:a", "2", str(out)], check=True)
        decoded = Path(tmp) / "decoded.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(out), "-c:a", "pcm_f32le", str(decoded)],
                       check=True)
        y, _ = sf.read(decoded, always_2d=True)
    return (f"{name:12s} {what:22s} {len(body) / rate:5.1f} s  {lufs:6.1f} LUFS {gain_db:+5.1f} dB"
            f"  -> mp3 {meter.integrated_loudness(y):6.1f} LUFS {db(mix.true_peak(y).max()):5.1f} dBTP"
            f"  {out.stat().st_size // 1024} kB")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--only", default="", help=f"comma-separated clips (default: all): {', '.join(CLIPS)}")
    p.add_argument("--showcase", type=Path, default=assemble.OUT, help="the rendered showcase sections")
    p.add_argument("--hero-mix", type=Path, help="mix of the title picture's film (its report next to it)")
    a = p.parse_args()
    assemble.OUT = a.showcase
    names = [] if a.only == "none" else a.only.split(",") if a.only else list(CLIPS)
    AUDIO.mkdir(parents=True, exist_ok=True)
    for name in names:
        print(make(name, CLIPS[name]))
    if a.hero_mix:
        print(make_hero(a.hero_mix))


if __name__ == "__main__":
    main()
