"""Known answers of ``occlusion`` (README.md), asserted on the pink-noise probes on the motorbike and
at the accordion: octave-band levels of each default pass against its ``_off`` pass at the same
time (which leaves the occlusion alone), the baked visibility against the line of sight, the
distance law without occlusion, the reverb stem of the busker passes.

    .venv/bin/python examples/showcase/sections/occlusion/check.py [--dir out/showcase/occlusion]
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1]), str(HERE)]

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from kit import measure  # noqa: E402
from kit.checks import Check  # noqa: E402
from section import OPEN_S, TUNE_S, bike_edges, bike_heard_delay  # noqa: E402

FPS = 30
BANDS = (250.0, 1000.0, 4000.0)
HIDDEN = (-12.1, -13.6, -21.1)
"""Fully hidden: the transmission T(f) = -12 dB / sqrt(1 + (f / 1500 Hz)^2) at the band centres."""
WINDOW_S = 0.3


def octaves(x: np.ndarray, rate: int) -> np.ndarray:
    m = measure.mono(x)
    return np.array([measure.band_db(m, rate, f / 2 ** 0.5, f * 2 ** 0.5) for f in BANDS])


def visibility(c: Check, source_id: str):
    """Times in the pass (s) and the baked visibility (samples, bands) of a source."""
    z = np.load(c.dir / "bake" / "scene.npz")
    man = json.loads((c.dir / "bake" / "scene.json").read_text())
    k = next(s["track"] for s in man["sources"] if s["id"] == source_id)
    return z["vis_frames"], z["src_visibility"][:, k, :]


def crossings(t: np.ndarray, v: np.ndarray, level: float = 0.5) -> list[float]:
    out = []
    for i in range(1, len(v)):
        if (v[i - 1] - level) * (v[i] - level) < 0:
            out.append(float(t[i - 1] + (level - v[i - 1]) / (v[i] - v[i - 1]) * (t[i] - t[i - 1])))
    return out


def run(c: Check) -> None:
    rate = c.rate
    bike = {k: c.probe(k, "noise").audio for k in ("bike_off", "bike")}

    def diff(t: float, w: float = WINDOW_S) -> np.ndarray:
        a, b = c.t("bike", t - w / 2), c.t("bike", t + w / 2)
        return octaves(bike["bike"][a:b], rate) - octaves(bike["bike_off"][a:b], rate)

    # the line of sight as seen; heard later by the travel time
    edges = bike_edges()
    heard = [e + bike_heard_delay(e) for e in edges]
    end_heard = 9.0 - 0.25 - 0.5  # the faded end arrives MARGIN_S before the pass ends
    hidden = [((0.0 if i == 0 else edges[2 * i - 1]) + (edges[2 * i] if i < 3 else 8.0)) / 2 for i in range(4)]
    for i, t in enumerate(hidden):
        th = min(t + bike_heard_delay(t), end_heard - 0.3)
        got = diff(th)
        for band, g, want in zip(BANDS, got, HIDDEN):
            c.near(f"bike: behind house {i + 1} ({th:.2f} s heard), {band:g} Hz", g, want, 1.5, "dB", 1)
    for i in range(3):
        a, b = heard[2 * i], heard[2 * i + 1]
        ts = np.arange(a, b, 0.02)
        best = np.max([diff(t, 0.2) for t in ts], axis=0)
        outer = i != 1
        c.near(f"bike: gap {i + 1} ({a:.2f} to {b:.2f} s heard), highest at 1 kHz", best[1], 0.0, 1.0, "dB", 2)
        c.near(f"bike: gap {i + 1}, highest at 4 kHz", best[2], 0.0, 1.0, "dB", 2)
        if outer:
            c.expect(f"bike: gap {i + 1}, highest at 250 Hz (seen at an angle)", f"{best[0]:.2f} dB", "at least -3 dB",
                     best[0] >= -3.0)
        else:
            c.near(f"bike: gap {i + 1}, highest at 250 Hz", best[0], 0.0, 1.0, "dB", 2)

    # the baked visibility: hidden and open, and its changes against the line of sight
    vf, vis = visibility(c, "occlusion.probe.bike.noise")
    first = c.windows["bike"][0]
    t = (vf - first) / FPS
    sel = (t >= 0) & (t < 9.0)
    t, vis = t[sel], vis[sel]
    for label, times, want in (("behind the houses' middles", [h + bike_heard_delay(h) for h in hidden[:3]], 0.0),
                               ("in the gaps' middles", [(heard[2 * i] + heard[2 * i + 1]) / 2 for i in range(3)], 1.0)):
        vals = [vis[np.argmin(abs(t - x))] for x in times]
        worst = float(np.max(np.abs(np.array(vals) - want)))
        c.expect(f"bike: baked visibility {label}, all bands", f"max |v - {want:g}| {worst:.2f}", "0", worst == 0)
    cross = crossings(t, vis[:, 1])
    c.expect("bike: visibility at 1 kHz opens three times", f"{sum(1 for i in range(0, len(cross), 2))} openings",
             "3", len(cross) == 6)
    if len(cross) == 6:
        err = max(abs(a - b) for a, b in zip(cross, heard))
        c.expect("bike: visibility changes (1 kHz passes 0.5) against the line of sight heard",
                 f"max {err:.2f} s", "within 0.3 s", err <= 0.3)

    # fall faster than rise (followers of 60 and 150 ms), at 4 kHz, from -3 to -15 dB
    step = 0.005
    ts = np.arange(0.3, end_heard - 0.3, step)
    env = np.array([diff(x, 0.04)[2] for x in ts])
    falls, rises = [], []
    for e in heard[:-1]:
        near = (ts > e - 0.4) & (ts < e + 0.5)
        seg, st = env[near], ts[near]
        hi, lo = np.nonzero(seg > -3.0)[0], np.nonzero(seg < -15.0)[0]
        if not len(hi) or not len(lo):
            continue
        if seg[0] > seg[-1]:  # a house comes into the way
            falls.append(st[lo[0]] - st[hi[hi < lo[0]][-1]] if np.any(hi < lo[0]) else np.nan)
        else:
            rises.append(st[hi[0]] - st[lo[lo < hi[0]][-1]] if np.any(lo < hi[0]) else np.nan)
    c.expect("bike: an edge at 4 kHz, -3 to -15 dB: falling faster than rising",
             f"fall {np.nanmean(falls) * 1000:.0f} ms, rise {np.nanmean(rises) * 1000:.0f} ms", "fall < rise",
             np.nanmean(falls) < np.nanmean(rises))

    # without occlusion the level follows the distance: the probe less the emitted noise and the
    # distance law, 200 Hz to 1 kHz (below the air absorption)
    noise = sf.read(c.dir.parents[0] / "sounds" / "noise_pink.wav")[0]
    sid = "occlusion.probe.bike_off.noise"
    first = c.windows["bike_off"][0]
    rest = []
    for x in np.arange(0.5, end_heard - 0.6, 0.1):
        f = c.frame("bike_off", x)
        te = (c.geo.emission(sid, f) - first) / FPS
        a = int(round((te - 0.1) * rate))
        emitted = noise[np.arange(a, a + int(0.2 * rate)) % len(noise)]
        seg = measure.mono(bike["bike_off"][c.t("bike_off", x - 0.1):c.t("bike_off", x + 0.1)])
        rest.append(measure.band_db(seg, rate, 200, 1000) - measure.band_db(emitted, rate, 200, 1000)
                    - c.geo.direct_gain_db(sid, f))
    spread = (max(rest) - min(rest)) / 2
    jump = float(np.max(np.abs(np.diff(rest))))
    closest = max(c.geo.direct_gain_db(sid, c.frame("bike_off", x)) for x in np.arange(0.5, 8.0, 0.05))
    c.near("bike_off: distance law at the closest point (55 m), relative to 10 m", closest, -14.8, 0.05, "dB", 2)
    c.expect("bike_off: level less the distance law, 200 Hz to 1 kHz", f"± {spread:.2f} dB, steps {jump:.2f} dB",
             "constant within ± 0.5 dB, no step above 0.3 dB", spread <= 0.5 and jump <= 0.3)

    # busker: the direct sound (the probe's own group stem; the reverb is its own stem)
    busk = {k: c.probe(k, "noise", stems=True) for k in ("busker_off", "busker")}
    direct = {k: r.stems["probe"] for k, r in busk.items()}

    def bdiff(t: float, w: float = WINDOW_S) -> np.ndarray:
        a, b = c.t("busker", t - w / 2), c.t("busker", t + w / 2)
        return octaves(direct["busker"][a:b], rate) - octaves(direct["busker_off"][a:b], rate)

    early = np.array([bdiff(x) for x in np.arange(0.3, 2.0, 0.1)])
    for j, (band, want) in enumerate(zip(BANDS, HIDDEN)):
        worst = early[:, j][np.argmax(np.abs(early[:, j] - want))]
        c.near(f"busker: first 2 s, fully hidden, {band:g} Hz (worst window)", worst, want, 1.5, "dB", 1)
    late = np.array([bdiff(x) for x in np.arange(6.5, TUNE_S - WINDOW_S / 2, 0.1)])
    worst = float(np.max(np.abs(late)))
    c.expect("busker: 6.5 s to the end of the tune, all bands", f"max |d| {worst:.2f} dB", "0 ± 0.5 dB", worst <= 0.5)
    vf, vis = visibility(c, "occlusion.probe.busker.noise")
    t = (vf - c.windows["busker"][0]) / FPS
    sel = (t >= 0) & (t < 9.0)
    cross = crossings(t[sel], vis[sel][:, 1])
    c.expect("busker: visibility at 1 kHz passes 0.5", ", ".join(f"{x:.2f} s" for x in cross) or "never",
             f"once, {OPEN_S} ± 0.4 s", len(cross) == 1 and abs(cross[0] - OPEN_S) <= 0.4)
    rv = {k: r.stems["reverb"] for k, r in busk.items()}
    lv = {k: measure.short_term_db(measure.mono(x), rate, 0.4, 0.1) for k, x in rv.items()}
    live = lv["busker_off"] > -70
    d = float(np.max(np.abs(lv["busker"][live] - lv["busker_off"][live])))
    c.expect("busker: the reverb stem with occlusion against without (obstruction, R4)", f"max {d:.2f} dB",
             "within 0.5 dB", d <= 0.5)
    real = {k: c.stem(k, "reverb") for k in ("busker_off", "busker")}
    lv = {k: measure.short_term_db(measure.mono(x), rate, 0.4, 0.1) for k, x in real.items()}
    live = lv["busker_off"] > -70
    d = float(np.max(np.abs(lv["busker"][live] - lv["busker_off"][live])))
    c.expect("busker: the accordion's reverb stem with occlusion against without", f"max {d:.2f} dB", "within 0.5 dB",
             d <= 0.5)


if __name__ == "__main__":
    Check.main(run, "occlusion")
