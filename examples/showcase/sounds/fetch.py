"""Fetch and prepare the showcase's recorded sounds (runs in the repo venv; sounds/README.md).

Reads ``sources.toml``. For each recording: check the licence on its page (CC0 only), download the
file into ``<out>/download/`` unless it is there, check its SHA-256, and apply the entry's
processing (mono, or both channels with ``stereo = true`` for beds; cut, loop crossfade or
one-shot cuts, 48 kHz, peak -3 dBFS, 24 bit). Writes
``<out>/<name>.wav``, ``<out>/fetch.json`` (measures per sound) and ``<out>/credits.json`` (for the
end card).

    .venv/bin/python examples/showcase/sounds/fetch.py [--out out/showcase/sounds] [--offline]

``--offline`` uses the downloads already present and does not open the pages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import tomllib
import urllib.request
from pathlib import Path

import numpy as np
import soundfile as sf
import soxr

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from kit import measure  # noqa: E402

RATE = 48000
PEAK_DB = -3.0
CC0 = "creativecommons.org/publicdomain/zero/1.0/"
HEADERS = {"User-Agent": "Mozilla/5.0 (soundstage showcase fetch)"}


def get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=60) as r:
        return r.read()


def freesound_preview(page_url: str) -> str:
    """URL of the HQ preview, after checking that the page states CC0 and nothing else."""
    page = get(page_url).decode("utf-8", "replace")
    licences = {m.split("&")[0] for m in re.findall(r"creativecommons\.org/[^\"\s]+", page)}
    if licences != {CC0}:
        raise SystemExit(f"{page_url}: licence {sorted(licences)}, not CC0 only")
    return re.search(r'data-mp3="([^"]+)"', page).group(1).replace("-lq.mp3", "-hq.mp3")


def download(rec: dict, folder: Path, offline: bool) -> Path:
    path = folder / (re.sub(r"\W+", "_", rec["page"].rstrip("/").split("/")[-1]) + ".mp3")
    if not path.exists():
        if offline:
            raise SystemExit(f"{path} missing; run without --offline")
        if rec["download"] != "freesound-hq-preview":
            raise SystemExit(f"{rec['page']}: unknown download kind {rec['download']!r}")
        path.write_bytes(get(freesound_preview(rec["page"])))
        time.sleep(2)
    elif not offline and rec["download"] == "freesound-hq-preview":
        freesound_preview(rec["page"])  # the licence is checked on every online run
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != rec["sha256"]:
        raise SystemExit(f"{path}: SHA-256 {digest} differs from sources.toml")
    return path


def load(path: Path, stereo: bool = False) -> np.ndarray:
    """Mono (channels averaged), or the two channels as they are for a stereo bed (A3)."""
    x, rate = sf.read(path, always_2d=True)
    if stereo:
        if x.shape[1] != 2:
            raise SystemExit(f"{path}: stereo = true, but the file has {x.shape[1]} channel(s)")
    else:
        x = x.mean(axis=1)
    return soxr.resample(x, rate, RATE, quality="VHQ") if rate != RATE else x


def make_loop(x: np.ndarray, start: float, length: float, crossfade: float) -> np.ndarray:
    """``length`` seconds from ``start``, with the ``crossfade`` seconds that follow faded into the
    beginning (equal power), so the end joins the start without a seam."""
    a, n, c = int(start * RATE), int(length * RATE), int(crossfade * RATE)
    body, tail = x[a:a + n].copy(), x[a + n:a + n + c]
    if len(tail) < c:
        raise SystemExit(f"loop at {start} + {length} s needs {crossfade} s more recording")
    t = (0.5 * np.pi * np.arange(c) / c).reshape(-1, *[1] * (x.ndim - 1))  # broadcast over channels
    body[:c] = body[:c] * np.sin(t) + tail * np.cos(t)
    return body


def make_oneshot(x: np.ndarray, onset: float, length: float, fade_out: float) -> np.ndarray:
    a = int((onset - 0.003) * RATE)
    y = x[a:a + int(length * RATE)].copy()
    f = int(fade_out * RATE)
    y[-f:] *= np.cos(0.5 * np.pi * np.arange(f) / f) ** 2
    return y


def write(out: Path, name: str, x: np.ndarray) -> Path:
    x = x - np.mean(x, axis=0)
    x = x / np.abs(x).max() * 10 ** (PEAK_DB / 20)
    path = out / f"{name}.wav"
    sf.write(path, x, RATE, subtype="PCM_24")
    return path


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", default="out/showcase/sounds")
    p.add_argument("--offline", action="store_true")
    a = p.parse_args()
    out = Path(a.out)
    (out / "download").mkdir(parents=True, exist_ok=True)
    recordings = tomllib.loads((HERE / "sources.toml").read_text())["recording"]
    facts, credits = {}, []
    for rec in recordings:
        proc = rec["process"]
        x = load(download(rec, out / "download", a.offline), proc.get("stereo", False))
        if proc["kind"] == "loop":
            parts = {rec["names"][0]: make_loop(x, proc["start"], proc["length"], proc["crossfade"])}
        elif proc["kind"] == "oneshots":
            parts = {name: make_oneshot(x, t, proc["length"], proc["fade_out"])
                     for name, t in zip(rec["names"], proc["onsets"], strict=True)}
        else:
            raise SystemExit(f"unknown process kind {proc['kind']!r}")
        for name, y in parts.items():
            path = write(out, name, y)
            z, rate = sf.read(path, always_2d=True)
            facts[name] = {"loop": proc["kind"] == "loop", "page": rec["page"], **measure.sound_facts(z, rate, proc["kind"] == "loop")}
            print(f"{name:18s} {measure.describe(facts[name])}")
        credits.append({"author": rec["author"], "title": rec["title"], "page": rec["page"], "licence": rec["licence"],
                        "names": rec["names"]})
    (out / "fetch.json").write_text(json.dumps(facts, indent=1, sort_keys=True) + "\n")
    (out / "credits.json").write_text(json.dumps(credits, indent=1) + "\n")


if __name__ == "__main__":
    main()
