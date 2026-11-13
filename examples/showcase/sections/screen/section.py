"""Storyboard of ``screen`` (README.md): a tennis rally filmed from the side with a zoom, heard with
the direction from the camera, then with the direction on the screen."""

import math

from kit.story import FPS, Pass, Section, TitlePage

SECTION = Section(
    key="screen",
    title="Sound follows the lens",
    title_page=TitlePage(
        title="Sound follows the lens",
        claim="A source in the picture is heard where it is seen, also when the lens zooms.",
        code='pan_reference = "screen"',
        listen="the hits moving apart as the players reach the frame's edges.",
    ),
    passes=(
        Pass("camera", 360, "Direction from the camera", 'pan_reference="camera"', "WITHOUT",
             settings={"pan_reference": "camera"}),
        Pass("screen", 360, "Direction on the screen", 'pan_reference="screen"  screen_edge_deg=16.5', "WITH"),
    ),
    gain_db=2.0,
    loudness_reported_only=True,
)

CAMERA = (0.0, -40.0, 6.0)
"""On the line of the net (the net runs along Y at x = 0), 40 m from the middle of the court."""
AIM = (0.0, 0.0, 1.0)
"""The camera looks at the middle of the court at the height of the hits: the hits lie on the
picture's horizontal midline."""
HIT_X = 11.9
"""The hits are on the baselines, left (-X) and right (+X) of the net."""
HIT_Z = 1.0
LENS_WIDE, LENS_TELE = 24.0, 55.0
ZOOM_S = (3.0, 8.0)
"""24 mm until 3 s into the pass, a zoom to 55 mm until 8 s, then 55 mm."""
HITS = 10
FIRST_HIT_S = 0.6
HIT_EVERY_S = 1.2
SCREEN_EDGE_DEG = 16.5
SPEAKER_DEG = 30.0
R_MIN = 0.25
HEAD_RADIUS = 0.0875
HEAD_SHADOW = 0.5
C = 343.0


def lens(t: float) -> float:
    """Focal length (mm) t seconds into a pass."""
    a, b = ZOOM_S
    if t <= a:
        return LENS_WIDE
    if t >= b:
        return LENS_TELE
    return LENS_WIDE + (LENS_TELE - LENS_WIDE) * (t - a) / (b - a)


def hit_times() -> list[float]:
    return [FIRST_HIT_S + i * HIT_EVERY_S for i in range(HITS)]


def hitter(i: int) -> str:
    """The left player hits first."""
    return "left" if i % 2 == 0 else "right"


def hit_point(side: str) -> tuple[float, float, float]:
    return ((-HIT_X if side == "left" else HIT_X), 0.0, HIT_Z)


def camera_space(p: tuple[float, float, float]) -> tuple[float, float, float]:
    """(x right, y up, z towards the camera) of a point, for the camera at CAMERA aimed at AIM."""
    f = [a - c for a, c in zip(AIM, CAMERA)]
    n = math.sqrt(sum(v * v for v in f))
    f = [v / n for v in f]
    right = (f[1], -f[0], 0.0)
    rn = math.hypot(right[0], right[1])
    right = (right[0] / rn, right[1] / rn, 0.0)
    up = (right[1] * f[2] - right[2] * f[1], right[2] * f[0] - right[0] * f[2], right[0] * f[1] - right[1] * f[0])
    d = [a - c for a, c in zip(p, CAMERA)]
    dot = lambda u, v: sum(a * b for a, b in zip(u, v))  # noqa: E731
    return dot(d, right), dot(d, up), -dot(d, f)


def image_u(side: str, focal_mm: float) -> float:
    """Horizontal position of a hit in the frame, -1 (left edge) to 1 (right edge)."""
    x, _, z = camera_space(hit_point(side))
    return (x / -z) / (18.0 / focal_mm)


def law_ratio(lam: float) -> float:
    """(g_R - g_L) / (g_R + g_L) of the sine law."""
    return math.tan(lam * math.pi / 4)


def law_inverse(ratio: float) -> float:
    return math.atan(ratio) * 4 / math.pi


def lateral(side: str, focal_mm: float, reference: str) -> float:
    """The lateral sine the engine pans with (docs/spec/signal-model.md, "Panning")."""
    x, y, z = camera_space(hit_point(side))
    r_e = math.sqrt(x * x + y * y + z * z + R_MIN * R_MIN)
    if reference == "camera":
        return x / r_e
    k = math.tan(math.radians(SCREEN_EDGE_DEG)) / math.tan(math.radians(SPEAKER_DEG))
    return law_inverse(image_u(side, focal_mm) * k) * math.hypot(x, z) / r_e


def head_shadow_db(f: float, cos_theta: float) -> float:
    """Brown-Duda shelf of one ear at f (signal-model.md), at the engine's default strength."""
    theta = math.degrees(math.acos(max(-1.0, min(1.0, cos_theta))))
    a = 1.05 + 0.95 * math.cos(math.radians(theta * 180.0 / 150.0))
    alpha = 1 + HEAD_SHADOW * (a - 1)
    w = f / (2 * C / HEAD_RADIUS / (2 * math.pi))  # omega / (2 omega_0)
    return 10 * math.log10((1 + (alpha * w) ** 2) / (1 + w * w))


def level_difference_db(side: str, focal_mm: float, reference: str, f: float = 283.0) -> float:
    """Near channel minus far channel at f: the sine law plus the head shadow."""
    lam = lateral(side, focal_mm, reference)
    phi = (lam + 1) * math.pi / 4
    pan = 20 * math.log10(math.tan(phi)) if side == "right" else 20 * math.log10(1 / math.tan(phi))
    near, far = (lam, -lam) if side == "right" else (-lam, lam)
    return pan + head_shadow_db(f, near) - head_shadow_db(f, far)


def heard_u(side: str, focal_mm: float, reference: str) -> float:
    """Where the hit is heard, as a position on the screen (-1 to 1): its channel ratio read back
    through the tangent law on loudspeakers at +-30 deg and a screen edge at SCREEN_EDGE_DEG."""
    k = math.tan(math.radians(SCREEN_EDGE_DEG)) / math.tan(math.radians(SPEAKER_DEG))
    return law_ratio(lateral(side, focal_mm, reference)) / k


def frames_per_pass() -> int:
    return round(12 * FPS)
