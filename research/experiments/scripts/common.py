"""Shared helpers for the experiment scripts: paths, synthetic scenes, measurements, figures.

Scripts run in the repo venv from the repository root, e.g.
``.venv/bin/python research/experiments/scripts/e03_interpolators.py``. They print markdown tables
(pasted into the experiment write-ups) and write figures to research/figures/.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

REPO = Path(__file__).resolve().parents[3]
FIGURES = REPO / "research" / "figures"
RATE = 48000
sys.path.insert(0, str(REPO))

from soundstage.engine import render  # noqa: E402
from soundstage.engine.scene import build_manifest, load_scene, write_scene  # noqa: E402


def figure_path(name: str) -> Path:
    FIGURES.mkdir(parents=True, exist_ok=True)
    return FIGURES / name


def save(fig, name: str) -> None:
    path = figure_path(name)
    fig.savefig(path, dpi=90, bbox_inches="tight")
    print(f"\nfigure: {path.relative_to(REPO)}")


def table(header: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def listener_at(positions: np.ndarray) -> np.ndarray:
    """Listener matrices looking along world +Y at the given positions (N, 3)."""
    m = np.repeat(np.eye(4)[None], len(positions), axis=0)
    m[:, :3, :3] = [[1, 0, 0], [0, 0, -1], [0, 1, 0]]
    m[:, :3, 3] = positions
    return m


def scene(sources: list[dict], positions, *, frame_end: int = 60, fps: int = 30, listener=None, cuts=(),
          settings: dict | None = None, directory: Path | None = None, visibility=None, frame=None):
    """A loaded synthetic scene; ``positions`` (S, 3) static or (N, S, 3) per baked frame;
    ``visibility`` is (frames (M,), values (M, S, bands 250/1000/4000 Hz)) for occlusion; ``frame``
    the listener's frame edges (x / -z of left and right), constant (2,) or per baked frame (N, 2)."""
    directory = directory or Path(tempfile.mkdtemp(prefix="soundstage_exp_"))
    manifest = build_manifest(sources=sources, frame_end=frame_end, fps=fps, settings=settings)
    frames = np.arange(1, frame_end + 2, dtype=float)
    pos = np.asarray(positions, dtype=float)
    pos = pos if pos.ndim == 3 else np.repeat(pos[None], len(frames), axis=0)
    index = np.zeros(len(frames), np.int16)
    for c in cuts:
        index[frames >= c] += 1
    arrays = {"frames": frames, "listener_matrix": listener_at(np.zeros((len(frames), 3))) if listener is None
              else listener, "listener_index": index, "cuts": np.asarray(cuts, float), "src_pos": pos}
    if frame is not None:
        arrays["listener_frame"] = np.broadcast_to(np.asarray(frame, dtype=float), (len(frames), 2)).copy()
    if visibility is not None:
        arrays["vis_frames"] = np.asarray(visibility[0], dtype=np.float64)
        arrays["src_visibility"] = np.asarray(visibility[1], dtype=np.float32)
        manifest["occlusion"] = {"bands_hz": [250.0, 1000.0, 4000.0]}
    return load_scene(write_scene(directory, manifest, arrays))


def sample(name: str, data: np.ndarray, directory: Path | None = None) -> str:
    directory = directory or Path(tempfile.mkdtemp(prefix="soundstage_exp_"))
    path = directory / name
    sf.write(path, data, RATE, subtype="FLOAT")
    return str(path)


def sine(f: float = 1000.0, seconds: float = 2.0, amplitude: float = 0.5) -> np.ndarray:
    return amplitude * np.sin(2 * np.pi * f * np.arange(int(seconds * RATE)) / RATE)


def frequency(x: np.ndarray, rate: int = RATE) -> float:
    """Frequency of a sine from sub-sample zero crossings."""
    z = np.nonzero((x[:-1] <= 0) & (x[1:] > 0))[0]
    t = z + x[z] / (x[z] - x[z + 1])
    return (len(t) - 1) / ((t[-1] - t[0]) / rate)


def rms_db(x: np.ndarray) -> float:
    return float(20 * np.log10(np.sqrt(np.mean(np.square(x))) + 1e-300))


__all__ = ["REPO", "FIGURES", "RATE", "render", "save", "table", "scene", "sample", "sine", "frequency",
           "rms_db", "listener_at"]
