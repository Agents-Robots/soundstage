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


@pytest.fixture
def make_scene(tmp_path):
    """Build and load a scene. ``positions`` is (S, 3) static or (N, S, 3) per baked frame."""

    def make(sources, positions=None, *, frame_start=1, frame_end=60, fps=30, fps_base=1.0, settings=None):
        manifest = build_manifest(sources=sources, frame_start=frame_start, frame_end=frame_end,
                                  fps=fps, fps_base=fps_base, settings=settings)
        frames = np.arange(frame_start, frame_end + 2, dtype=np.float64)
        n_tracks = sum(1 for s in manifest["sources"] if s["track"] is not None)
        pos = np.zeros((len(frames), n_tracks, 3))
        if positions is not None:
            positions = np.asarray(positions, dtype=np.float64)
            pos[:] = positions if positions.ndim == 3 else positions[None]
        arrays = {"frames": frames, "listener_matrix": static_listener(len(frames)),
                  "listener_index": np.zeros(len(frames), np.int16), "cuts": np.zeros(0), "src_pos": pos}
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


def onset(x: np.ndarray, threshold: float = 1e-6) -> int:
    """First sample whose absolute value (any channel) exceeds the threshold."""
    a = np.abs(x).max(axis=1) if x.ndim == 2 else np.abs(x)
    return int(np.argmax(a > threshold))
