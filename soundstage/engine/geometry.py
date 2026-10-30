"""Trajectories and listener-relative geometry at control rate.

- Tracks: baked positions as cubic splines (scipy ``CubicSpline``, not-a-knot: exact for constant
  velocity and acceleration) per piece, and separately on each side of a kink (an acceleration above
  ``KINK_ACCELERATION`` between two samples, e.g. where keyframed motion starts or stops), so the
  velocity steps there instead of ringing; pieces are split at
  cuts and at teleports (speed between two baked samples above ``teleport_speed``). The listener
  rotation uses ``RotationSpline`` per segment. A spline is only evaluated inside its own piece and
  held at the piece's ends.
- Retarded delay: ``tau = |s(t - tau) - p(t)| / c``, two fixed-point steps then Newton steps
  (``f'(tau) = 1 + u.v / c``), with the source piece chosen by emission time. Points that do not
  converge (the gap after a source teleports away, supersonic ambiguity) are marked inaudible.
- ``Path``: everything the models need for one source on the control grid (ADR 0009). With
  ``pan_reference = "screen"`` its lateral sine follows the frame through the lens
  (``panning.screen_lateral``, from the baked frame edges).

Blender camera axes: +X right, +Y up, -Z forward.
Spec: docs/spec/signal-model.md#coordinate-frames, #trajectories-and-control-rate,
#propagation-delay-doppler-itd.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.spatial.transform import Rotation, RotationSpline

from soundstage.engine import panning
from soundstage.engine.control import CONTROL_STEP, ControlGrid  # noqa: F401  (CONTROL_STEP re-exported)

R_MIN = 0.25
"""Near-field softening distance in metres (smooth pan when a source passes through the camera)."""

FIXED_POINT_STEPS = 2
NEWTON_STEPS = 8
RETARDED_TOLERANCE_S = 1e-9
TELEPORT_FACTOR = 3.0
"""Default teleport speed as a multiple of the speed of sound."""

KINK_ACCELERATION = 200.0
"""m/s^2 (about 20 g): a larger velocity change between two baked samples is a kink, not smooth motion."""


def kinks(times: np.ndarray, positions: np.ndarray) -> np.ndarray:
    """Sample indices where the velocity jumps (keyframed motion starting, stopping, turning sharply)."""
    if len(times) < 3:
        return np.zeros(0, dtype=np.int64)
    v = np.diff(positions, axis=0) / np.diff(times)[:, None]
    accel = np.linalg.norm(np.diff(v, axis=0), axis=1) / (0.5 * (times[2:] - times[:-2]))
    return np.nonzero(accel > KINK_ACCELERATION)[0] + 1


def camera_space(listener_matrix: np.ndarray, src_pos: np.ndarray) -> np.ndarray:
    """Camera-space vectors (N, S, 3) of source positions (N, S, 3) for listener matrices (N, 4, 4)."""
    rot = listener_matrix[:, :3, :3]
    rel = src_pos - listener_matrix[:, None, :3, 3]
    return np.einsum("nji,nsj->nsi", rot, rel)


def derived(q: np.ndarray) -> dict[str, np.ndarray]:
    """Distance and direction quantities from camera-space vectors (..., 3)."""
    r = np.linalg.norm(q, axis=-1)
    r_e = np.sqrt(r * r + R_MIN * R_MIN)
    return {
        "distance": r,
        "lateral": q[..., 0] / r_e,  # lateral sine, -1 left .. +1 right
        "rear": np.maximum(0.0, q[..., 2] / r_e),  # 0 front/side .. 1 behind
    }


def piece_starts(times: np.ndarray, positions: np.ndarray, max_speed: float, cut_times=()) -> np.ndarray:
    """Indices where a new piece starts (always including 0): cuts and teleports.

    A teleport between samples k-1 and k (speed above ``max_speed``) starts a piece at k; a cut at
    time c starts a piece at the first sample at or after c.
    """
    starts = {0}
    if len(times) > 1:
        speed = np.linalg.norm(np.diff(positions, axis=0), axis=1) / np.diff(times)
        starts.update((np.nonzero(speed > max_speed)[0] + 1).tolist())
    for c in cut_times:
        k = int(np.searchsorted(times, c - 1e-9))
        if 0 < k < len(times):
            starts.add(k)
    return np.array(sorted(starts), dtype=np.int64)


class Track:
    """Piecewise interpolation of (N, D) values over baked times; held at each piece's ends."""

    def __init__(self, times: np.ndarray, values: np.ndarray, starts: np.ndarray, kind: str = "cubic"):
        self.times = times
        self.starts = starts
        self.bounds = np.append(times[starts], np.inf)  # piece j covers [bounds[j], bounds[j+1])
        self.bounds[0] = -np.inf
        self.pieces = []
        ends = np.append(starts[1:], len(times))
        breaks = set(kinks(times, values).tolist()) if kind == "cubic" else set()
        for a, b in zip(starts, ends):
            edges = [a, *sorted(k for k in breaks if a < k < b - 1), b - 1]
            segments = []
            for s0, s1 in zip(edges[:-1], edges[1:]):  # segments share their end samples
                t, v = times[s0:s1 + 1], values[s0:s1 + 1]
                if len(t) >= 3 and kind == "cubic":
                    segments.append(CubicSpline(t, v, axis=0))
                else:
                    segments.append(_Linear(t, v))
            if b - a == 1:
                fn = _Constant(values[a])
            elif len(segments) == 1:
                fn = segments[0]
            else:
                fn = _Segments(times[edges[:-1]], segments)
            self.pieces.append((times[a], times[b - 1], fn))

    def piece_of(self, t: np.ndarray) -> np.ndarray:
        return np.searchsorted(self.bounds, t, side="right") - 1

    def __call__(self, t: np.ndarray, piece: np.ndarray | None = None, nu: int = 0) -> np.ndarray:
        """Values (``nu = 0``) or time derivatives (``nu = 1``; zero where a piece is held)."""
        piece = self.piece_of(t) if piece is None else piece
        out = None
        for j in np.unique(piece):
            m = piece == j
            t0, t1, fn = self.pieces[j]
            tc = np.clip(t[m], t0, t1)
            v = fn(tc, nu)
            if nu:
                v = np.where(((t[m] >= t0) & (t[m] <= t1))[:, None], v, 0.0)
            if out is None:
                out = np.empty((len(t),) + v.shape[1:])
            out[m] = v
        return out if out is not None else np.empty((0,))


class _Linear:
    def __init__(self, t, v):
        self.t, self.v = t, v

    def __call__(self, t, nu=0):
        if nu:
            k = np.clip(np.searchsorted(self.t, t, side="right") - 1, 0, len(self.t) - 2)
            return (self.v[k + 1] - self.v[k]) / (self.t[k + 1] - self.t[k])[:, None]
        return np.stack([np.interp(t, self.t, self.v[:, i]) for i in range(self.v.shape[1])], axis=1)


class _Segments:
    """Interpolants joined at kinks (continuous position, velocity may step)."""

    def __init__(self, starts, parts):
        self.starts, self.parts = starts, parts

    def __call__(self, t, nu=0):
        idx = np.clip(np.searchsorted(self.starts, t, side="right") - 1, 0, len(self.parts) - 1)
        out = None
        for j in np.unique(idx):
            m = idx == j
            v = self.parts[j](t[m], nu)
            if out is None:
                out = np.empty((len(t),) + v.shape[1:])
            out[m] = v
        return out


class _Constant:
    def __init__(self, v):
        self.v = v

    def __call__(self, t, nu=0):
        return np.broadcast_to(self.v * (0.0 if nu else 1.0), (len(t),) + self.v.shape).copy()


class ListenerTrack:
    """Listener position (cubic per segment) and rotation (RotationSpline per segment)."""

    def __init__(self, times: np.ndarray, matrices: np.ndarray, starts: np.ndarray):
        self.position = Track(times, matrices[:, :3, 3], starts)
        self.rotations = []
        ends = np.append(starts[1:], len(times))
        for a, b in zip(starts, ends):
            rot = Rotation.from_matrix(matrices[a:b, :3, :3])
            spline = RotationSpline(times[a:b], rot) if b - a >= 2 else None
            self.rotations.append((times[a], times[b - 1], spline, rot[0]))

    def pose(self, t: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Position (n, 3), rotation matrices (n, 3, 3) and segment index (n,) at times t."""
        segment = self.position.piece_of(t)
        p = self.position(t, segment)
        rot = np.empty((len(t), 3, 3))
        for j in np.unique(segment):
            m = segment == j
            t0, t1, spline, first = self.rotations[j]
            rot[m] = spline(np.clip(t[m], t0, t1)).as_matrix() if spline is not None else first.as_matrix()
        return p, rot, segment


@dataclass
class Path:
    """Control-rate geometry of one spatial source (reception times on ``grid``)."""

    grid: ControlGrid
    tau: np.ndarray  # propagation delay (s)
    distance: np.ndarray  # propagation distance c * tau (m)
    q: np.ndarray  # camera-space vector of the retarded source position (n, 3)
    lateral: np.ndarray
    rear: np.ndarray
    cos_emit: np.ndarray  # cosine of the angle between emitter forward and the direction to the listener
    segment: np.ndarray  # listener segment
    piece: np.ndarray  # source piece (by emission time)
    audible: np.ndarray  # False where the retarded time has no solution (after a teleport away)
    visibility: np.ndarray | None = None  # (n, bands) open share per band from the bake (None: not baked)
    jumps: np.ndarray = field(default_factory=lambda: np.zeros(0, np.int64))  # control indices starting a jump
    before_bake: np.ndarray | None = None  # per control point: emission time precedes the baked range


class SceneGeometry:
    """Listener and source tracks of a scene, and per-source paths on a control grid."""

    def __init__(self, scene, grid: ControlGrid):
        self.scene = scene
        self.grid = grid
        s = scene.settings
        self.c = float(s["speed_of_sound"])
        self.max_speed = float(s["teleport_speed"] or TELEPORT_FACTOR * self.c)
        self.times = scene.seconds(scene.frames)
        cut_times = scene.seconds(np.asarray(scene.cuts, dtype=np.float64))
        lpos = scene.listener_matrix[:, :3, 3]
        self.listener = ListenerTrack(self.times, scene.listener_matrix,
                                      piece_starts(self.times, lpos, self.max_speed, cut_times))
        self.t = grid.times
        self.p, self.rot, self.segment = self.listener.pose(self.t)
        self.frame = None  # (tan left, tan right) of the frame edges per control point, for screen panning
        frame = getattr(scene, "listener_frame", None)
        if s["pan_reference"] == "screen" and frame is not None:
            self.frame = tuple(np.interp(self.t, self.times, frame[:, i]) for i in (0, 1))
        self._tracks: dict[int, tuple[Track, Track | None]] = {}

    def sub(self, j0: int, count: int) -> SceneGeometry:
        """The same geometry on control points j0 .. j0 + count - 1 of this grid (a sub-grid aligned
        with it), sharing the listener tracks; source tracks are built anew and dropped with it."""
        g = object.__new__(SceneGeometry)
        g.__dict__.update(self.__dict__)
        g.grid = ControlGrid(start=self.grid.start + j0 * self.grid.step, count=count, rate=self.grid.rate,
                             step=self.grid.step)
        sl = slice(j0, j0 + count)
        g.t, g.p, g.rot, g.segment = self.t[sl], self.p[sl], self.rot[sl], self.segment[sl]
        g.frame = None if self.frame is None else tuple(f[sl] for f in self.frame)
        g._tracks = {}
        return g

    def tracks(self, track: int) -> tuple[Track, Track | None]:
        if track not in self._tracks:
            pos = self.scene.src_pos[:, track]
            extra = [self.scene.seconds(f) for k, f in getattr(self.scene, "src_cuts", np.zeros((0, 2)))
                     if int(k) == track]
            starts = piece_starts(self.times, pos, self.max_speed, extra)
            fwd = None
            if getattr(self.scene, "src_fwd", None) is not None:
                fwd = Track(self.times, self.scene.src_fwd[:, track], starts, kind="linear")
            self._tracks[track] = (Track(self.times, pos, starts), fwd)
        return self._tracks[track]

    def retarded(self, track: int, t: np.ndarray, p: np.ndarray):
        """Retarded delay (n,), source piece (n,), retarded source position (n, 3), converged (n,)."""
        pos, _ = self.tracks(track)
        tau = np.linalg.norm(pos(t) - p, axis=1) / self.c
        for _ in range(FIXED_POINT_STEPS):
            tau = np.linalg.norm(pos(t - tau) - p, axis=1) / self.c
        for _ in range(NEWTON_STEPS):
            piece = pos.piece_of(t - tau)
            rel = pos(t - tau, piece) - p
            dist = np.maximum(np.linalg.norm(rel, axis=1), 1e-12)
            f = tau - dist / self.c
            if np.all(np.abs(f) < RETARDED_TOLERANCE_S):
                break
            slope = 1.0 + np.einsum("ni,ni->n", rel / dist[:, None], pos(t - tau, piece, nu=1)) / self.c
            tau = np.maximum(tau - f / np.maximum(slope, 0.05), 0.0)
        piece = pos.piece_of(t - tau)
        s = pos(t - tau, piece)
        ok = np.abs(tau - np.linalg.norm(s - p, axis=1) / self.c) < 1e-6
        return tau, piece, s, ok

    def path(self, track: int) -> Path:
        tau, piece, s, ok = self.retarded(track, self.t, self.p)
        rel = s - self.p
        q = np.einsum("nji,nj->ni", self.rot, rel)
        d = derived(q)
        if self.frame is not None:
            s = self.scene.settings
            d["lateral"] = panning.screen_lateral(q, *self.frame, s["screen_edge_deg"],
                                                  panning.PAN_LAWS[s["pan_law"]], R_MIN)
        _, fwd = self.tracks(track)
        if fwd is not None:
            f = fwd(self.t - tau, piece)
            f = f / np.maximum(np.linalg.norm(f, axis=1, keepdims=True), 1e-12)
            to_listener = -rel / np.maximum(np.linalg.norm(rel, axis=1, keepdims=True), 1e-12)
            cos_emit = np.einsum("ni,ni->n", f, to_listener)
        else:
            cos_emit = np.ones(len(tau))
        changed = (np.diff(self.segment) != 0) | (np.diff(piece) != 0) | (np.diff(ok.astype(np.int8)) != 0)
        return Path(
            grid=self.grid,
            tau=tau,
            distance=self.c * tau,
            q=q,
            lateral=d["lateral"],
            rear=d["rear"],
            cos_emit=cos_emit,
            segment=self.segment,
            piece=piece,
            audible=ok,
            visibility=self.visibility(track),
            jumps=np.nonzero(changed)[0] + 1,
            before_bake=self.t - tau < self.times[0] - 1e-9,
        )

    def visibility(self, track: int) -> np.ndarray | None:
        sc = self.scene
        if sc.src_visibility is None or sc.vis_frames is None or len(sc.vis_frames) == 0:
            return None
        times = sc.seconds(sc.vis_frames)
        v = sc.src_visibility[:, track]
        return np.stack([np.interp(self.t, times, v[:, b]) for b in range(v.shape[1])], axis=1)

    def delay_at(self, track: int, t: float) -> float:
        """Retarded delay at one reception time (for reference delays outside the grid)."""
        p, _, _ = self.listener.pose(np.array([t]))
        tau, _, _, _ = self.retarded(track, np.array([t]), p)
        return float(tau[0])
