"""Known answers of ``production`` (README.md): the race's whine before and after the closest pass of
its flyby shot against the Doppler factor of 612 km/h, the race's frames from the newest render, the
metropolis render with its music, and the render time the callout states. The race's shots must be
the animation's current cut: after a recut its renders hold other cameras at some frames.

    .venv/bin/python examples/showcase/sections/production/check.py [--dir out/showcase/production]
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1]), str(HERE)]

from kit import measure, story  # noqa: E402
from kit.checks import C, Check  # noqa: E402
from section import ANIM_FPS, RACE_BPM, RACE_CUT, RACE_FRAME, RACE_SHOTS, RACE_STEMS, RENDER_CLAIM_S, SPEECH_DUCK_DB  # noqa: E402
from steps import projects, race_renders  # noqa: E402

SPEED = 170.0
"""The racers' speed in the animation (m/s): 612 km/h."""
WHINE_HZ = 1050.0
"""The whine's pitch at rest in the race (its ``audio/make_samples.py``)."""
FLYBY = "flyby_omega"
BEFORE_S, AFTER_S = (3.0, 3.35), (4.2, 5.2)
"""Seconds into the flyby shot: the racer coming (it is heard from 3.0 s; the pass is at about 3.6 s),
going."""


def run(c: Check) -> None:
    rate = c.rate
    x = measure.mono(c.pass_audio("race"))
    shot = sum(n for camera, _, _, n in RACE_SHOTS[:[s[0] for s in RACE_SHOTS].index(FLYBY)]) / story.FPS
    coming = measure.frequency(x[int((shot + BEFORE_S[0]) * rate):int((shot + BEFORE_S[1]) * rate)], rate,
                               WHINE_HZ * C / (C - SPEED))
    going = measure.frequency(x[int((shot + AFTER_S[0]) * rate):int((shot + AFTER_S[1]) * rate)], rate,
                              WHINE_HZ * C / (C + SPEED))
    # head-on at 612 km/h; the animation's camera moves too, so the measured ratio may differ a little
    c.near(f"race: whine coming / going ({coming:.0f} / {going:.0f} Hz, {FLYBY} at {shot:.2f} s) against "
           "(c + v) / (c - v)", coming / going, (C + SPEED) / (C - SPEED), 0.15, "", 2)
    c.near("race: whine coming against its pitch at rest times c / (c - v), x 1001/1000 (30 fps)", coming,
           WHINE_HZ * C / (C - SPEED) * 1001 / 1000, 0.05 * WHINE_HZ * C / (C - SPEED), "Hz", 0)

    summary = json.loads((c.dir / "production.report.json").read_text())
    rows = {r["pass"]: r for r in summary["passes"]}
    origin = rows["race"]["anim_mix"]
    c.expect("race: only the stems SoundStage rendered", ", ".join(origin["stems"]), ", ".join(RACE_STEMS),
             tuple(origin["stems"]) == RACE_STEMS)
    lifted = max(origin["lifted_db_max"].values())
    c.expect("race: the step back under the radio voices undone", f"lifted by up to {lifted:.1f} dB",
             f"at most {SPEECH_DUCK_DB:g} dB", lifted <= SPEECH_DUCK_DB + 0.01)
    # the shots: camera, beats and, where the cut gives it, the first race frame
    cut = json.loads((projects()["race"] / RACE_CUT).read_text())["shots"]
    beat = 60 / RACE_BPM * ANIM_FPS["race"]
    ours = [(camera, round(n / beat), race0) for camera, _, race0, n in RACE_SHOTS]
    differ = [f"{i + 1}: {o[0]} {o[1]} beats from {o[2]}, cut {s}" for i, (o, s) in enumerate(zip(ours, cut))
              if (o[0], o[1]) != (s[0], s[1]) or (len(s) > 2 and s[2] != o[2])]
    if len(ours) != len(cut):
        differ.append(f"{len(ours)} shots, cut {len(cut)}")
    c.expect(f"race: the shots as the animation cuts them ({RACE_CUT})", "; ".join(differ) or f"{len(ours)} as cut",
             "all as cut", not differ)
    # the frames: every shot from the newest render of its pass
    stale = []
    for camera, render_pass, race0, n in RACE_SHOTS:
        newest = race_renders(render_pass)[0]
        missing = sum(not (newest / RACE_FRAME.format(f)).exists() for f in range(race0, race0 + n))
        if missing:
            stale.append(f"{camera} {missing} of {n}")
    c.expect("race: every shot from the newest render of its pass",
             "; ".join(stale) or "all", "all (else: frames from an older render)", not stale)

    anim = rows["metropolis"]["anim_render"][0]
    c.expect("metropolis: the music in the render", ", ".join(anim["groups"]), "'music' among them",
             "music" in anim["groups"])
    c.expect("metropolis: sources rendered", rows["metropolis"]["sources"], "2200", rows["metropolis"]["sources"] == 2200)
    far = anim["far_field"] or {}
    c.expect("metropolis: sources in the far field (reported)", f"{far.get('far_sources')}", "reported", True)
    t = rows["metropolis"]["render_seconds"]
    workers = (anim["timing_s"] or {}).get("workers")
    seconds = (rows["metropolis"]["frames"][1] - rows["metropolis"]["frames"][0] + 1) / story.FPS
    c.expect(f"metropolis: render time of the {seconds:.0f} s (load, culling, DSP): the callout's claim",
             f"{t:.1f} s, {workers} workers", f"under {RENDER_CLAIM_S} s on 16 cores / 32 threads",
             t < RENDER_CLAIM_S and workers == 32)


if __name__ == "__main__":
    Check.main(run, "production")
