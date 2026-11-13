"""What the engine's ear model does with a direction, for expected values in checks (stdlib only):
pan law, screen-relative lateral, head shadow, rear cue (docs/spec/signal-model.md, "Panning").

A camera is given by its position, its compass yaw (0 = +Y, 90 = -X, as ``base.aim``) and its pitch
(up positive), with no roll. The defaults are the engine's.
"""

from __future__ import annotations

import cmath
import math

C = 343.0
HEAD_RADIUS = 0.0875
HEAD_SHADOW = 0.5
R_MIN = 0.25
"""Near-field softening of the direction."""
SCREEN_EDGE_DEG = 16.5
SPEAKER_DEG = 30.0
REAR_DEFAULTS = (-2.0, 6000.0)
REAR_OFF = {"rear_gain_db": 0.0, "rear_cutoff_hz": 20000.0}


def camera_space(p, cam, yaw_deg: float, pitch_deg: float) -> tuple[float, float, float]:
    """(x right, y up, z towards the camera) of point p."""
    yaw, pitch = math.radians(yaw_deg), math.radians(pitch_deg)
    fwd = (-math.sin(yaw) * math.cos(pitch), math.cos(yaw) * math.cos(pitch), math.sin(pitch))
    right = (math.cos(yaw), math.sin(yaw), 0.0)
    up = (right[1] * fwd[2] - right[2] * fwd[1], right[2] * fwd[0] - right[0] * fwd[2],
          right[0] * fwd[1] - right[1] * fwd[0])
    d = [a - b for a, b in zip(p, cam)]
    dot = lambda u, v: sum(a * b for a, b in zip(u, v))  # noqa: E731
    return dot(d, right), dot(d, up), -dot(d, fwd)


def law_inverse(ratio: float) -> float:
    """The lateral sine whose sine-law ratio (g_R - g_L) / (g_R + g_L) is ``ratio``."""
    return math.atan(ratio) * 4 / math.pi


def lateral(p, cam, yaw_deg: float, pitch_deg: float, focal_mm: float, reference: str = "screen") -> float:
    """The lateral sine the engine pans with, for a point in the picture."""
    x, y, z = camera_space(p, cam, yaw_deg, pitch_deg)
    r_e = math.sqrt(x * x + y * y + z * z + R_MIN * R_MIN)
    if reference == "camera":
        return x / r_e
    u = (x / -z) / (18.0 / focal_mm)
    k = math.tan(math.radians(SCREEN_EDGE_DEG)) / math.tan(math.radians(SPEAKER_DEG))
    return law_inverse(u * k) * math.hypot(x, z) / r_e


def head_shadow_db(f: float, cos_theta: float) -> float:
    """Brown-Duda shelf of one ear at f, ``cos_theta`` the cosine of the angle from that ear's axis."""
    theta = math.degrees(math.acos(max(-1.0, min(1.0, cos_theta))))
    a = 1.05 + 0.95 * math.cos(math.radians(theta * 180.0 / 150.0))
    alpha = 1 + HEAD_SHADOW * (a - 1)
    w = f / (2 * C / HEAD_RADIUS / (2 * math.pi))
    return 10 * math.log10((1 + (alpha * w) ** 2) / (1 + w * w))


def right_minus_left_db(lam: float, f: float = 283.0) -> float:
    """Level of the right channel over the left at f: the sine law and the head shadow."""
    phi = (lam + 1) * math.pi / 4
    return 20 * math.log10(math.tan(phi)) + head_shadow_db(f, lam) - head_shadow_db(f, -lam)


def rear_factor(p, cam, yaw_deg: float, pitch_deg: float) -> float:
    """How far behind the listener a point is: 1 straight behind, 0 at the sides and in front."""
    x, y, z = camera_space(p, cam, yaw_deg, pitch_deg)
    return max(0.0, z / math.sqrt(x * x + y * y + z * z + R_MIN * R_MIN))


def rear_db(f: float, rho: float, gain_db: float = REAR_DEFAULTS[0], cutoff_hz: float = REAR_DEFAULTS[1],
            rate: int = 48000) -> float:
    """The rear cue's effect at f: the dry signal mixed with a one-pole low-pass (TPT, prewarped at the
    cutoff) by rho, and the rear gain scaled by rho."""
    g = math.tan(math.pi * cutoff_hz / rate)
    z = cmath.exp(1j * 2 * math.pi * f / rate)
    s = (z - 1) / (z + 1)
    lp = g / (s + g)
    return 20 * math.log10(abs(1 + rho * (lp - 1))) + gain_db * rho
