"""Render report (``<mix>.report.json``).

Metrics: sample peak, true peak (4x oversampling), integrated loudness (pyloudnorm, ITU-R BS.1770),
per-source statistics and warnings from the render. The report is how agents verify renders without
listening (NFR-6). The debug plot and loudness range follow in Phase 3.

Format: docs/spec/cli.md#report-mixreportjson.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pyloudnorm
from scipy.signal import resample_poly

from soundstage.engine.filters import gain_to_db
from soundstage.engine.render import RenderResult
from soundstage.engine.scene import Scene


def _db(value: float) -> float | None:
    """dB value rounded for JSON; None for silence."""
    return None if value <= 0 else round(float(gain_to_db(value)), 2)


def metrics(audio: np.ndarray, rate: int) -> dict:
    peak = float(np.abs(audio).max()) if audio.size else 0.0
    true_peak = float(np.abs(resample_poly(audio, 4, 1, axis=0)).max()) if audio.size else 0.0
    lufs = None
    if len(audio) >= int(0.4 * rate) and peak > 0:
        value = pyloudnorm.Meter(rate).integrated_loudness(audio)
        lufs = round(float(value), 2) if np.isfinite(value) else None
    return {"peak_dbfs": _db(peak), "true_peak_dbtp": _db(true_peak), "lufs_integrated": lufs}


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
        "sources": result.sources,
        "cuts": [float(c) for c in scene.cuts],
        "warnings": result.warnings,
        "timing_s": result.timing_s,
    }


def write_report(path: str | Path, report: dict) -> Path:
    path = Path(path)
    path.write_text(json.dumps(report, indent=2) + "\n")
    return path
