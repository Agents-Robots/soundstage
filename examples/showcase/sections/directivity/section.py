"""Storyboard of ``directivity`` (README.md): a camera circling a business jet with its engines
running, the engines' sounds first without cones, then with a cone per sound."""

import math

from kit.story import Pass, Section, TitlePage

SECTION = Section(
    key="directivity",
    title="Directivity",
    title_page=TitlePage(
        title="Directivity",
        claim="Most sources are louder in one direction. A cone per sound sets where it radiates.",
        code="cone_inner_deg = 60   cone_outer_deg = 240",
        listen="the whine in front of the jet, the roar behind it.",
    ),
    passes=(
        Pass("omni", 390, "Equally loud in all directions", "cone_inner_deg=360  cone_outer_deg=360", "WITHOUT"),
        Pass("cones", 390, "A cone per sound", "whine 60° / 240° / −18 dB    roar 90° / 270° / −12 dB", "WITH"),
    ),
    gain_db=-7.0,
)

RADIUS = 30.0
"""The camera's circle, centred on the middle between the engines (the jet's origin)."""
CAMERA_Z = 3.0
LENS = 28.0
LAP_S = 13.0
AIM = (0.0, -4.0, 2.4)
"""The camera looks at the jet, a little ahead of the engines, so that the whole jet stays in frame."""
ENGINE = (1.9, 0.0, 2.6)
"""Middle of the right engine (models.JET_ENGINE); the left one mirrored."""
HALF_NACELLE = 1.5
FADE_IN_S = 0.2
FADE_OUT_S = 0.4
MARGIN_S = 0.25
C = 343.0

CONES = {
    # sound: (cone_inner_deg, cone_outer_deg, cone_outer_gain_db, forward axis of the jet)
    "whine": (60.0, 240.0, -18.0, "-Y"),
    "roar": (90.0, 270.0, -12.0, "Y"),
}
OMNI = (360.0, 360.0, -12.0)


def camera_position(t: float) -> tuple[float, float, float]:
    """The camera t seconds into a pass: in front of the nose (-Y) at 0, then counter-clockwise seen
    from above (first to +X, the jet's left side), once per LAP_S."""
    a = 2 * math.pi * t / LAP_S
    return (RADIUS * math.sin(a), -RADIUS * math.cos(a), CAMERA_Z)


def emitter(sound: str, side: int) -> tuple[float, float, float]:
    """Intake (whine) or nozzle (roar) of the engine on ``side`` (-1 left, +1 right)."""
    dy = -HALF_NACELLE if sound == "whine" else HALF_NACELLE
    return (side * ENGINE[0], ENGINE[1] + dy, ENGINE[2])


def cone_db(beta_deg: float, inner: float, outer: float, outer_db: float) -> float:
    """The cone gain at beta (signal-model.md, "Cones"): linear in gain between the half angles."""
    g_out = 10 ** (outer_db / 20)
    if beta_deg <= inner / 2:
        return 0.0
    if beta_deg >= outer / 2:
        return outer_db
    return 20 * math.log10(1 + (g_out - 1) * (beta_deg - inner / 2) / (outer / 2 - inner / 2))


def beta(sound: str, side: int, listener: tuple[float, float, float]) -> float:
    """Angle between the sound's cone axis and the direction from its emitter to the listener."""
    e = emitter(sound, side)
    d = [a - b for a, b in zip(listener, e)]
    axis = (0.0, -1.0, 0.0) if sound == "whine" else (0.0, 1.0, 0.0)
    cos = sum(a * b for a, b in zip(d, axis)) / math.sqrt(sum(v * v for v in d))
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def cone_at(sound: str, side: int, t: float) -> float:
    """The cone gain (dB) of a sound heard t seconds into a pass (the jet stands, so the camera's
    position at reception decides)."""
    inner, outer, outer_db, _ = CONES[sound]
    return cone_db(beta(sound, side, camera_position(t)), inner, outer, outer_db)
