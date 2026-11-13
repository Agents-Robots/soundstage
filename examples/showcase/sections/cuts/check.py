"""Known answers of ``cuts`` (README.md), asserted on the probes on the lead car (a 1 kHz sine and a
click every 0.5 s): after every cut of ``per_camera`` the sound is what the new camera alone hears
(renders of the same pass from bakes with that camera as the fixed listener); on board the sine is
steady; ``one_mic`` is one smooth Doppler curve heard from camera A.

    .venv/bin/python examples/showcase/sections/cuts/check.py [--dir out/showcase/cuts]
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1]), str(HERE)]

import numpy as np  # noqa: E402
from kit import audio, measure  # noqa: E402
from kit.checks import Check, Geometry  # noqa: E402
from section import SHOT_FRAMES, SHOT_S, SHOTS  # noqa: E402

from soundstage.engine.scene import load_scene  # noqa: E402

FPS = 30
AFTER = (0.010, 0.060)
"""The 50 ms after a cut, from the end of the engine's 10 ms crossfade, which starts at the cut."""


def power_db(x: np.ndarray) -> float:
    return 10 * np.log10(max(float(np.mean(np.sum(x ** 2, axis=1))), 1e-30))


def run(c: Check) -> None:
    rate = c.rate
    first, last = c.windows["per_camera"]
    sine = {k: c.probe(k, "sine").audio for k in ("one_mic", "per_camera")}
    x = sine["per_camera"]

    rep = c.pass_report("per_camera")
    inside = [f for f in rep["cuts"] if first < f <= last]
    want = [first + SHOT_FRAMES * j for j in range(1, len(SHOTS))]
    c.expect("per_camera: cuts in the report", ", ".join(f"{f:g}" for f in inside), ", ".join(map(str, want)),
             inside == want)
    rep1 = c.pass_report("one_mic")
    c.expect("one_mic: cuts in the report", rep1["cuts"] or "none", "none", not rep1["cuts"])

    # what each camera alone hears through the pass, from the bakes with a fixed listener
    p = next(p for p in c.man["passes"] if p["key"] == "per_camera")
    alone = {}
    for name in sorted(set(SHOTS)):
        scene = load_scene(c.dir / f"bake_cam_{name}" / "scene.json", {"master_gain_db": 0.0, **p["settings"]})
        alone[name] = audio.render_frames(scene, first, last, ["cuts.probe.per_camera.sine"]).audio
    for j in range(1, len(SHOTS)):
        t, name = j * SHOT_S, SHOTS[j]
        a, b = c.t("per_camera", t + AFTER[0]), c.t("per_camera", t + AFTER[1])
        got, ref = x[a:b], alone[name][a:b]
        f_got, f_ref = measure.frequency(got, rate, 1000), measure.frequency(ref, rate, 1000)
        before = measure.frequency(x[c.t("per_camera", t - AFTER[1]):c.t("per_camera", t - AFTER[0])], rate, 1000)
        c.expect(f"cut {j} at {t:g} s to {name.upper()}: sine frequency in the 50 ms after",
                 f"{f_got:.1f} Hz (before {before:.1f})", f"{f_ref:.1f} Hz ± 0.5 %", abs(f_got / f_ref - 1) <= 0.005)
        c.near(f"cut {j} to {name.upper()}: sine level in the 50 ms after, against {name.upper()} alone",
               power_db(got) - power_db(ref), 0.0, 0.5, "dB", 2)
        # the crossfade: no sample step around the cut larger than the signal's own on either side
        n = c.t("per_camera", t)
        d = np.abs(np.diff(x, axis=0))
        around = d[n - int(0.002 * rate):n + int(0.012 * rate)].max()
        sides = max(d[n - int(0.06 * rate):n - int(0.002 * rate)].max(), d[n + int(0.012 * rate):n + int(0.06 * rate)].max())
        c.expect(f"cut {j}: largest sample step from 2 ms before to 12 ms after", f"{around:.2e} (sides {sides:.2e})",
                 "at most 1.05 x the sides", around <= 1.05 * sides)
    # the whole pass: shot by shot, what that camera alone hears
    worst = 0.0
    for j, name in enumerate(SHOTS):
        a, b = c.t("per_camera", j * SHOT_S + 0.06), c.t("per_camera", (j + 1) * SHOT_S - 0.06)
        worst = max(worst, float(np.max(np.abs(x[a:b] - alone[name][a:b]))))
    c.expect("per_camera: every shot, from 60 ms after its cut, against its camera alone", f"max |d| {worst:.1e}",
             "below 1e-5 (the same samples)", worst < 1e-5)

    # on board: no Doppler, constant level
    for j in (1, 4):
        a, b = c.t("per_camera", j * SHOT_S + 0.1), c.t("per_camera", (j + 1) * SHOT_S - 0.1)
        f = measure.frequency(x[a:b], rate, 1000)
        lv = measure.short_term_db(measure.mono(x[a:b]), rate, 0.2, 0.1)
        c.near(f"per_camera shot {j + 1} (on board): sine frequency", f, 1000.0, 0.5, "Hz", 2)
        c.expect(f"per_camera shot {j + 1} (on board): sine level", f"spread {np.ptp(lv):.3f} dB", "within 0.1 dB",
                 np.ptp(lv) <= 0.1)

    # clicks: emitted on their frames, heard after the distance to the shot's camera (those that
    # arrive within the shot they were emitted in)
    clicks = c.probe("per_camera", "click").audio
    geo = {name: Geometry(c.dir / f"bake_cam_{name}") for name in set(SHOTS)}
    late, n = [], 0
    for i in range(28):
        e = 0.25 + 0.5 * i
        name = SHOTS[int(e // SHOT_S)]
        arrive = (geo[name].arrival("cuts.probe.per_camera.click", c.frame("per_camera", e)) - first) / FPS
        if arrive > (int(e // SHOT_S) + 1) * SHOT_S - 0.01:
            continue
        n += 1
        a = c.t("per_camera", arrive - 0.02)
        on = measure.onsets(clicks[a:a + c.t("per_camera", 0.05)], rate)
        late.append(1000 * (on[0] - 0.02) if on else float("nan"))
    w = max(late, key=abs)
    c.expect(f"per_camera: click onsets at emission + distance / c ({n} clicks)", f"max {w:+.2f} ms", "0 ± 1 ms",
             abs(w) <= 1.0)

    # one microphone: shot 1 of per_camera is the same; the sine glides smoothly all the way
    a, b = c.t("one_mic", 0.1), c.t("one_mic", SHOT_S - 0.06)
    d = float(np.max(np.abs(measure.short_term_db(measure.mono(sine["one_mic"][a:b]), rate, 0.1, 0.05)
                            - measure.short_term_db(measure.mono(x[a:b]), rate, 0.1, 0.05))))
    c.expect("per_camera shot 1 and one_mic, first 2.5 s", f"max {d:.3f} dB", "within 0.1 dB", d <= 0.1)
    g1 = Geometry(c.dir / "bake_one_mic")
    sid = "cuts.probe.one_mic.sine"
    t, f = measure.frequency_track(sine["one_mic"][:c.t("one_mic", 13.0)], rate, 0.1, 0.02, 1000)
    keep = t > 0.3
    t, f = t[keep], f[keep]
    expected = np.array([1000 * g1.rate(sid, c.frame("one_mic", x_)) for x_ in t])
    err = float(np.max(np.abs(f / expected - 1)))
    c.expect("one_mic: sine frequency against the Doppler of camera A, 0.3 to 13 s", f"max {100 * err:.2f} %",
             "within 0.5 %", err <= 0.005)
    steps = float(np.max(np.abs(np.diff(f) - np.diff(expected))))
    c.expect("one_mic: no steps: the change per 20 ms against the Doppler's", f"max {steps:.2f} Hz", "within 1 Hz",
             steps <= 1.0)
    for at_s, label in ((2.5, "leaving"), (10.0, "coming back along the far straight")):
        i = int(np.argmin(np.abs(t - at_s)))
        c.near(f"one_mic: sine at {at_s:g} s ({label})", f[i], expected[i], 0.005 * expected[i], "Hz", 1)

    for k in ("one_mic", "per_camera"):
        clamps = [w for w in c.pass_report(k)["warnings"] if "clamp" in w]
        c.expect(f"{k}: no playback-rate clamp warning", clamps or "none", "none", not clamps)


if __name__ == "__main__":
    Check.main(run, "cuts")
