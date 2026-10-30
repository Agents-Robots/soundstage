"""Gain laws, cutoff laws, air absorption and the audio-rate filter stages.

- Gains: distance models (``soundstage.levels``, shared with the bake), directivity cone, rear cue.
- Cutoffs: rear cue; air absorption from ISO 9613-1, realized as two state-variable sections with a
  pair of zeros each, fitted per distance once per render (``AirAbsorption``).
- Head shadow: Brown-Duda first-order shelf coefficients per ear.
- Stages (ADR 0009): ``AirStage`` (emission side, the air sections with per-sample interpolated
  parameters), ``RearStage``, ``GridOnePoleStage`` and ``ShelfStage`` (reception side, per ear). All
  keep their state between calls to ``process``.

Spec: docs/spec/signal-model.md (distance gain, directivity cone, air absorption, panning, rear cue).
"""

from __future__ import annotations

import functools
import math

import numpy as np
from scipy.optimize import least_squares

from soundstage.engine import kernels
from soundstage.levels import DISTANCE_MODELS, distance_gain  # noqa: F401  (shared with the bake)

# ---------------------------------------------------------------------------- gains


def db_to_gain(db: float | np.ndarray) -> float | np.ndarray:
    return 10.0 ** (np.asarray(db) / 20.0)


def gain_to_db(gain: float | np.ndarray, floor: float = -200.0) -> float | np.ndarray:
    g = np.maximum(np.abs(np.asarray(gain, dtype=np.float64)), 10.0 ** (floor / 20.0))
    return 20.0 * np.log10(g)


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


AIR_SECTIONS = 2
"""Second-order sections of the air-absorption filter (order 4)."""
AIR_FIT_MAX_LOSS_DB = 60.0
"""Below this loss the fit follows ISO 9613-1; beyond it the filter only has to attenuate at least as much."""
AIR_FIT_HZ = (50.0, 20000.0)
AIR_DISTANCES = np.geomspace(0.05, 20000.0, 112)
AIR_BYPASS_DB = 0.05  # loss at 20 kHz below this: the stage passes the signal unchanged
AIR_SMOOTH = 0.3
"""Weight (dB per unit of log parameter) that keeps each distance's fit near the previous one's."""
AIR_DAMPING = (0.3, 2.0)
"""Bounds of the sections' damping R = 1/(2Q)."""
IDENTITY = (1.0, 1.0, 2.0, 1.0)
"""Section parameters (g, R, c, m) that pass the signal unchanged."""


def section_power(t: np.ndarray, p: np.ndarray) -> np.ndarray:
    """|H|^2 of TPT state-variable sections ``y = lp + c bp + m hp`` with parameters p (..., 4) =
    (g, R, c, m) at warped frequencies t = tan(pi f / fs) (B,): the bilinear transform of
    H(s) = (1 + c s + m s^2) / (1 + 2R s + s^2), s in units of the prewarped corner g."""
    g, r, c, m = (p[..., i, None] for i in range(4))
    x = t / g
    num = (1.0 - m * x * x) ** 2 + (c * x) ** 2
    den = (1.0 - x * x) ** 2 + (2.0 * r * x) ** 2
    return num / den


def _air_loss(v: np.ndarray, t: np.ndarray, jac: bool) -> tuple[np.ndarray, np.ndarray | None]:
    """Loss in dB (B,) of AIR_SECTIONS low-pass sections with a pair of zeros, parameters
    v = (log g, log R, log z) per section (zeros at z times the corner, m = 1/z^2, c = 0), and its
    Jacobian (B, 3 AIR_SECTIONS)."""
    k = 10.0 / math.log(10.0)
    loss = np.zeros(len(t))
    out = np.empty((len(t), len(v))) if jac else None
    for s in range(len(v) // 3):
        g, r, m = math.exp(v[3 * s]), math.exp(v[3 * s + 1]), math.exp(-2.0 * v[3 * s + 2])
        x = t / g
        x2 = x * x
        den = (1.0 - x2) ** 2 + 4.0 * r * r * x2
        e = 1.0 - m * x2
        e = np.where(np.abs(e) < 1e-9, 1e-9, e)
        loss += k * (np.log(den) - 2.0 * np.log(np.abs(e)))
        if jac:
            ddx = (-4.0 * x * (1.0 - x2) + 8.0 * r * r * x) / den  # d log(den) / dx
            out[:, 3 * s] = k * (-x * ddx - 4.0 * m * x2 / e)  # dx/dlog g = -x
            out[:, 3 * s + 1] = k * 8.0 * r * r * x2 / den
            out[:, 3 * s + 2] = -4.0 * k * m * x2 / e  # dm/dlog z = -2m
    return loss, out


@functools.lru_cache(maxsize=8)
def _air_table(temperature_c: float, humidity_pct: float, rate: int) -> np.ndarray:
    """Section parameters (len(AIR_DISTANCES), AIR_SECTIONS, 4) as ``section_power``; NaN rows where the
    stage is bypassed. Fit per distance (least squares in dB): within ``AIR_FIT_HZ`` the loss follows
    ISO 9613-1 where it is below ``AIR_FIT_MAX_LOSS_DB``; elsewhere, up to 0.45 of the rate (what a
    Doppler shift could bring down into the audible range), it must reach at least that loss."""
    f = np.geomspace(AIR_FIT_HZ[0], 0.45 * rate, 240)
    t = np.tan(np.pi * f / rate)
    inside = f <= AIR_FIT_HZ[1]
    alpha = iso9613_alpha(f, temperature_c, humidity_pct)
    lo = np.tile([math.log(math.tan(math.pi * 20.0 / rate)), math.log(AIR_DAMPING[0]), math.log(1.02)], AIR_SECTIONS)
    hi = np.tile([math.log(math.tan(math.pi * 0.49)), math.log(AIR_DAMPING[1]), math.log(60.0)], AIR_SECTIONS)
    x = np.tile([math.log(math.tan(math.pi * 0.4)), math.log(0.7), math.log(3.0)], AIR_SECTIONS)
    x[0::3] -= 0.2 * np.arange(AIR_SECTIONS)
    table = np.full((len(AIR_DISTANCES), AIR_SECTIONS, 4), np.nan)
    n_v = 3 * AIR_SECTIONS
    for i, d in enumerate(AIR_DISTANCES):
        target = alpha * d
        if target[inside][-1] < AIR_BYPASS_DB:
            continue
        follow = inside & (target < AIR_FIT_MAX_LOSS_DB)
        floor = np.minimum(target, AIR_FIT_MAX_LOSS_DB)
        prev = x.copy()

        def res(v):
            loss, _ = _air_loss(v, t, False)
            return np.concatenate([np.where(follow, loss - target, np.minimum(loss - floor, 0.0)),
                                   AIR_SMOOTH * (v - prev)])

        def jac(v):
            loss, j = _air_loss(v, t, True)
            j = np.where((follow | (loss < floor))[:, None], j, 0.0)
            return np.vstack([j, AIR_SMOOTH * np.eye(n_v)])

        x = least_squares(res, np.clip(x, lo + 1e-9, hi - 1e-9), jac=jac, bounds=(lo, hi)).x
        x = x.reshape(-1, 3)[np.argsort(x[0::3])].ravel()  # sections by corner: warm starts stay on one path
        g, r, z = np.exp(x.reshape(-1, 3)).T
        table[i] = np.stack([g, r, np.zeros(AIR_SECTIONS), 1.0 / (z * z)], axis=1)
    return table


class AirAbsorption:
    """Parameters of the air-absorption sections as a function of propagation distance."""

    def __init__(self, temperature_c: float, humidity_pct: float, rate: int, scale: float = 1.0):
        self.scale, self.rate = scale, rate
        self.table = _air_table(float(temperature_c), float(humidity_pct), int(rate))

    def params(self, distance: np.ndarray) -> np.ndarray:
        """(n, AIR_SECTIONS, 4) section parameters for distances in metres, interpolated in log
        distance (log corner, damping, zeros); ``IDENTITY`` sections where the loss is negligible,
        with the first fitted denominator, so that a track passing that distance changes smoothly."""
        d = np.asarray(distance, dtype=np.float64) * self.scale
        out = np.empty((len(d), AIR_SECTIONS, 4))
        out[:] = IDENTITY
        finite = ~np.isnan(self.table[:, 0, 0])
        if self.scale <= 0 or not finite.any():
            return out
        grid = np.log(AIR_DISTANCES[finite])
        tab = self.table[finite]
        logd = np.log(np.clip(d, AIR_DISTANCES[0], AIR_DISTANCES[-1]))
        active = logd >= grid[0]
        u = np.clip(logd[active], grid[0], grid[-1])
        for s in range(AIR_SECTIONS):
            out[:, s, 0] = tab[0, s, 0]
            out[:, s, 1] = tab[0, s, 1]
            out[:, s, 2] = 2.0 * tab[0, s, 1]
            out[active, s, 0] = np.exp(np.interp(u, grid, np.log(tab[:, s, 0])))
            out[active, s, 1] = np.interp(u, grid, tab[:, s, 1])
            out[active, s, 2] = 0.0
            out[active, s, 3] = np.exp(np.interp(u, grid, np.log(tab[:, s, 3])))
        return out

    def bypass(self, distance: np.ndarray) -> bool:
        """Whether every distance is closer than the first fitted one (the stage passes the signal)."""
        finite = ~np.isnan(self.table[:, 0, 0])
        if self.scale <= 0 or not finite.any():
            return True
        return bool(np.all(np.asarray(distance) * self.scale < AIR_DISTANCES[finite][0]))

    def loss_db(self, f: np.ndarray, distance: float) -> np.ndarray:
        """The designed loss in dB at frequencies f (B,) for one distance."""
        p = self.params(np.array([distance]))[0]
        t = np.tan(np.pi * np.minimum(np.asarray(f, dtype=np.float64), 0.49 * self.rate) / self.rate)
        return -10.0 * np.log10(section_power(t, p).prod(axis=0))


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


def _onepole_power(gain: np.ndarray, t: np.ndarray) -> np.ndarray:
    """|H|^2 of TPT one-pole low-passes with gains G (any shape) at warped frequencies
    t = tan(pi f / fs) (B,): 1 / (1 + (t / g)^2), g = G / (1 - G); G = 1 passes."""
    inv_g = (1.0 - gain) / np.maximum(gain, 1e-12)
    return 1.0 / (1.0 + (inv_g[..., None] * t) ** 2)


def _warped(freqs_hz: np.ndarray, rate: float) -> np.ndarray:
    return np.tan(np.pi * np.minimum(np.asarray(freqs_hz, dtype=np.float64), 0.49 * rate) / rate)


class AirStage:
    """Emission-side air absorption: state-variable sections whose parameters (n_ctl, S, 4) are given
    at (monotonic) emission times."""

    def __init__(self, times: np.ndarray, params: np.ndarray, rate: int, bypass: bool = False):
        self.rate = rate
        self.times = times
        self.params = np.ascontiguousarray(params)
        self.coef = np.ascontiguousarray(kernels.svf_coefficients(self.params))
        self.state = np.zeros((params.shape[1], 2))
        self.bypass = bypass

    def process(self, x: np.ndarray, a: int, b: int) -> np.ndarray:
        """Emission samples [a, b) (index / rate = emission time in seconds)."""
        if self.bypass:
            return x
        return kernels.svf_cascade_track(np.ascontiguousarray(x), a, self.rate, self.times, self.coef,
                                         self.state, np.empty(b - a))

    def power_response(self, freqs_hz: np.ndarray, idx: np.ndarray) -> np.ndarray:
        """|H|^2 (len(idx), B) at control points ``idx`` (for the culling estimate)."""
        if self.bypass:
            return np.ones((len(idx), len(freqs_hz)))
        return section_power(_warped(freqs_hz, self.rate), self.params[idx]).prod(axis=1)


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

    def power_response(self, freqs_hz: np.ndarray, idx: np.ndarray) -> np.ndarray:
        """|1 + rho (LP - 1)|^2 = (1 + ((1 - rho) t/g)^2) / (1 + (t/g)^2) at control points ``idx``."""
        tg = _warped(freqs_hz, self.rate) * (1.0 - self.gain) / max(self.gain, 1e-12)
        rho = self.rear[idx][:, None]
        return (1.0 + ((1.0 - rho) * tg) ** 2) / (1.0 + tg ** 2)


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

    def power_response(self, freqs_hz: np.ndarray, idx: np.ndarray) -> np.ndarray:
        return _onepole_power(self.gains[idx], _warped(freqs_hz, self.rate))

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

    def power_response(self, freqs_hz: np.ndarray, idx: np.ndarray) -> np.ndarray:
        """|b0 + b1 z^-1|^2 / |1 + a1 z^-1|^2 at control points ``idx``."""
        rate = self.grid.rate
        c = np.cos(2.0 * np.pi * np.minimum(np.asarray(freqs_hz, dtype=np.float64), 0.49 * rate) / rate)
        b0, b1 = self.b0[idx][:, None], self.b1[idx][:, None]
        return (b0 ** 2 + b1 ** 2 + 2.0 * b0 * b1 * c) / (1.0 + self.a1 ** 2 + 2.0 * self.a1 * c)

    def held(self, index: int) -> ShelfStage:
        """A copy with the parameters frozen at a control index and the current state (crossfades)."""
        copy = ShelfStage(self.grid, np.full_like(self.b0, self.b0[index]), np.full_like(self.b1, self.b1[index]),
                          self.a1)
        copy.state = self.state.copy()
        return copy
