"""Storyboard of ``around`` (README.md): a scooter circling the camera at 12 m, once per pass, heard
with level difference only, then with time difference and head shadow, then with the rear cue."""

import cmath
import math

from kit.story import FPS, Pass, Section, TitlePage

REAR_OFF = {"rear_gain_db": 0.0, "rear_cutoff_hz": 20000.0}
SECTION = Section(
    key="around",
    title="Around the listener",
    title_page=TitlePage(
        title="Around the listener",
        claim="Two channels, two ears: level, arrival time and timbre tell where a sound comes from.",
        code='panner = "hybrid"',
        listen="the scooter leaving the picture, passing behind you and coming back. Use headphones.",
        headphones=True,
    ),
    passes=(
        Pass("amplitude", 360, "Level difference only", 'panner="amplitude"  rear_gain_db=0', "WITHOUT",
             settings={"panner": "amplitude", **REAR_OFF}),
        Pass("hybrid", 360, "Plus time difference and head shadow", 'panner="hybrid"  rear_gain_db=0',
             settings={"panner": "hybrid", **REAR_OFF}),
        Pass("rear", 360, "Plus the rear cue", 'panner="hybrid"  rear_gain_db=-2  rear_cutoff_hz=6000', "WITH"),
    ),
    gain_db=-4.5,
)

C = 343.0
CAMERA = (0.0, 0.0, 1.6)
"""The camera in the middle of the island, looking along +Y."""
LENS = 24.0
RADIUS = 12.0
LAP_S = 12.0
EMITTER_Z = 1.0
"""The engine and the probe ride 1 m above the ground (the camera is 0.6 m higher)."""
FADE_IN_S = 0.2
FADE_OUT_S = 0.4
MARGIN_S = 0.25
"""The faded end arrives this long before its pass ends (S3; C5 asks for 0.2 s of silence at the end)."""
HEAD_RADIUS = 0.0875
ITD_SCALE = 0.5
R_MIN = 0.25
"""Near-field softening of the engine's direction (docs/spec/signal-model.md)."""
REAR_DEFAULTS = (-2.0, 6000.0)
ILD_LIMIT_DB = 12.0
"""``hybrid``'s largest pan level difference between the ears, reached at the sides (#46)."""


def angle(t: float) -> float:
    """Clockwise angle from straight ahead (radians), t seconds after the first pass starts."""
    return 2 * math.pi * t / LAP_S


def position(t: float) -> tuple[float, float, float]:
    a = angle(t)
    return (CAMERA[0] + RADIUS * math.sin(a), CAMERA[1] + RADIUS * math.cos(a), EMITTER_Z)


def lateral(t: float) -> float:
    """The engine's lateral sine (positive to the right) as seen from the camera."""
    x, y, z = (p - c for p, c in zip(position(t), CAMERA))
    return x / math.sqrt(x * x + y * y + z * z + R_MIN ** 2)


def rear_factor(t: float) -> float:
    x, y, z = (p - c for p, c in zip(position(t), CAMERA))
    return max(0.0, -y / math.sqrt(x * x + y * y + z * z + R_MIN ** 2))


def itd_ms(t: float, scale: float = ITD_SCALE) -> float:
    """Arrival-time difference (ms), Woodworth: positive when the right ear hears first."""
    th = math.asin(lateral(t))
    return 1000 * scale * HEAD_RADIUS / C * (th + math.sin(th))


def rear_db(f: float, rho: float, gain_db: float = REAR_DEFAULTS[0], cutoff_hz: float = REAR_DEFAULTS[1],
            rate: int = 48000) -> float:
    """The rear cue's effect at f: the dry signal mixed with a one-pole low-pass (TPT, prewarped at the
    cutoff) by rho, and the rear gain scaled by rho."""
    g = math.tan(math.pi * cutoff_hz / rate)
    z = cmath.exp(1j * 2 * math.pi * f / rate)
    s = (z - 1) / (z + 1)  # bilinear transform; the TPT one-pole is H(s) = g / (s + g)
    lp = g / (s + g)
    return 20 * math.log10(abs(1 + rho * (lp - 1))) + gain_db * rho


def frames_per_lap() -> int:
    return round(LAP_S * FPS)
