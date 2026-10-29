"""Render report (``<mix>.report.json``).

Metrics: sample peak, true peak (4x oversampling), integrated loudness (pyloudnorm, ITU-R BS.1770),
loudness range (EBU Tech 3342), per group (stems) and per source, plus the render's warnings. The
report is how agents verify renders without listening (NFR-6).

Format: docs/spec/cli.md#report-mixreportjson.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pyloudnorm
from pyloudnorm.iirfilter import IIRfilter

from soundstage.engine import mix
from soundstage.engine.filters import gain_to_db
from soundstage.engine.render import RenderResult
from soundstage.engine.scene import Scene


def _db(value: float) -> float | None:
    """dB value rounded for JSON; None for silence."""
    return None if value <= 0 else round(float(gain_to_db(value)), 2)


def _k_weighted(audio: np.ndarray, rate: int) -> np.ndarray:
    """BS.1770 K-weighting (the two pyloudnorm filter stages: high shelf, then high-pass)."""
    x = np.asarray(audio, dtype=np.float64)
    for f in (IIRfilter(4.0, 1 / np.sqrt(2), 1500.0, rate, "high_shelf"), IIRfilter(0.0, 0.5, 38.0, rate, "high_pass")):
        x = f.apply_filter(x)
    return x


def loudness_range(audio: np.ndarray, rate: int) -> float | None:
    """EBU Tech 3342 loudness range: short-term loudness (3 s windows every 0.1 s), absolute gate
    -70 LUFS, relative gate -20 LU below the gated mean, then the 10th to 95th percentile spread."""
    win, hop = int(3.0 * rate), int(0.1 * rate)
    if len(audio) < win:
        return None
    k = _k_weighted(audio if audio.ndim == 2 else audio[:, None], rate)
    power = (k ** 2).sum(axis=1)
    c = np.concatenate([[0.0], np.cumsum(power)])
    starts = np.arange(0, len(power) - win + 1, hop)
    ms = (c[starts + win] - c[starts]) / win
    st = -0.691 + 10 * np.log10(np.maximum(ms, 1e-20))
    st = st[st > -70.0]
    if len(st) < 2:
        return None
    rel = -0.691 + 10 * np.log10(np.mean(10 ** ((st + 0.691) / 10))) - 20.0
    st = st[st > rel]
    if len(st) < 2:
        return None
    return round(float(np.percentile(st, 95) - np.percentile(st, 10)), 2)


def metrics(audio: np.ndarray, rate: int) -> dict:
    peak = float(np.abs(audio).max()) if audio.size else 0.0
    true_peak = float(mix.true_peak(audio).max()) if audio.size else 0.0
    lufs = None
    if len(audio) >= int(0.4 * rate) and peak > 0:
        value = pyloudnorm.Meter(rate).integrated_loudness(audio)
        lufs = round(float(value), 2) if np.isfinite(value) else None
    return {"peak_dbfs": _db(peak), "true_peak_dbtp": _db(true_peak), "lufs_integrated": lufs,
            "loudness_range_lu": loudness_range(audio, rate) if peak > 0 else None}


def build_report(scene: Scene, result: RenderResult, output: Path, settings_overrides: dict) -> dict:
    return {
        "scene": str(scene.path.resolve()),
        "output": str(output.resolve()),
        "sample_rate": result.rate,
        "frames": list(result.frames),
        "fps": scene.fps,
        "length_samples": len(result.audio),
        "settings": scene.settings,
        "overrides": settings_overrides,
        "master": metrics(result.audio, result.rate),
        "reverb": result.reverb,
        "groups": {g: metrics(a, result.rate) for g, a in result.stems.items()},
        "sources": [{k: v for k, v in s.items() if not k.startswith("_")} for s in result.sources],
        "cuts": [float(c) for c in scene.cuts],
        "warnings": result.warnings,
        "culling": result.culling,
        "timing_s": result.timing_s,
    }


def write_report(path: str | Path, report: dict) -> Path:
    path = Path(path)
    path.write_text(json.dumps(report, indent=2) + "\n")
    return path
