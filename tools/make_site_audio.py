"""Make the sound clips of the project page in site/audio/ (run in the repo venv).

One clip per card of the page's "What you hear" section: the pass of the card's showcase section in
which its effect is on (``out/showcase/<section>``, built by ``examples/showcase``), cut sample-exact
the way the showcase assembly cuts a clip. Off passes, which the sections keep only as references for
their checks, are never used. Each clip gets one fixed gain to -18 LUFS integrated (the sections'
reference level), so that the page's players are about equally loud; within a clip nothing is
normalized or limited, so its level changes are the engine's. The gain is lowered where the clip's
true peak would rise above -1.5 dBTP, which leaves room for the MP3 encoder (VBR about 190 kbit/s,
48 kHz stereo). The decoded MP3's loudness and true peak are measured and printed.

Usage::

    .venv/bin/python tools/make_site_audio.py [--only doppler,reverb] [--showcase DIR]
"""

from __future__ import annotations

import argparse
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
TARGET_LUFS = -18.0
CEILING_DBTP = -1.5


def db(x: float) -> float:
    return 20 * np.log10(max(x, 1e-12))


def make(name: str, clip: Clip) -> str:
    """Cut, level and encode one clip; return a line of measurements."""
    part = assemble.Part(clip, None)
    problems = [p for p in part.problems() if "picture" not in p and "frame" not in p]
    if problems:
        raise SystemExit(f"{name}: " + "; ".join(problems))
    rate = part.man["sample_rate"]
    body, _ = part.sound(rate)
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
    return (f"{name:12s} {clip.key + ':' + clip.pass_key:22s} {len(body) / rate:5.1f} s  {lufs:6.1f} LUFS {gain_db:+5.1f} dB"
            f"  -> mp3 {meter.integrated_loudness(y):6.1f} LUFS {db(mix.true_peak(y).max()):5.1f} dBTP"
            f"  {out.stat().st_size // 1024} kB")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--only", default="", help=f"comma-separated clips (default: all): {', '.join(CLIPS)}")
    p.add_argument("--showcase", type=Path, default=assemble.OUT, help="the rendered showcase sections")
    a = p.parse_args()
    assemble.OUT = a.showcase
    names = a.only.split(",") if a.only else list(CLIPS)
    AUDIO.mkdir(parents=True, exist_ok=True)
    for name in names:
        print(make(name, CLIPS[name]))


if __name__ == "__main__":
    main()
