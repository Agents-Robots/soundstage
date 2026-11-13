"""Build ``intro`` (README.md) in Blender: a street at dusk, an ambulance and a car passing, a
pedestrian; the same action twice, first silent, then tagged.

    blender -b --factory-startup -y --python examples/showcase/sections/intro/build.py -- [--out DIR]
"""

import argparse
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1]), str(HERE)]

from kit.blender import base, models, overlay, town  # noqa: E402
from mathutils import Vector  # noqa: E402
from section import (  # noqa: E402
    CAMERA_X,
    CAR_PASS_AT_S,
    CAR_SPEED,
    NOTE,
    PASS_AT_S,
    SECTION,
    SOURCES_END_FRAME,
    SPEED,
    TAGLINE,
    WORDMARK_FRAME,
)

from soundstage.blender import tag  # noqa: E402

S = SECTION
FPS = base.story.FPS
LEAD_S = 1.0


def amb_at(t: float) -> Vector:
    """The ambulance, t seconds after the start of a pass: towards -X in the lane at +1.75."""
    return Vector((CAMERA_X + SPEED * (PASS_AT_S - t), town.LANE, models.VEHICLE_Z))


def car_at(t: float) -> Vector:
    """The car: towards +X in the lane at -1.75."""
    return Vector((CAMERA_X + CAR_SPEED * (t - CAR_PASS_AT_S), -town.LANE, models.VEHICLE_Z))


def action(amb, car_, walker, window) -> list[tuple[float, str]]:
    """Key one run of the action from the start of ``window``; returns the walker's step contacts."""
    f0, f1 = window.first, window.last
    t1 = (f1 - f0) / FPS  # the run ends on the pass's last frame: the next pass keys the frame after
    models.drive(amb, [(f0, amb_at(0)), (f1, amb_at(t1))], heading_deg=90)
    models.drive(car_, [(f0, car_at(0)), (f1, car_at(t1))], heading_deg=-90)
    models.blink(amb, [(f0, f1)])
    return models.walk(walker, Vector((CAMERA_X + 22.0, 7.4, 0.12)), 90, f0, steps=16, first_s=0.6)


def follower(name: str, at, heading_deg: float, window, lead_s: float = LEAD_S):
    """An empty on the path of the sound pass from ``lead_s`` before it starts. The sounds ride on
    it, so that what is on its way when the pass begins (the siren, 90 m away, 0.26 s) is heard on
    its first frame; the visible vehicle is elsewhere in those frames (the silent pass)."""
    e = base.empty(name)
    e.rotation_euler = (0, 0, math.radians(heading_deg + 180))
    t1 = window.seconds
    base.runs(e, "location", [[(window.first - lead_s * FPS, at(-lead_s)), (window.last + 1, at(t1))]])
    return e


def build(out: Path) -> Path:
    base.new_scene(S)
    base.world("dusk")
    parked = [(CAMERA_X - 14, -town.PARKING, "car_blue"), (CAMERA_X - 21, -town.PARKING, "car_grey"),
              (CAMERA_X + 27, -town.PARKING, "car_green"), (CAMERA_X + 34, town.PARKING, "car_grey"),
              (CAMERA_X + 52, town.PARKING, "car_red"), (CAMERA_X + 75, -town.PARKING, "car_blue")]
    town.build("dusk", parked)

    cam = base.camera("intro.cam", (CAMERA_X, -4.25, base.EYE), lens=24.0,
                      rotation=base.aim(None, yaw_deg=-90 + 25, pitch_deg=2.0))
    amb = models.ambulance("ambulance")
    car_ = models.car("car", "car_grey", lights=True)
    walker = models.figure("walker", shirt="jacket")

    silent, sound = S.window("silent"), S.window("sound")
    action(amb, car_, walker, silent)
    steps = action(amb, car_, walker, sound)

    # sounds: the sound pass only (ids intro.sound.*), on followers; the probe sits on the light bar
    amb_sound = follower("ambulance.sound", amb_at, 90, sound)
    bar = base.empty("ambulance.sound.lightbar", next(o for o in amb.children if o.name == "ambulance.lightbar").location,
                     amb_sound)
    car_sound = follower("car.sound", car_at, -90, sound)
    end = SOURCES_END_FRAME
    start = sound.first - LEAD_S * FPS
    cone = dict(cone_inner_deg=120.0, cone_outer_deg=300.0, cone_outer_gain_db=-8.0, forward_axis="-Y")
    tag.add_sound(bar, "siren_two_tone.wav", id=S.source_id("sound", "siren"), frame=start, end_frame=end,
                  fade_in=0.0, fade_out=0.5, ref_distance=8.0, group="vehicles", **cone)
    tag.add_sound(bar, "sine_1k.wav", id=S.probe_id("sound", "siren"), frame=start, end_frame=end,
                  fade_in=0.0, fade_out=0.5, ref_distance=8.0, loop_phase=0.0, **cone)
    tag.add_sound(amb_sound, "car_engine.wav", id=S.source_id("sound", "amb_engine"), frame=start, end_frame=end,
                  fade_in=0.0, fade_out=0.5, pitch=0.9, ref_distance=4.0, group="vehicles")
    tag.add_sound(amb_sound, "tyre_noise.wav", id=S.source_id("sound", "amb_tyres"), frame=start, end_frame=end,
                  fade_in=0.0, fade_out=0.5, ref_distance=4.0, gain_db=-6.0, offset=(0, 1.9, -0.4), group="vehicles")
    tag.add_sound(car_sound, "car_engine.wav", id=S.source_id("sound", "car_engine"), frame=start, end_frame=end,
                  fade_in=0.0, fade_out=0.5, ref_distance=4.0, gain_db=-4.0, group="vehicles")
    tag.add_sound(car_sound, "tyre_noise.wav", id=S.source_id("sound", "car_tyres"), frame=start, end_frame=end,
                  fade_in=0.0, fade_out=0.5, ref_distance=4.0, gain_db=-6.0, offset=(0, 1.35, -0.4), group="vehicles")
    for i in range(4):
        frames = [f for j, (f, _) in enumerate(steps) if j % 4 == i and f < end]
        if frames:
            tag.add_sound(walker, f"footstep_{i + 1}.wav", mode="once", frame=frames, id=S.source_id("sound", f"step_{i + 1}"),
                          ref_distance=2.0, group="people")
    root = base.empty("intro.bed")
    tag.add_sound(root, "town_bed.wav", id=S.source_id("sound", "bed"), spatial=False, gain_db=-18.0, frame=sound.first,
                  fade_in=0.5, end_frame=465, fade_out=1.0, group="ambience")

    # overlays: two labels, the wordmark card over the running shot, fades from and to black
    overlay.centred_label(cam, "intro.silent", S.passes[0].label, (silent.first, silent.last))
    label = overlay.centred_label(cam, "intro.sound", S.passes[1].label, (sound.first, WORDMARK_FRAME + 12))
    label.opacity([(WORDMARK_FRAME, 1.0), (WORDMARK_FRAME + 12, 0.0)])
    card = overlay.wordmark_card(cam, "intro", TAGLINE, NOTE, (WORDMARK_FRAME, sound.last))
    card.opacity([(WORDMARK_FRAME, 0.0), (WORDMARK_FRAME + 12, 1.0)])
    overlay.fade_black(cam, "intro.in", (1, 9), None, (1, 9))
    overlay.fade_black(cam, "intro.out", None, (sound.last - 8, sound.last), (sound.last - 8, sound.last))

    return base.finish(S, [(1, cam)], out)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=str(base.REPO / "out" / "showcase" / S.key))
    build(Path(p.parse_args(argv).out))
