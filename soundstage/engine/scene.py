"""Load, validate and represent a scene file (scene.json + scene.npz).

- Check ``format`` and ``version``; refuse unknown versions (ADR 0004). Check the arrays' shapes,
  so a hand-made scene file fails with a message instead of deep inside a render.
- Apply ``--set`` overrides to the scene settings and validate them with ``blender.schema``.
- ``Scene`` and ``Source`` dataclasses with time-base helpers (frame -> seconds -> samples with
  ``fps / fps_base``, exact for 29.97).
- ``build_manifest`` and ``write_scene`` for tests and hand-made scenes without Blender.

Spec: docs/spec/scene-format.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from soundstage.blender import schema

FORMAT = "soundstage.scene"
VERSION = 1


class SceneError(Exception):
    """Invalid or unsupported scene file."""


@dataclass
class Source:
    id: str
    track: int | None
    params: dict  # resolved tag parameters (docs/spec/tagging.md)

    @property
    def spatial(self) -> bool:
        return bool(self.params["spatial"])

    @property
    def group(self) -> str:
        return self.params["group"]


@dataclass
class Scene:
    path: Path
    manifest: dict
    settings: dict
    sources: list[Source]
    frames: np.ndarray  # (N,) baked frame numbers
    listener_matrix: np.ndarray  # (N, 4, 4)
    listener_index: np.ndarray  # (N,)
    cuts: np.ndarray  # (C,) frames
    src_pos: np.ndarray  # (N, S, 3)
    src_fwd: np.ndarray | None = None  # (N, S, 3) emitter forward vectors (absent: omnidirectional)
    src_cuts: np.ndarray = field(default_factory=lambda: np.zeros((0, 2)))  # (K, 2) (track, frame)
    vis_frames: np.ndarray | None = None  # (M,) frames of the visibility samples
    src_visibility: np.ndarray | None = None  # (M, S, bands) open share of each band
    warnings: list[str] = field(default_factory=list)

    @property
    def fps(self) -> float:
        t = self.manifest["time"]
        return t["fps"] / t["fps_base"]

    @property
    def frame_start(self) -> int:
        return self.manifest["time"]["frame_start"]

    @property
    def frame_end(self) -> int:
        return self.manifest["time"]["frame_end"]

    @property
    def visibility_bands(self) -> list[float]:
        occ = self.manifest.get("occlusion") or {}
        return occ.get("bands_hz", [250.0, 1000.0, 4000.0])

    @property
    def sample_rate(self) -> int:
        return int(self.settings["sample_rate"])

    def seconds(self, frame) -> np.ndarray | float:
        """Time of a frame relative to the first frame of the shot."""
        return (np.asarray(frame, dtype=np.float64) - self.frame_start) / self.fps

    def sample_of(self, frame: float) -> int:
        """Output sample index of a frame (sample 0 = frame_start)."""
        return int(round((frame - self.frame_start) * self.sample_rate / self.fps))

    def length_samples(self, frame_a: int | None = None, frame_b: int | None = None) -> int:
        """Samples from the start of frame_a to the end of frame_b (default: the whole shot)."""
        a = self.frame_start if frame_a is None else frame_a
        b = self.frame_end if frame_b is None else frame_b
        return self.sample_of(b + 1) - self.sample_of(a)


def parse_overrides(pairs: list[str]) -> dict:
    """``["key=value", ...]`` from the command line into typed settings."""
    out = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep:
            raise SceneError(f"--set expects key=value, got {pair!r}")
        try:
            out[key.strip()] = schema.parse_value(key.strip(), value.strip())
        except ValueError as e:
            raise SceneError(str(e)) from None
    return out


def check_arrays(arrays: dict[str, np.ndarray], manifest: dict, where: Path) -> None:
    """Shapes and consistency of the scene.npz arrays (docs/spec/scene-format.md#scenenpz)."""
    for key in ("frames", "listener_matrix", "src_pos"):
        if key not in arrays:
            raise SceneError(f"{where}: array {key!r} missing")
    frames = arrays["frames"]
    n = len(frames)
    if frames.ndim != 1 or n < 1 or np.any(np.diff(frames) <= 0):
        raise SceneError(f"{where}: 'frames' must be a non-empty, strictly increasing 1-D array")
    t = manifest.get("time", {})
    if n and not (frames[0] <= t.get("frame_start", frames[0]) and t.get("frame_end", frames[-1]) <= frames[-1]):
        raise SceneError(f"{where}: 'frames' ({frames[0]:g}..{frames[-1]:g}) do not cover the shot "
                         f"{t.get('frame_start')}-{t.get('frame_end')}")
    shapes = {"listener_matrix": (n, 4, 4), "listener_index": (n,)}
    for key, shape in shapes.items():
        if key in arrays and arrays[key].shape != shape:
            raise SceneError(f"{where}: {key!r} has shape {arrays[key].shape}, expected {shape}")
    pos = arrays["src_pos"]
    if pos.shape[0] != n or (pos.size and (pos.ndim != 3 or pos.shape[2] != 3)):
        raise SceneError(f"{where}: 'src_pos' has shape {pos.shape}, expected ({n}, tracks, 3)")
    if "src_fwd" in arrays and arrays["src_fwd"].shape != pos.shape:
        raise SceneError(f"{where}: 'src_fwd' has shape {arrays['src_fwd'].shape}, expected {pos.shape}")
    if ("vis_frames" in arrays) != ("src_visibility" in arrays):
        raise SceneError(f"{where}: 'vis_frames' and 'src_visibility' go together")
    if "src_visibility" in arrays:
        vis, m = arrays["src_visibility"], len(arrays["vis_frames"])
        bands = len((manifest.get("occlusion") or {}).get("bands_hz", [250.0, 1000.0, 4000.0]))
        tracks = pos.shape[1] if pos.ndim == 3 else 0
        if vis.shape != (m, tracks, bands):
            raise SceneError(f"{where}: 'src_visibility' has shape {vis.shape}, expected ({m}, {tracks}, {bands})")


def load_scene(path: str | Path, overrides: dict | None = None) -> Scene:
    path = Path(path)
    try:
        manifest = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise SceneError(f"cannot read {path}: {e}") from None
    if manifest.get("format") != FORMAT:
        raise SceneError(f"{path}: not a {FORMAT} file")
    if manifest.get("version") != VERSION:
        raise SceneError(f"{path}: unsupported version {manifest.get('version')} (supported: {VERSION})")

    settings = {**manifest.get("settings", {}), **(overrides or {})}
    errors = schema.validate_settings(settings)
    if errors:
        raise SceneError("settings: " + "; ".join(errors))
    settings = schema.resolve_settings(settings)

    sources = []
    for raw in manifest["sources"]:
        params = {k: v for k, v in raw.items() if k in schema.SOURCE_KEYS}
        errors = schema.validate_source(params)
        if errors:
            raise SceneError(f"source {raw.get('id')}: " + "; ".join(errors))
        params = schema.resolve_source(params, default_id=raw.get("id"))
        sources.append(Source(id=params["id"], track=raw.get("track"), params=params))

    arrays_path = path.parent / manifest.get("arrays", "scene.npz")
    try:
        with np.load(arrays_path) as a:
            arrays = {k: a[k] for k in a.files}
    except (OSError, ValueError) as e:
        raise SceneError(f"cannot read {arrays_path}: {e}") from None
    check_arrays(arrays, manifest, arrays_path)

    n_tracks = arrays["src_pos"].shape[1] if arrays["src_pos"].ndim == 3 else 0
    for s in sources:
        if s.spatial and (s.track is None or not 0 <= s.track < n_tracks):
            raise SceneError(f"source {s.id}: track {s.track} not in scene.npz")
    return Scene(
        path=path,
        manifest=manifest,
        settings=settings,
        sources=sources,
        frames=arrays["frames"].astype(np.float64),
        listener_matrix=arrays["listener_matrix"].astype(np.float64),
        listener_index=arrays.get("listener_index", np.zeros(len(arrays["frames"]), np.int16)),
        cuts=arrays.get("cuts", np.zeros(0)),
        src_pos=arrays["src_pos"].astype(np.float64).reshape(len(arrays["frames"]), n_tracks, 3),
        src_fwd=(arrays["src_fwd"].astype(np.float64).reshape(len(arrays["frames"]), n_tracks, 3)
                 if "src_fwd" in arrays else None),
        src_cuts=arrays.get("src_cuts", np.zeros((0, 2))).reshape(-1, 2),
        vis_frames=arrays["vis_frames"].astype(np.float64) if "vis_frames" in arrays else None,
        src_visibility=arrays["src_visibility"].astype(np.float64) if "src_visibility" in arrays else None,
        warnings=list(manifest.get("warnings", [])),
    )


def build_manifest(
    *,
    sources: list[dict],
    frame_start: int = 1,
    frame_end: int = 100,
    fps: float = 30,
    fps_base: float = 1.0,
    substeps: int = 1,
    settings: dict | None = None,
) -> dict:
    """A complete manifest from partial source entries; spatial sources get tracks in order."""
    resolved, track = [], 0
    for i, entry in enumerate(sources):
        errors = schema.validate_source(entry)
        if errors:
            raise SceneError(f"source {i}: " + "; ".join(errors))
        r = schema.resolve_source(entry, default_id=f"source:{i}")
        r["track"] = track if r["spatial"] else None
        track += 1 if r["spatial"] else 0
        resolved.append(r)
    return {
        "format": FORMAT,
        "version": VERSION,
        "generator": {"tool": "soundstage.engine.scene.build_manifest"},
        "time": {
            "fps": fps,
            "fps_base": fps_base,
            "frame_start": frame_start,
            "frame_end": frame_end,
            "substeps": substeps,
            "pad_frames_before": 0,
            "pad_frames_after": 0,
        },
        "units": {"scale_length": 1.0},
        "settings": schema.resolve_settings(settings or {}),
        "listener": {"objects": ["listener"]},
        "sources": resolved,
        "arrays": "scene.npz",
        "warnings": [],
    }


def write_scene(directory: str | Path, manifest: dict, arrays: dict[str, np.ndarray]) -> Path:
    """Write scene.json and scene.npz; return the path of scene.json."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(directory / manifest.get("arrays", "scene.npz"), **arrays)
    out = directory / "scene.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    return out
