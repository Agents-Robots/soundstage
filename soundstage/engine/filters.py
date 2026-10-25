"""Gain laws, cutoff laws, air absorption and the audio-rate filter stages.

- Gains: distance models (as in OpenAL and Blender), directivity cone, rear cue.
- Cutoffs: rear cue; air absorption from ISO 9613-1, realized as four cascaded one-pole low-passes
  whose cutoffs are fitted per distance once per render (``AirAbsorption``).
- Head shadow: Brown-Duda first-order shelf coefficients per ear.
- Stages (ADR 0009): ``OnePoleStage`` (emission side, cascade of TPT one-poles with per-sample
  interpolated gains) and ``ShelfStage`` (reception side, per ear). Both keep their state between
  calls to ``process``.

Spec: docs/spec/signal-model.md (distance gain, directivity cone, air absorption, panning, rear cue).
"""

from __future__ import annotations

import functools
import math

import numpy as np
from scipy.optimize import least_squares

from soundstage.engine import kernels

# ---------------------------------------------------------------------------- gains


def db_to_gain(db: float | np.ndarray) -> float | np.ndarray:
    return 10.0 ** (np.asarray(db) / 20.0)


def gain_to_db(gain: float | np.ndarray, floor: float = -200.0) -> float | np.ndarray:
    g = np.maximum(np.abs(np.asarray(gain, dtype=np.float64)), 10.0 ** (floor / 20.0))
    return 20.0 * np.log10(g)


def distance_gain(d: np.ndarray, model: str, ref: float, max_distance: float | None, rolloff: float) -> np.ndarray:
    """Linear gain for distances ``d`` (metres); 1 at and inside the reference distance."""
    d = np.asarray(d, dtype=np.float64)
    hi = np.inf if max_distance is None else max_distance
    dc = np.clip(d, ref, hi)
    if model == "inverse_clamped":
        return ref / (ref + rolloff * (dc - ref))
    if model == "linear_clamped":
        return np.maximum(0.0, 1.0 - rolloff * (dc - ref) / (hi - ref)) if hi > ref else np.ones_like(dc)
    if model == "exponential_clamped":
        return (dc / ref) ** (-rolloff)
    if model == "none":
        return np.ones_like(dc)
    raise ValueError(f"unknown distance model {model!r}")


DISTANCE_MODELS = ("inverse_clamped", "linear_clamped", "exponential_clamped", "none")


def cone_gain(cos_angle: np.ndarray, inner_deg: float, outer_deg: float, outer_gain_db: float) -> np.ndarray:
    """OpenAL cone: 1 inside inner/2, the outer gain beyond outer/2, linear in angle in between."""
    if inner_deg >= 360.0 and outer_deg >= 360.0:
        return np.ones_like(cos_angle)
    angle = np.degrees(np.arccos(np.clip(cos_angle, -1.0, 1.0)))
    a, b = inner_deg / 2.0, max(outer_deg, inner_deg) / 2.0
    g_out = float(db_to_gain(outer_gain_db))
    if b <= a:
        return np.where(angle <= a, 1.0, g_out)
    u = np.clip((angle - a) / (b - a), 0.0, 1.0)
    return 1.0 + u * (g_out - 1.0)


def rear_gain(rear: np.ndarray, rear_gain_db: float) -> np.ndarray:
    return db_to_gain(rear_gain_db * rear)


# ---------------------------------------------------------------------------- air absorption


def iso9613_alpha(f: np.ndarray, temperature_c: float = 20.0, humidity_pct: float = 50.0,
                  pressure_kpa: float = 101.325) -> np.ndarray:
    """ISO 9613-1 pure-tone atmospheric attenuation coefficient in dB/m."""
    t = temperature_c + 273.15
    t0, t01, pr = 293.15, 273.16, 101.325
    psat = pr * 10.0 ** (-6.8346 * (t01 / t) ** 1.261 + 4.6151)
    h = humidity_pct * (psat / pressure_kpa)
    fr_o = (pressure_kpa / pr) * (24.0 + 4.04e4 * h * (0.02 + h) / (0.391 + h))
    fr_n = (pressure_kpa / pr) * (t / t0) ** -0.5 * (9.0 + 280.0 * h * math.exp(-4.170 * ((t / t0) ** (-1 / 3) - 1.0)))
    f = np.asarray(f, dtype=np.float64)
    return 8.686 * f * f * (
        1.84e-11 * (pr / pressure_kpa) * (t / t0) ** 0.5
        + (t / t0) ** -2.5 * (0.01275 * math.exp(-2239.1 / t) / (fr_o + f * f / fr_o)
                              + 0.1068 * math.exp(-3352.0 / t) / (fr_n + f * f / fr_n))
    )


AIR_POLES = 4
AIR_FIT_MAX_LOSS_DB = 20.0
AIR_DISTANCES = np.geomspace(0.05, 20000.0, 112)
AIR_BYPASS_DB = 0.05  # loss at 20 kHz below this: the stage passes the signal unchanged


def _onepole_loss_db(f: np.ndarray, fc: np.ndarray, rate: float) -> np.ndarray:
    """Loss in dB of bilinear one-pole low-passes (summed over the cutoffs ``fc``)."""
    w = np.tan(np.pi * f[:, None] / rate) / np.tan(np.pi * fc[None, :] / rate)
    return (10.0 * np.log10(1.0 + w * w)).sum(axis=1)


@functools.lru_cache(maxsize=8)
def _air_table(temperature_c: float, humidity_pct: float, rate: int) -> np.ndarray:
    """Cutoffs (len(AIR_DISTANCES), AIR_POLES) in Hz; inf where the stage is bypassed."""
    f = np.geomspace(100.0, min(20000.0, 0.45 * rate), 200)
    alpha = iso9613_alpha(f, temperature_c, humidity_pct)
    lo, hi = math.log(20.0), math.log(0.49 * rate)
    x = np.log(np.full(AIR_POLES, 0.45 * rate)) - np.linspace(0.0, 0.3, AIR_POLES)
    table = np.full((len(AIR_DISTANCES), AIR_POLES), np.inf)
    for i, d in enumerate(AIR_DISTANCES):
        target = alpha * d
        if target[-1] < AIR_BYPASS_DB:
            continue
        m = target < AIR_FIT_MAX_LOSS_DB
        fit = least_squares(lambda v: _onepole_loss_db(f[m], np.exp(v), rate) - target[m], np.clip(x, lo, hi),
                            bounds=(lo, hi))
        x = np.sort(fit.x)  # warm start for the next distance keeps the cutoffs smooth
        table[i] = np.exp(x)
    return table


class AirAbsorption:
    """Cutoffs of the air-absorption cascade as a function of propagation distance."""

    def __init__(self, temperature_c: float, humidity_pct: float, rate: int, scale: float = 1.0):
        self.scale = scale
        self.table = _air_table(float(temperature_c), float(humidity_pct), int(rate))

    def cutoffs(self, distance: np.ndarray) -> np.ndarray:
        """(n, AIR_POLES) cutoffs in Hz for distances in metres (inf = no filtering)."""
        d = np.asarray(distance, dtype=np.float64) * self.scale
        out = np.full((len(d), AIR_POLES), np.inf)
        if self.scale <= 0:
            return out
        logd = np.log(np.clip(d, AIR_DISTANCES[0], AIR_DISTANCES[-1]))
        grid = np.log(AIR_DISTANCES)
        finite = np.isfinite(self.table[:, 0])
        if not finite.any():
            return out
        first = int(np.argmax(finite))
        active = logd >= grid[first]
        for j in range(AIR_POLES):
            out[active, j] = np.exp(np.interp(logd[active], grid[finite], np.log(self.table[finite, j])))
        return out


# ---------------------------------------------------------------------------- head shadow

HEAD_SHADOW_ALPHA_MIN = 0.1
HEAD_SHADOW_THETA_MIN_DEG = 150.0


def head_shadow_alpha(cos_theta: np.ndarray, strength: float) -> np.ndarray:
    """Brown-Duda high-frequency gain factor for an ear; theta from the ear's axis."""
    theta = np.degrees(np.arccos(np.clip(cos_theta, -1.0, 1.0)))
    a = (1.0 + HEAD_SHADOW_ALPHA_MIN / 2) + (1.0 - HEAD_SHADOW_ALPHA_MIN / 2) * np.cos(
        np.radians(theta * 180.0 / HEAD_SHADOW_THETA_MIN_DEG))
    return 1.0 + strength * (a - 1.0)


def head_shadow_coefficients(alpha: np.ndarray, head_radius: float, speed_of_sound: float,
                             rate: int) -> tuple[np.ndarray, np.ndarray, float]:
    """b0, b1 (per alpha) and a1 of H(s) = (1 + alpha s/wp) / (1 + s/wp), wp = 2c/a, bilinear at wp."""
    wp = 2.0 * speed_of_sound / head_radius
    k = 1.0 / math.tan(wp / (2.0 * rate))
    return (1.0 + alpha * k) / (1.0 + k), (1.0 - alpha * k) / (1.0 + k), (1.0 - k) / (1.0 + k)


# ---------------------------------------------------------------------------- stages


def tpt_gain(cutoff_hz: np.ndarray, rate: float) -> np.ndarray:
    """G = g / (1 + g), g = tan(pi fc / fs); fc = inf (or above 0.49 fs) gives G = 1 (pass)."""
    fc = np.asarray(cutoff_hz, dtype=np.float64)
    g = np.tan(np.pi * np.minimum(fc, 0.49 * rate) / rate)
    return np.where(np.isfinite(fc) & (fc < 0.49 * rate), g / (1.0 + g), 1.0)


class OnePoleStage:
    """Emission-side cascade of TPT one-poles; parameters given at (monotonic) emission times."""

    def __init__(self, times: np.ndarray, cutoffs: np.ndarray, rate: int):
        self.rate = rate
        self.times = times
        self.gains = np.ascontiguousarray(tpt_gain(cutoffs, rate))  # (n_ctl, poles)
        self.state = np.zeros(self.gains.shape[1])
        self.bypass = bool(np.all(self.gains >= 1.0))

    def process(self, x: np.ndarray, a: int, b: int) -> np.ndarray:
        """Emission samples [a, b) (index / rate = emission time in seconds)."""
        if self.bypass:
            return x
        return kernels.onepole_cascade_track(np.ascontiguousarray(x), a, self.rate, self.times, self.gains,
                                             self.state, np.empty(b - a))


class RearStage:
    """Emission-side rear cue: y = x + rho (LP(x) - x), LP a TPT one-pole at ``cutoff_hz``.

    A first-order shelf whose depth follows the rear factor rho: transparent in front and at the
    side (rho = 0), the plain low-pass straight behind (rho = 1).
    """

    def __init__(self, times: np.ndarray, rear: np.ndarray, cutoff_hz: float, rate: int):
        self.times, self.rear, self.rate = times, np.ascontiguousarray(rear, dtype=np.float64), rate
        self.gain = float(tpt_gain(np.array([cutoff_hz]), rate)[0])
        self.state = np.zeros(1)
        self.bypass = not np.any(rear > 0)

    def process(self, x: np.ndarray, a: int, b: int) -> np.ndarray:
        if self.bypass:
            return x
        return kernels.rear_shelf_track(np.ascontiguousarray(x), a, self.rate, self.times, self.rear, self.gain,
                                        self.state, np.empty(b - a))


OCCLUSION_ATTACK_S = 0.060  # becoming occluded
OCCLUSION_RELEASE_S = 0.150  # becoming visible


def occlusion_filter(visibility: np.ndarray, bands_hz: list[float], transmission_db: float,
                     transmission_cutoff_hz: float, dt: float) -> tuple[np.ndarray, np.ndarray]:
    """Broadband gain (n,) and low-pass cutoff (n,) from smoothed per-band visibility (n, bands).

    Each band's gain is the open share plus what passes through the occluders,
    ``g = v + (1 - v) T(f)``, with ``T`` the transmission gain low-passed at
    ``transmission_cutoff_hz``. The lowest band gives the broadband gain; the higher bands' ratios
    to it give the cutoff of a one-pole low-pass, fitted to their attenuations in dB (least
    squares, ``fit_onepole_cutoff``).
    """
    smooth = np.empty_like(visibility)
    down, up = math.exp(-dt / OCCLUSION_ATTACK_S), math.exp(-dt / OCCLUSION_RELEASE_S)
    for b in range(visibility.shape[1]):
        kernels.follow(np.ascontiguousarray(visibility[:, b]), down, up, smooth[:, b])
    f = np.asarray(bands_hz, dtype=np.float64)
    transmission = db_to_gain(transmission_db) / np.sqrt(1.0 + (f / transmission_cutoff_hz) ** 2)
    g = smooth + (1.0 - smooth) * transmission[None, :]
    gain = g[:, 0]
    ratios = np.clip(g[:, 1:] / np.maximum(gain, 1e-9)[:, None], 1e-6, 1.0)
    cutoff = np.full(len(g), np.inf)
    attenuated = (ratios < 0.9999).any(axis=1)
    if attenuated.any():
        cutoff[attenuated] = fit_onepole_cutoff(ratios[attenuated], f[1:])
    return gain, cutoff


def fit_onepole_cutoff(ratios: np.ndarray, freqs: np.ndarray, iterations: int = 40) -> np.ndarray:
    """Cutoff (n,) of the one-pole low-pass whose gains at ``freqs`` best match ``ratios`` (n, B)
    in dB (least squares); inf where nothing is attenuated.

    With ``x = 1/fc^2`` the attenuation is ``10 log10(1 + f^2 x)``; the optimum lies between the
    values of ``x`` that match single bands, where the derivative of the squared error changes
    sign, and is found by bisection.
    """
    want_db = -20.0 * np.log10(np.clip(ratios, 1e-6, 1.0))
    f2 = np.asarray(freqs, dtype=np.float64) ** 2
    single = (10.0 ** (want_db / 10.0) - 1.0) / f2
    lo, hi = single.min(axis=1), single.max(axis=1)
    for _ in range(iterations):
        x = 0.5 * (lo + hi)
        q = 1.0 + f2 * x[:, None]
        rising = ((10.0 * np.log10(q) - want_db) * f2 / q).sum(axis=1) > 0
        hi = np.where(rising, x, hi)
        lo = np.where(rising, lo, x)
    x = 0.5 * (lo + hi)
    with np.errstate(divide="ignore"):
        return np.where(x > 0, 1.0 / np.sqrt(x), np.inf)


class GridOnePoleStage:
    """Reception-side TPT one-pole low-pass with a control-rate cutoff track (per ear)."""

    def __init__(self, grid, cutoffs: np.ndarray, rate: int, jumps=None):
        self.grid, self.rate, self.jumps = grid, rate, jumps
        self.gains = tpt_gain(cutoffs, rate)
        self.state = np.zeros(1)

    def process(self, x: np.ndarray, a: int, b: int) -> np.ndarray:
        g = self.grid.linear(self.gains, a, b, self.jumps)
        return kernels.onepole_cascade(np.ascontiguousarray(x), g[:, None], self.state, np.empty(b - a))

    def held(self, index: int) -> GridOnePoleStage:
        copy = GridOnePoleStage.__new__(GridOnePoleStage)
        copy.grid, copy.rate, copy.jumps = self.grid, self.rate, None
        copy.gains = np.full_like(self.gains, self.gains[index])
        copy.state = self.state.copy()
        return copy


class ShelfStage:
    """Reception-side first-order shelf (head shadow) with per-sample interpolated numerator."""

    def __init__(self, grid, b0: np.ndarray, b1: np.ndarray, a1: float, jumps=None):
        self.grid, self.b0, self.b1, self.a1, self.jumps = grid, b0, b1, a1, jumps
        self.state = np.zeros(2)

    def process(self, x: np.ndarray, a: int, b: int) -> np.ndarray:
        """Output samples [a, b)."""
        return kernels.first_order(np.ascontiguousarray(x), self.grid.linear(self.b0, a, b, self.jumps),
                                   self.grid.linear(self.b1, a, b, self.jumps), self.a1, self.state,
                                   np.empty(b - a))

    def held(self, index: int) -> ShelfStage:
        """A copy with the parameters frozen at a control index and the current state (crossfades)."""
        copy = ShelfStage(self.grid, np.full_like(self.b0, self.b0[index]), np.full_like(self.b1, self.b1[index]),
                          self.a1)
        copy.state = self.state.copy()
        return copy
