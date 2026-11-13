"""Storyboard of ``doppler`` (README.md): four pass-bys at constant speed, three moving sources and a
moving camera, with the playback rate each one is heard at."""

import math
from dataclasses import dataclass

from kit.story import FPS, Pass, Section, TitlePage

SECTION = Section(
    key="doppler",
    title="Doppler effect",
    title_page=TitlePage(
        title="Doppler effect",
        claim="An approaching source sounds higher, a leaving one lower. The shift follows from the motion in "
              "the scene.",
        code="doppler_factor = 1.0",
        listen="the drop in pitch at the moment of passing.",
    ),
    passes=(
        Pass("siren_off", 270, "Ambulance, 72 km/h: no Doppler", "doppler_factor=0", "WITHOUT",
             settings={"doppler_factor": 0.0}),
        Pass("siren", 270, "Ambulance, 72 km/h", "doppler_factor=1", "WITH"),
        Pass("race", 210, "Race car, 252 km/h", 'doppler_factor=1  quality="high"', settings={"quality": "high"}),
        Pass("plane", 300, "Propeller plane, 216 km/h, 80 m away", 'doppler_factor=1  quality="high"',
             settings={"quality": "high"}),
        Pass("train", 240, "From a moving train, 108 km/h", "doppler_factor=1"),
    ),
    gain_db=-2.0,
    reference="siren",
)

C = 343.0
FADE_IN_S = 0.2
FADE_OUT_S = 0.5
MARGIN_S = 0.25
"""A source's faded end arrives this long before its pass ends (S3, R5)."""


@dataclass(frozen=True)
class PassBy:
    """A straight line at constant speed along +X of the pass's set, from ``start_m`` to ``end_m``
    over the whole pass, ``closest`` metres from the camera at x = 0. ``source_z`` and ``camera_z``
    are the heights of the probed emitter and of the camera; the rest of the offset is sideways.
    ``moving`` is what moves: the source (camera at rest) or the camera (source at rest)."""

    speed: float
    closest: float
    start_m: float
    end_m: float
    source_z: float
    camera_z: float
    moving: str = "source"

    @property
    def lateral(self) -> float:
        return math.sqrt(self.closest ** 2 - (self.source_z - self.camera_z) ** 2)

    def x(self, t: float) -> float:
        """Position along the line of the moving thing, t seconds into the pass."""
        return self.start_m + self.speed * t

    def r(self, x: float) -> float:
        return math.hypot(x, self.closest)

    def emitted(self, t_heard: float) -> float:
        """When the sound heard at t_heard (s into the pass) left the source."""
        t = t_heard
        for _ in range(60):
            if self.moving == "source":
                t = t_heard - self.r(self.x(t)) / C
            else:
                t = t_heard - self.r(self.x(t_heard)) / C
        return t

    def heard(self, t_emitted: float) -> float:
        """When the sound emitted at t_emitted (s into the pass) reaches the camera."""
        t = t_emitted
        for _ in range(60):
            t = t_emitted + self.r(self.x(t_emitted if self.moving == "source" else t)) / C
        return t

    def rate(self, t_heard: float) -> float:
        """Playback rate heard at t_heard: 1 / (1 + v_r / c) for a moving source (v_r its speed away
        from the camera at emission), 1 - v_r / c for a moving camera."""
        if self.moving == "source":
            x = self.x(self.emitted(t_heard))
            return 1 / (1 + self.speed * x / self.r(x) / C)
        x = self.x(t_heard)
        return 1 - self.speed * x / self.r(x) / C

    def end_s(self, pass_s: float) -> float:
        """Emission end (after the fade-out): its sound arrives MARGIN_S before the pass ends."""
        t = pass_s
        for _ in range(60):
            t -= self.heard(t) - (pass_s - MARGIN_S)
        return t


PASSBYS = {
    "siren_off": PassBy(20.0, 8.0, -90.0, 90.0, 2.65, 1.6),
    "siren": PassBy(20.0, 8.0, -90.0, 90.0, 2.65, 1.6),
    "race": PassBy(70.0, 15.0, -245.0, 245.0, 0.5, 1.6),
    "plane": PassBy(60.0, 80.0, -300.0, 300.0, 76.6, 1.6),
    "train": PassBy(30.0, 10.0, -120.0, 120.0, 3.0, 3.0, moving="camera"),
}
"""The probed emitters: the siren on the light bar, the race car's engine, the plane, the bell. The
plane flies 75 m above the camera and 27.8 m to the side (80 m away, 70 degrees up at the closest),
so that the camera can follow it without turning over."""

PLANE_SIDE = math.sqrt(80.0 ** 2 - 75.0 ** 2)
RACE_PITCH = 1.8
"""``race_engine.wav`` is a large car's engine at 100 Hz firing; raised to a racing engine's."""
BELL_LEAD_S = 1.5
"""The crossing bell rings before the pass starts, so that it is heard on its first frame."""
GAUGE_MARKS = (4, 2, 0, -2, -4)


def semitones(rate: float) -> float:
    return 12 * math.log2(rate)


def pass_seconds(key: str) -> float:
    return next(p.frames for p in SECTION.passes if p.key == key) / FPS
