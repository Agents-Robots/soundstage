"""File output.

Writes the master (sample 0 = first frame of the rendered range) as WAV: 32-bit float by default,
or 24-bit PCM with TPDF dither (seeded, so output stays deterministic). Stems, limiter and loudness
normalization follow in Phase 3.

Spec: docs/spec/signal-model.md#mixing-and-output; decision: ADR 0005.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf


def write_wav(path: str | Path, audio: np.ndarray, rate: int, *, pcm24: bool = False) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if pcm24:
        lsb = 2.0 ** -23
        rng = np.random.default_rng(0)
        dither = (rng.random(audio.shape) - rng.random(audio.shape)) * lsb
        data = np.clip(audio + dither, -1.0, 1.0 - lsb)
        sf.write(path, data, rate, subtype="PCM_24")
    else:
        sf.write(path, audio.astype(np.float32), rate, subtype="FLOAT")
    return path
