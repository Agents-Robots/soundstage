"""Storyboard of ``occlusion`` (README.md): a motorbike behind a row of houses, then a busker around
a street corner, each heard without occlusion and with it."""

import math

from kit.story import Pass, Section, TitlePage

STREETS = {"reverb": "city_streets"}
SECTION = Section(
    key="occlusion",
    title="Occlusion",
    title_page=TitlePage(
        title="Occlusion",
        claim="What stands between a source and the camera muffles it. The bake reads it from the scene's geometry.",
        code="occlusion = True",
        listen="the motorbike dimming behind each house; the busker heard around the corner before he is seen.",
    ),
    passes=(
        Pass("bike_off", 270, "Motorbike behind houses: no occlusion", "occlusion=False", "WITHOUT"),
        Pass("bike", 270, "Motorbike behind houses", "occlusion=True", "WITH"),
        Pass("busker_off", 270, "Busker around the corner: no occlusion", 'occlusion=False  reverb="city_streets"',
             "WITHOUT", settings=STREETS),
        Pass("busker", 270, "Busker around the corner", 'occlusion=True  reverb="city_streets"', "WITH",
             settings=STREETS),
    ),
    gain_db=9.0,
)
OCCLUSION = {"bike_off": False, "bike": True, "busker_off": False, "busker": True}
C = 343.0
FADE_IN_S = 0.2
MARGIN_S = 0.25
"""The faded end arrives this long before its pass ends (S3)."""

# --- motorbike ---------------------------------------------------------------------------------------
# The houses' fronts are on y = 0, facing the camera (-Y); the road runs behind them along X.

HOUSE_W, HOUSE_D, HOUSE_H = 12.0, 6.0, 7.0
HOUSES_X = (-36.0, -12.0, 12.0, 36.0)
"""Middles of the four houses: 12 m wide with gaps of 12 m."""
CAM_BIKE = (0.0, -45.0, 1.6)
LENS_BIKE = 70.0
ROAD_Y = HOUSE_D + 4.0
BIKE_X = (-50.0, 50.0)
"""The motorbike drives 100 m in the 9 s of a pass, 40 km/h."""
BIKE_S = 9.0
ENGINE_Z = 0.7
TYRES_Z = 0.3
BIKE_FADE_OUT_S = 0.5


def bike_x(t: float) -> float:
    return BIKE_X[0] + (BIKE_X[1] - BIKE_X[0]) * t / BIKE_S


def bike_position(t: float) -> tuple[float, float, float]:
    return (bike_x(t), ROAD_Y, ENGINE_Z)


def house_boxes() -> list[tuple[float, float, float, float]]:
    """(x0, y0, x1, y1) of the houses' walls, seen from above."""
    return [(x - HOUSE_W / 2, 0.0, x + HOUSE_W / 2, HOUSE_D) for x in HOUSES_X]


def crosses(a: tuple[float, float], b: tuple[float, float], box: tuple[float, float, float, float]) -> bool:
    """Whether the segment a-b passes through the rectangle (Liang-Barsky)."""
    t0, t1 = 0.0, 1.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    for p, q in ((-dx, a[0] - box[0]), (dx, box[2] - a[0]), (-dy, a[1] - box[1]), (dy, box[3] - a[1])):
        if p == 0:
            if q < 0:
                return False
        else:
            r = q / p
            if p < 0:
                t0 = max(t0, r)
            else:
                t1 = min(t1, r)
            if t0 > t1:
                return False
    return True


def open_line(a, b, boxes) -> bool:
    return not any(crosses(a[:2], b[:2], box) for box in boxes)


def bike_edges(step: float = 0.001) -> list[float]:
    """Times in the pass (as seen) at which the line from the camera to the motorbike opens or
    closes: 1.59, 2.52, 3.92, 5.08, 6.48, 7.41 s."""
    out, prev, t = [], None, 0.0
    while t <= BIKE_S:
        now = open_line(CAM_BIKE, bike_position(t), house_boxes())
        if prev is not None and now != prev:
            out.append(round(t, 3))
        prev, t = now, t + step
    return out


def bike_heard_delay(t: float) -> float:
    """Travel time (s) of the sound heard at about t (the motorbike moves at 3 % of c)."""
    p = bike_position(t)
    return math.dist(p, CAM_BIKE) / C


# --- busker ------------------------------------------------------------------------------------------
# Relative to the corner: the main street runs along X (centre y = 0, house fronts at y = +-9); the
# side street leaves it to the north between x = 0 and x = 6. The set stands at CORNER_X.

CORNER_X = 1000.0
FRONT = 9.0
SIDE_W = 6.0
CORNER_HOUSE = (-12.0, FRONT, 0.0, FRONT + 14.0)
"""The house on the near corner, which hides the busker."""
BUSKER = (3.0, FRONT + 8.0)
"""In the middle of the side street, 8 m from the corner."""
BUSKER_Z = 1.15
"""The accordion, at chest height."""
CAM_Y = FRONT - 3.0
WALK_MPS = 1.5
OPEN_S = 4.2
"""The corner opens the line of sight 4.2 s into the pass."""
TUNE_S = 7.0
BUSKER_FADE_OUT_S = 0.3
LENS_BUSKER = 28.0


def open_x() -> float:
    """The camera's x at which the line to the busker clears the corner (0, FRONT)."""
    bx, by = BUSKER
    k = (FRONT - CAM_Y) / (by - CAM_Y)
    return -k * bx / (1 - k)


CAM_X0 = open_x() - WALK_MPS * OPEN_S


def camera_busker(t: float) -> tuple[float, float, float]:
    """The walking camera t seconds into a busker pass (relative to the corner)."""
    return (CAM_X0 + WALK_MPS * min(max(t, 0.0), 9.0), CAM_Y, 1.6)


def busker_yaw(t: float) -> float:
    """The camera's compass heading (degrees, 0 = +Y, 90 = -X): ahead along the street (-90) until
    2.5 s, turning to the busker by 5 s (he is in the frame when the corner opens), then on him."""
    x, y, _ = camera_busker(t)
    bearing = math.degrees(math.atan2(-(BUSKER[0] - x), BUSKER[1] - y))
    w = min(max((t - 2.5) / 2.5, 0.0), 1.0)
    w = w * w * (3 - 2 * w)
    return -90.0 + (bearing + 90.0) * w


def busker_open(t: float) -> bool:
    return open_line(camera_busker(t), BUSKER, [CORNER_HOUSE])
