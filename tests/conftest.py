"""Shared fixtures: synthetic scenes without Blender, generated samples, measurement helpers."""

from __future__ import annotations

import shutil

import numpy as np
import pytest
import soundfile as sf

from soundstage.engine.scene import build_manifest, load_scene, write_scene

RATE = 48000


def pytest_collection_modifyitems(config, items):
    if shutil.which("blender"):
        return
    skip = pytest.mark.skip(reason="blender not on PATH")
    for item in items:
        if "blender" in item.keywords:
            item.add_marker(skip)


def static_listener(n: int) -> np.ndarray:
    """Listener at the origin looking along +Y (Blender camera rotated 90 degrees about X)."""
    m = np.eye(4)
    m[:3, :3] = [[1, 0, 0], [0, 0, -1], [0, 1, 0]]  # camera -Z (forward) = world +Y
    return np.repeat(m[None], n, axis=0)


def listener_at(positions: np.ndarray) -> np.ndarray:
    """Listener matrices looking along +Y at the given positions (N, 3)."""
    m = static_listener(len(positions))
    m[:, :3, 3] = positions
    return m


@pytest.fixture
def make_scene(tmp_path):
    """Build and load a scene. ``positions`` is (S, 3) static or (N, S, 3) per baked sample.

    Baked samples run from ``frame_start`` to ``frame_end + 1`` with ``substeps`` per frame.
    ``listener`` (N, 4, 4) replaces the static listener at the origin; ``cuts`` are frames where
    the listener changes (camera switches); ``src_fwd`` (N, S, 3) gives emitter forward vectors.
    """

    def make(sources, positions=None, *, frame_start=1, frame_end=60, fps=30, fps_base=1.0, settings=None,
             substeps=1, listener=None, cuts=(), src_fwd=None):
        manifest = build_manifest(sources=sources, frame_start=frame_start, frame_end=frame_end,
                                  fps=fps, fps_base=fps_base, substeps=substeps, settings=settings)
        frames = frame_start + np.arange((frame_end + 1 - frame_start) * substeps + 1) / substeps
        n_tracks = sum(1 for s in manifest["sources"] if s["track"] is not None)
        pos = np.zeros((len(frames), n_tracks, 3))
        if positions is not None:
            positions = np.asarray(positions, dtype=np.float64)
            pos[:] = positions if positions.ndim == 3 else positions[None]
        index = np.zeros(len(frames), np.int16)
        for c in cuts:
            index[frames >= c] += 1
        arrays = {"frames": frames, "listener_matrix": static_listener(len(frames)) if listener is None else listener,
                  "listener_index": index, "cuts": np.asarray(cuts, dtype=np.float64), "src_pos": pos}
        if src_fwd is not None:
            arrays["src_fwd"] = np.asarray(src_fwd, dtype=np.float64)
        return load_scene(write_scene(tmp_path / "scene", manifest, arrays))

    return make


@pytest.fixture
def wav(tmp_path):
    """Write a sample file and return its path."""

    def write(name, data, rate=RATE):
        path = tmp_path / name
        sf.write(path, data, rate, subtype="FLOAT")
        return str(path)

    return write


@pytest.fixture
def sine(wav):
    t = np.arange(RATE * 2) / RATE
    return wav("sine.wav", 0.5 * np.sin(2 * np.pi * 1000 * t))


@pytest.fixture
def click(wav):
    x = np.zeros(RATE // 2)
    x[0] = 1.0
    return wav("click.wav", x)


def rms_db(x: np.ndarray) -> float:
    return 20 * np.log10(np.sqrt(np.mean(np.square(x))))


def peak_index(x: np.ndarray) -> int:
    """Sample of the largest absolute value (any channel): where a click lands."""
    a = np.abs(x).max(axis=1) if x.ndim == 2 else np.abs(x)
    return int(np.argmax(a))


def onset(x: np.ndarray, threshold: float = 1e-6) -> int:
    """First sample whose absolute value (any channel) exceeds the threshold."""
    a = np.abs(x).max(axis=1) if x.ndim == 2 else np.abs(x)
    return int(np.argmax(a > threshold))


def frequency(x: np.ndarray, rate: int = RATE) -> float:
    """Frequency of a sine from sub-sample zero crossings (mono)."""
    z = np.nonzero((x[:-1] <= 0) & (x[1:] > 0))[0]
    t = z + x[z] / (x[z] - x[z + 1])
    return (len(t) - 1) / ((t[-1] - t[0]) / rate)
