"""Render benchmark for NFR-3: N sources over M minutes of a synthetic shot (no Blender).

    .venv/bin/python tools/benchmark.py [--sources 50] [--minutes 5] [--quality standard] [--workers N]

Builds a scene with a slowly moving camera and sources on straight passes at 5-60 m/s (loops) plus
one-shots every few seconds, baked at 30 fps with 4 sub-frames, renders it with the default
settings and prints the timing. Samples are generated noise and tones (seeded).
"""

from __future__ import annotations

import argparse
import tempfile
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from soundstage.engine import render
from soundstage.engine.scene import build_manifest, load_scene, write_scene

RATE = 48000


def build(directory: Path, n_sources: int, minutes: float, fps: int = 30, substeps: int = 4) -> Path:
    rng = np.random.default_rng(1)
    t = np.arange(int(4 * RATE)) / RATE
    hum = 0.3 * (np.sin(2 * np.pi * 55 * t) + 0.5 * np.sin(2 * np.pi * 110 * t)) + 0.05 * rng.standard_normal(len(t))
    sf.write(directory / "hum.wav", hum, RATE, subtype="FLOAT")
    burst = rng.standard_normal(RATE // 2) * np.exp(-np.arange(RATE // 2) / 4000) * 0.5
    sf.write(directory / "hit.wav", burst, RATE, subtype="FLOAT")

    frame_end = int(minutes * 60 * fps)
    frames = 1 + np.arange((frame_end) * substeps + 1) / substeps
    tt = (frames - 1) / fps
    sources, pos = [], []
    for i in range(n_sources):
        if i % 5 == 4:
            hits = list(np.arange(1 + i, frame_end, 3 * fps + i).astype(float))
            sources.append({"sample": str(directory / "hit.wav"), "mode": "once", "frame": hits, "ref_distance": 5.0})
        else:
            sources.append({"sample": str(directory / "hum.wav"), "ref_distance": 10.0, "pitch": 0.8 + 0.01 * i})
        speed = rng.uniform(5, 60)
        start = rng.uniform(-500, 500, 3) * [1, 1, 0.1]
        direction = rng.normal(size=3) * [1, 1, 0.1]
        direction /= np.linalg.norm(direction)
        x = start + np.outer((tt % 40.0) * speed, direction)  # repeat a 40 s pass (teleports back)
        pos.append(x)
    m = np.repeat(np.eye(4)[None], len(frames), axis=0)
    m[:, :3, :3] = [[1, 0, 0], [0, 0, -1], [0, 1, 0]]
    m[:, :3, 3] = np.stack([np.zeros_like(tt), 2.0 * tt, np.full_like(tt, 1.7)], axis=1)
    manifest = build_manifest(sources=sources, frame_start=1, frame_end=frame_end, fps=fps, substeps=substeps)
    arrays = {"frames": frames, "listener_matrix": m, "listener_index": np.zeros(len(frames), np.int16),
              "cuts": np.zeros(0), "src_pos": np.stack(pos, axis=1)}
    return write_scene(directory / "scene", manifest, arrays)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", type=int, default=50)
    ap.add_argument("--minutes", type=float, default=5.0)
    ap.add_argument("--quality", default="standard")
    ap.add_argument("--workers", type=int)
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        t0 = time.perf_counter()
        path = build(Path(tmp), a.sources, a.minutes)
        scene = load_scene(path, {"quality": a.quality})
        t1 = time.perf_counter()
        result = render.render(scene, workers=a.workers)
        t2 = time.perf_counter()
    audio_s = len(result.audio) / result.rate
    print(f"{a.sources} sources x {audio_s / 60:.1f} min, quality {a.quality}: scene {t1 - t0:.1f} s, "
          f"render {t2 - t1:.1f} s (load {result.timing_s['load']} s, dsp {result.timing_s['dsp']} s, "
          f"{result.timing_s['workers']} workers), {audio_s / (t2 - t1):.1f}x real time")
    print(f"warnings: {len(result.warnings)}; peak {20 * np.log10(np.abs(result.audio).max()):.1f} dBFS")


if __name__ == "__main__":
    main()
