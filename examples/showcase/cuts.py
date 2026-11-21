"""The cuts of the showcase (sections/README.md, "Cuts"): section keys in order. ``key:body`` takes the
section without its title page; a ``Clip`` takes part of one pass, or its title page (``TITLE_PAGE``).
Nothing else depends on the order."""

from typing import NamedTuple


class Clip(NamedTuple):
    """Seconds [start, end) of one pass, from its first frame (whole frames; ``end`` None: to the pass's
    end); the pass ``TITLE_PAGE`` is the section's title page. ``gain_db`` is a fixed gain for this clip (a
    trailer evens out sections that are quiet by design; no normalization). ``tail`` seconds of the
    clip's sound run on under the next part, fading out; the clip's sound is otherwise faded in and out
    over ``EDGE_FADE_S`` where it is cut."""

    key: str
    pass_key: str
    start: float = 0.0
    end: float | None = None
    gain_db: float = 0.0
    tail: float = 0.0


EDGE_FADE_S = 0.015
TITLE_PAGE = "@title"


def chapter(key: str, *passes: str) -> tuple[Clip, ...]:
    """A section's title page and some of its passes, whole."""
    return (Clip(key, TITLE_PAGE), *(Clip(key, p) for p in passes))


FULL = (
    Clip("intro", "sound"),
    *chapter("doppler", "siren", "race", "train"),
    *chapter("delay", "physical"),
    *chapter("occlusion", "bike", "busker"),
    *chapter("around", "lap"),
    *chapter("directivity", "cones"),
    *chapter("reverb", "livingroom", "church"),
    *chapter("screen", "screen"),
    *chapter("distance", "air"),
    *chapter("sources", "loop", "events", "pitch"),
    *chapter("cuts", "per_camera"),
    "city",
    "production",
    "finale",
    "outro",
)
"""About 6.5 minutes: the features first (Doppler, delay, occlusion), each mostly in the pass where it
is on; then the scale, the animations and the evening in the town with what it took."""
TRAILER = (
    Clip("production", "race", 20.6, 26.9, tail=1.2),   # the flyby: a racer at 612 km/h, the whine three times lower
    Clip("slates", "not_recorded"),
    Clip("slates", "title"),
    Clip("doppler", "siren", 2.5, 6.5),               # the ambulance through the pass
    Clip("delay", "physical", 7.6, 13.0),             # lightning; the thunder 3 s later
    Clip("occlusion", "busker", 2.5, 7.5),            # round the corner, the accordion opens up
    Clip("reverb", "church", 0.4, 4.4),               # the bounces in a church
    Clip("cuts", "per_camera", 1.0, 6.5),             # five cameras, the sound cuts with them
    Clip("slates", "thousands"),
    Clip("city", "night", 15.0, 26.0),                # into the boulevard among 10 000 cars
    Clip("production", "metropolis", 9.0, 17.0),      # music on a party terrace, neon signs round the tower
    Clip("finale", "town", 63.5, 71.5),               # the fireworks' closing salvo over the town
    "outro",
)
CUTS = {
    "full": FULL,
    "trailer": TRAILER,
}
