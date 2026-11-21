"""Known answers of ``finale`` (README.md), asserted on the probes that sit on the town's sources: the
cuts, the bell's delay and level from the drone and from the square, the ambulance's pitch and its
occlusion, the busker around the corner, the train's horn and the second crossing's bell, the zoom,
the scooter behind the camera, the fireworks; that no one-shot arrives just before a cut, that the
bursts clear the roofs, that the stems are written and that the sources keep their defaults.

    .venv/bin/python examples/showcase/sections/finale/check.py [--dir out/showcase/finale]
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1]), str(HERE)]

import numpy as np  # noqa: E402
from kit import hearing, measure  # noqa: E402
from kit.checks import Check  # noqa: E402
from section import (  # noqa: E402
    AMB_PASS_S,
    AMB_SPEED,
    BELL_S,
    BURSTS,
    BUSKER,
    BUSKER_SOUND_Z,
    HORN_S,
    PASS_S,
    RENDER_CLAIM_S,
    SCOOTER_BEHIND_S,
    SHOTS,
    SOURCES,
    SQUARE_CAM,
    ZOOM_S,
    corner_sight_s,
    frame,
    scooter_at,
    shot_window,
    square_lens,
    square_yaw,
    street_opening,
    tag_calls,
)

from soundstage.blender import schema  # noqa: E402
from soundstage.engine.filters import AirAbsorption, occlusion_filter, section_power  # noqa: E402
from soundstage.engine.propagation import interpolator_for  # noqa: E402

FPS = 30
HIDDEN = (-12.1, -13.6, -21.1)
"""Fully hidden, at 250 Hz, 1 kHz and 4 kHz (occlusion's defaults: -12 dB, 1500 Hz)."""
OCTAVES = (250.0, 1000.0, 4000.0)
GROUPS = ("ambience", "music", "bells", "vehicles", "people", "railway", "fireworks", "reverb")
ALLOWED = {"sample", "mode", "id", "frame", "end_frame", "ref_distance", "gain_db", "pitch", "fade_in", "fade_out",
           "group", "loop_phase", "loop_crossfade", "offset", "spatial"}
"""What a source of the mix may set (README, "Sounds"); every other key keeps its default."""


def octaves(x: np.ndarray, rate: int) -> np.ndarray:
    m = measure.mono(x)
    return np.array([measure.band_db(m, rate, f / 2 ** 0.5, f * 2 ** 0.5) for f in OCTAVES])


def visibility(c: Check, source_id: str, mean: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """Times in the pass (s) and the baked visibility of a source (its bands averaged, or all)."""
    z = np.load(c.dir / "bake" / "scene.npz")
    v = z["src_visibility"][:, c.geo.tracks[source_id], :]
    return (z["vis_frames"] - c.windows["town"][0]) / FPS, v.mean(axis=1) if mean else v


def occlusion_db(c: Check, source_id: str, times: list[float]) -> np.ndarray:
    """What the occlusion does to each octave of OCTAVES at reception times (s), from the baked
    visibility by the documented model (docs/spec/signal-model.md, "Occlusion"): per band the open
    share plus the transmission, smoothed; the lowest band gives the broadband gain, a one-pole
    low-pass fitted to the others the rest."""
    vt, v = visibility(c, source_id, mean=False)
    dt = 0.005
    grid = np.arange(vt[0], vt[-1], dt)
    vg = np.stack([np.interp(grid, vt, v[:, b]) for b in range(v.shape[1])], axis=1)
    scene = c.scene("town")
    gain, cutoff = occlusion_filter(vg, scene.visibility_bands, scene.settings["occlusion_gain_db"],
                                    scene.settings["occlusion_cutoff_hz"], dt)
    inv2 = np.where(np.isfinite(cutoff), 1.0 / np.square(cutoff), 0.0)
    out = []
    for t in times:
        te = t - float(c.geo.distance(source_id, c.frame("town", t), c.frame("town", t))) / 343.0
        g, x = np.interp(te, grid, gain), np.interp(te, grid, inv2)
        out.append([20 * np.log10(g) - 10 * np.log10(1 + f * f * x) for f in OCTAVES])
    return np.array(out)


def band_response(x: np.ndarray, rate: int, fc: float, h) -> float:
    """A filter's effect h(f) (dB) on the third octave around fc, weighted by x's spectrum in it."""
    p = (np.abs(np.fft.rfft(measure.mono(x) * np.hanning(len(x)))) ** 2)
    f = np.fft.rfftfreq(len(x), 1 / rate)
    sel = (f >= fc / 2 ** (1 / 6)) & (f < fc * 2 ** (1 / 6))
    return float(10 * np.log10(np.sum(p[sel] * 10 ** (np.array([h(v) for v in f[sel]]) / 10)) / np.sum(p[sel])))


def crossing_time(t: np.ndarray, f: np.ndarray, level: float = 1000.0) -> float:
    i = int(np.flatnonzero((f[:-1] - level) * (f[1:] - level) <= 0)[0])
    return float(t[i] + (level - f[i]) / (f[i + 1] - f[i]) * (t[i + 1] - t[i]))


def run(c: Check) -> None:
    rate = c.rate
    first, last = c.windows["town"]
    geo = c.geo

    def at(t: float) -> int:
        return c.t("town", t)

    # --- cuts, and the one-shots around them (R5) --------------------------------------------------------
    rep = c.pass_report("town")
    cuts = [round(frame(t)) for _, t in SHOTS[1:]]
    c.expect("cuts in the report", ", ".join(f"{f:g}" for f in rep["cuts"]), ", ".join(map(str, cuts)),
             [round(f) for f in rep["cuts"]] == cuts)
    worst, which = 99.0, ""
    for s in geo.man["sources"]:
        if s["mode"] != "once" or ".probe." in s["id"] or s.get("track") is None:
            continue
        for f in s["frame"] if isinstance(s["frame"], list) else [s["frame"]]:
            heard = geo.arrival(s["id"], f)
            before = [(cut - heard) / FPS for cut in cuts if cut > heard]
            if before and before[0] < worst:
                worst, which = before[0], f"{s['id']} at frame {f:g}"
    c.expect("one-shots: shortest time from arriving to the next cut (R5)", f"{worst:.2f} s ({which})",
             "at least 0.3 s", worst >= 0.3)

    # --- the bell: from the drone and from the square ----------------------------------------------------
    bell = c.probe("town", "bell", stems=True).stems["probe"]
    sid = "finale.probe.town.bell"
    late, levels = [], []
    for t in BELL_S:
        heard = (geo.arrival(sid, frame(t)) - first) / FPS
        on = measure.onsets(bell[at(heard - 0.02):at(heard + 0.05)], rate)
        late.append(1000 * (on[0] - 0.02) if on else float("nan"))
        seg = bell[at(heard - 0.002):at(heard + 0.02)]  # both channels' power: the same for any pan
        levels.append((heard, 10 * np.log10(sum(10 ** (measure.band_db(seg[:, ch], rate, 250.0, 1000.0) / 10)
                                                for ch in (0, 1)))))
    d0 = float(geo.distance(sid, frame(BELL_S[0]), geo.arrival(sid, frame(BELL_S[0]))))
    d3 = float(geo.distance(sid, frame(BELL_S[3]), geo.arrival(sid, frame(BELL_S[3]))))
    c.expect(f"bell: strikes 1 to 3 from the drone ({d0:.0f} m, {d0 / 343:.3f} s late), the fourth from the square "
             f"({d3:.0f} m, {d3 / 343:.3f} s): onsets at emission + distance / c",
             " ".join(f"{v:+.2f}" for v in late) + " ms", "0 ± 1 ms", max(abs(v) for v in late) <= 1.0)
    f = np.fft.rfftfreq(int(0.022 * rate), 1 / rate)
    f = f[(f >= 250) & (f < 1000)]
    fe = rate * interpolator_for("standard").oversample  # the air stage runs oversampled
    settings = c.scene("town").settings
    air = AirAbsorption(settings["air_temperature_c"], settings["air_humidity_pct"], fe)

    def air_db(d: float) -> float:
        """The engine's air absorption (its fit of ISO 9613-1) over the band, a flat spectrum."""
        p = air.params(np.array([d]))[0]
        power = np.prod([section_power(np.tan(np.pi * f / fe), p[k][None, :])[0] for k in range(len(p))], axis=0)
        return float(10 * np.log10(np.mean(power)))

    want = (geo.direct_gain_db(sid, frame(BELL_S[3]) + d3 / 343 * FPS) + air_db(d3)) - \
           (geo.direct_gain_db(sid, frame(BELL_S[2]) + d0 / 343 * FPS) + air_db(d0))
    c.near("bell: the fourth strike (square) above the third (drone), 250 Hz to 1 kHz", levels[3][1] - levels[2][1],
           want, 1.0, "dB", 1)

    # --- the ambulance: pitch and the houses -------------------------------------------------------------
    sine = c.probe("town", "amb_sine").audio
    amb = "finale.probe.town.amb_sine"
    for t in (9.3, 18.8):
        got = measure.frequency(sine[at(t - 0.1):at(t + 0.1)], rate, 1000)
        c.near(f"ambulance: sine at {t:g} s", got, 1000 * geo.rate(amb, frame(t)), 0.005 * 1000 * geo.rate(amb, frame(t)),
               "Hz", 1)
    a, b = shot_window("street")
    tt, ff = measure.frequency_track(sine[at(a + 0.2):at(b - 0.5)], rate, 0.1, 0.01, 1000)
    tt += a + 0.2
    ts = np.arange(a + 0.3, b - 0.6, 0.005)
    rates = np.array([geo.rate(amb, frame(t)) for t in ts])
    c.near("ambulance: through 1000 Hz at", crossing_time(tt, ff), crossing_time(ts, 1000 * rates), 0.03, "s", 2)
    noise = {k: c.probe("town", k, stems=True).stems["probe"] for k in ("amb_noise", "amb_open")}  # direct sound
    aid = "finale.probe.town.amb_noise"
    times = np.arange(a + 0.5, b - 1.0, 0.25)
    want, early, late_ = (occlusion_db(c, aid, list(times + dt)) for dt in (0.0, -0.15, 0.15))
    steady = np.max(np.abs(early - late_), axis=1) < 1.0  # the visibility does not change within the window
    times, want = times[steady], want[steady]
    errors, hidden = [], []
    for t, w in zip(times, want):
        d = octaves(noise["amb_noise"][at(t - 0.15):at(t + 0.15)], rate) - \
            octaves(noise["amb_open"][at(t - 0.15):at(t + 0.15)], rate)
        errors.append(float(np.max(np.abs(d - w))))
        if np.max(np.abs(w - HIDDEN)) < 0.3:
            hidden.append(d)
    c.expect(f"ambulance: octaves against no occlusion, every 0.25 s of the street shot ({len(times)} steady windows), "
             "against the baked visibility", f"max error {max(errors):.2f} dB", "within 1.5 dB", max(errors) <= 1.5)
    h = np.mean(hidden, axis=0)
    c.expect(f"ambulance behind the houses ({len(hidden)} windows)", " ".join(f"{v:+.1f}" for v in h) + " dB",
             " ".join(f"{v:+.1f}" for v in HIDDEN) + " ± 1.5", len(hidden) > 10 and np.max(np.abs(h - HIDDEN)) <= 1.5)
    vt, vis = visibility(c, aid)
    opened = vt[(vis > 0.99) & (vt > a - 1) & (vt < b)]
    lo, hi = street_opening()
    geo_open = sorted(AMB_PASS_S + ((lo + hi) / 2 - x) / AMB_SPEED for x in (lo, hi))
    c.expect("ambulance: in the open (baked, all bands) against the line of sight through the square's side",
             f"{opened.min():.2f} to {opened.max():.2f} s", f"{geo_open[0]:.2f} to {geo_open[1]:.2f} s ± 0.25",
             abs(opened.min() - geo_open[0]) <= 0.25 and abs(opened.max() - geo_open[1]) <= 0.25)

    # --- the busker around the corner --------------------------------------------------------------------
    a, b = shot_window("corner")
    busk = {k: c.probe("town", k, stems=True) for k in ("busker_noise", "busker_open")}
    bid = "finale.probe.town.busker_noise"
    times = (21.0, 30.5)
    for t, w in zip(times, occlusion_db(c, bid, list(times))):
        d = octaves(busk["busker_noise"].stems["probe"][at(t - 0.2):at(t + 0.2)], rate) - \
            octaves(busk["busker_open"].stems["probe"][at(t - 0.2):at(t + 0.2)], rate)
        c.expect(f"busker at {t:g} s: octaves against no occlusion, against the baked visibility",
                 " ".join(f"{v:+.1f}" for v in d) + " dB", " ".join(f"{v:+.1f}" for v in w) + " ± 1.5",
                 np.max(np.abs(d - w)) <= 1.5)
    vt, vis = visibility(c, bid, mean=False)
    seen = vt[(vis[:, -1] > 0.5) & (vt > a) & (vt < b)]
    c.expect("busker: the 4 kHz band half in sight from the walking camera, against the line of sight past the corner",
             f"{seen.min():.2f} s" if len(seen) else "never", f"{corner_sight_s():.2f} s ± 0.5",
             len(seen) > 0 and abs(seen.min() - corner_sight_s()) <= 0.5)
    rv = [measure.rms_db(busk[k].stems["reverb"][at(a):at(b)]) for k in ("busker_noise", "busker_open")]
    c.near("busker: reverb stem with occlusion against without, corner shot", rv[0] - rv[1], 0.0, 0.5, "dB", 2)

    # --- the train ---------------------------------------------------------------------------------------
    horn = c.probe("town", "horn_sine").audio
    hid = "finale.probe.town.horn_sine"
    for t in (31.3, 40.7):
        want = 1000 * geo.rate(hid, frame(t))
        c.near(f"train front (crossing camera): sine at {t:g} s", measure.frequency(horn[at(t - 0.1):at(t + 0.1)], rate, 1000),
               want, 0.005 * want, "Hz", 1)
    heard = (geo.arrival("finale.town.train_horn", frame(HORN_S)) - first) / FPS
    c.expect("train horn: heard at (reported)", f"{heard:.2f} s ({(heard - HORN_S) * 343:.0f} m)", "reported", True)
    a, b = shot_window("onboard")
    xs = c.probe("town", "xing2_sine").audio
    xid = "finale.probe.town.xing2_sine"
    for t in (a + 0.3, b - 0.4):
        want = 1000 * geo.rate(xid, frame(t))
        c.near(f"second crossing's bell (cab camera): sine at {t:g} s",
               measure.frequency(xs[at(t - 0.1):at(t + 0.1)], rate, 1000), want, 0.005 * want, "Hz", 1)
    tt, ff = measure.frequency_track(xs[at(a + 0.2):at(b - 0.3)], rate, 0.1, 0.01, 1000)
    tt += a + 0.2
    ts = np.arange(a + 0.3, b - 0.4, 0.005)
    c.near("second crossing's bell: through 1000 Hz at", crossing_time(tt, ff),
           crossing_time(ts, 1000 * np.array([geo.rate(xid, frame(t)) for t in ts])), 0.03, "s", 2)
    semis = 12 * np.log2(np.nanmax(ff) / np.nanmin(ff))
    c.expect("second crossing's bell: drop over the shot", f"{semis:.2f} semitones", "about 3 (2.8 to 3.1)",
             2.8 <= semis <= 3.1)
    cab = c.probe("town", "cab_sine").audio
    tt, ff = measure.frequency_track(cab[at(a + 0.2):at(b - 0.3)], rate, 0.2, 0.05, 1000)
    c.expect("a sine on the train, heard in its cab", f"{np.nanmin(ff):.2f} to {np.nanmax(ff):.2f} Hz",
             "1000.0 ± 0.5 Hz", np.nanmax(np.abs(ff - 1000)) <= 0.5)

    # --- the square: the zoom and the scooter behind -----------------------------------------------------
    busker = c.probe("town", "busker_noise", stems=True).stems["probe"]
    yaw = square_yaw()
    p = (BUSKER[0], BUSKER[1], BUSKER_SOUND_Z)
    for (t0, t1), label in (((49.4, 50.9), "before the zoom"), ((ZOOM_S[1] + 0.2, 58.6), "after the zoom")):
        seg = busker[at(t0):at(t1)]
        got = measure.band_db(seg[:, 0], rate, 200, 400) - measure.band_db(seg[:, 1], rate, 200, 400)
        lam = hearing.lateral(p, SQUARE_CAM, yaw, 0.0, square_lens((t0 + t1) / 2))
        c.near(f"busker {label} ({square_lens((t0 + t1) / 2):.0f} mm): left over right, 200 to 400 Hz", got,
               -hearing.right_minus_left_db(lam), 0.7, "dB", 2)
    sc = {k: c.probe("town", "scooter_noise", extra=e, stems=True).stems["probe"]
          for k, e in (("rear", None), ("off", hearing.REAR_OFF))}
    behind = SCOOTER_BEHIND_S + float(np.linalg.norm(np.subtract(scooter_at(SCOOTER_BEHIND_S), SQUARE_CAM))) / 343.0
    rho = hearing.rear_factor(scooter_at(SCOOTER_BEHIND_S), SQUARE_CAM, yaw, 0.0)
    seg = {k: v[at(behind - 0.06):at(behind + 0.06)] for k, v in sc.items()}
    for fc in (1000.0, 12000.0):
        got = measure.band_db(seg["rear"], rate, fc / 2 ** (1 / 6), fc * 2 ** (1 / 6)) - \
            measure.band_db(seg["off"], rate, fc / 2 ** (1 / 6), fc * 2 ** (1 / 6))
        want = band_response(seg["off"], rate, fc, lambda v: hearing.rear_db(v, rho, rate=fe)
                             - hearing.rear_db(v, rho, *hearing.REAR_OFF.values(), rate=fe))
        c.near(f"scooter straight behind ({behind:.2f} s, rho {rho:.2f}): rear cue against off, {fc / 1000:g} kHz third octave",
               got, want, 0.7, "dB", 2)

    # --- fireworks ---------------------------------------------------------------------------------------
    late = []
    for i, (t, d, *_) in enumerate(BURSTS):
        bid = f"finale.probe.town.burst_{i + 1}"
        x = c.probe("town", f"burst_{i + 1}").audio
        heard = (geo.arrival(bid, frame(t)) - first) / FPS
        on = measure.onsets(x[at(heard - 0.02):at(heard + 0.05)], rate)
        late.append((1000 * (on[0] - 0.02) if on else float("nan"), d, heard - t))
    w = max(late, key=lambda v: abs(v[0]))
    c.expect(f"bursts: onsets at the flash + distance / c, all {len(BURSTS)}", f"max {w[0]:+.2f} ms", "0 ± 1 ms",
             all(abs(v[0]) <= 1.0 for v in late))
    c.expect("bursts: delays (reported)", ", ".join(f"{d:.0f} m {s:.2f} s" for _, d, s in late), "reported", True)
    worst = 1.0
    for i, (t, *_) in enumerate(BURSTS):
        vt, vis = visibility(c, f"finale.town.burst_{i + 1}")
        worst = min(worst, float(np.interp(t, vt, vis)))
    c.expect("bursts: baked visibility on their flash frames (R6)", f"min {worst:.3f}", "at least 0.99", worst >= 0.99)

    # --- the pass alone: it is the trailer (R3) -----------------------------------------------------------
    x = c.pass_audio("town")
    edge = at(0.2)
    ends = [measure.db(np.abs(x[:edge]).max()), measure.db(np.abs(x[-edge:]).max())]
    c.expect("the pass's first and last 0.2 s (R3)", f"{ends[0]:.1f}, {ends[1]:.1f} dBFS", "below -60 dBFS",
             max(ends) < -60)

    # --- stems and settings ------------------------------------------------------------------------------
    missing = [g for g in GROUPS if not (c.dir / "passes" / f"finale.town_stem_{g}.wav").exists()]
    c.expect("stems per group (R8)", missing or "all eight", "all eight", not missing)
    raw = {}
    for s in json.loads((c.dir / "bake" / "scene.json").read_text())["sources"]:
        if ".probe." in s["id"]:
            continue
        for k, field in schema.SOURCE_KEYS.items():
            if k not in ALLOWED and k in s and s[k] != field.default and (s[k] or field.default):
                raw.setdefault(s["id"], []).append(f"{k}={s[k]}")
    c.expect("sources: no setting other than the README's differs from its default", raw or "none", "none", not raw)

    # --- what the scene took: the numbers on the card (R10) ----------------------------------------------
    ids = [x["id"] for x in json.loads((c.dir / "bake" / "scene.json").read_text())["sources"] if ".probe." not in x["id"]]
    c.expect("sources in the bake, probes left out: the card's number (R10)", len(ids), f"{SOURCES}", len(ids) == SOURCES)
    calls = tag_calls()
    c.expect("tag calls and their lines in build.py: the panel and the card (R10)",
             f"{len(calls)} calls, {sum(n for _, n in calls)} lines", "reported", True)
    summary = json.loads((c.dir / "finale.report.json").read_text())
    row, machine = summary["passes"][0], summary.get("machine") or {}
    c.expect(f"render time of the {PASS_S:.0f} s: the card's claim (R10)",
             f"{row['render_seconds']:.1f} s, {machine.get('cpu')}, {machine.get('threads')} threads",
             f"under {RENDER_CLAIM_S} s", row["render_seconds"] < RENDER_CLAIM_S)


if __name__ == "__main__":
    Check.main(run, "finale")
