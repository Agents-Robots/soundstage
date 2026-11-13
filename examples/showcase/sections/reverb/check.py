"""Known answers of ``reverb`` (README.md), asserted on the probes: clicks on every ball and clap
frame of the four rooms, white-noise bursts on the two claps of ``walk``. The direct sound is the
probes' own group stem, the reverberation the ``reverb`` stem.

    .venv/bin/python examples/showcase/sections/reverb/check.py [--dir out/showcase/reverb]
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1]), str(HERE)]

import numpy as np  # noqa: E402
from kit import measure  # noqa: E402
from kit.checks import Check  # noqa: E402
from scipy import signal  # noqa: E402
from section import BOUNCES_S, CLAPS_S, DECAY_S, ROOMS, WALK_CLAPS_S, send_db  # noqa: E402

BAND = (500.0, 2000.0)


def band(x: np.ndarray, rate: int) -> np.ndarray:
    sos = signal.butter(4, BAND, btype="bandpass", fs=rate, output="sos")
    return signal.sosfilt(sos, measure.mono(x))


def t30(x: np.ndarray, rate: int) -> float:
    """Decay time from the Schroeder curve of x (starting at the excitation), fitted from -5 to
    -35 dB and extended to 60 dB."""
    e = np.cumsum((x ** 2)[::-1])[::-1]
    db = 10 * np.log10(e / e[0] + 1e-30)
    i0, i1 = np.argmax(db <= -5), np.argmax(db <= -35)
    t = np.arange(i0, i1) / rate
    slope = np.polyfit(t, db[i0:i1], 1)[0]
    return -60.0 / slope


def run(c: Check) -> None:
    rate = c.rate
    probes = {k: c.probe(k, stems=True) for k in (*ROOMS, "walk")}
    silent = probes["outdoors"].stems.get("reverb")
    level = -999.0 if silent is None or not np.any(silent) else measure.db(np.abs(silent).max())
    c.expect("outdoors: the reverb stem", f"{level:.0f} dBFS", "below -120 dBFS", level < -120)

    direct = {}
    for k in ROOMS:
        sid = f"reverb.probe.{k}.click_clap"
        x = probes[k].stems["probe"]
        direct[k] = measure.rms_db(x[:c.t(k, CLAPS_S[-1] + 0.2)])
        late = []
        for name, times in (("click_ball", BOUNCES_S), ("click_clap", CLAPS_S)):
            for s in times:
                want = (c.geo.arrival(f"reverb.probe.{k}.{name}", c.frame(k, s)) - c.windows[k][0]) / 30
                a = c.t(k, want - 0.02)
                on = measure.onsets(x[a:a + c.t(k, 0.05)], rate)
                late.append(1000 * (on[0] - 0.02) if on else float("nan"))
        w = max(late, key=abs)
        c.expect(f"{k}: click onsets at frame + distance / c ({len(late)} clicks)", f"max {w:+.2f} ms", "0 ± 1 ms",
                 abs(w) <= 1.0)
        if k == "outdoors":
            continue
        rv = probes[k].stems["reverb"]
        start = (c.geo.arrival(sid, c.frame(k, CLAPS_S[-1])) - c.windows[k][0]) / 30
        got = t30(band(rv, rate)[c.t(k, start):], rate)
        c.near(f"{k}: decay time of the reverb stem after the last click (T30, 500 Hz to 2 kHz)", got, DECAY_S[k],
               0.1 * DECAY_S[k], "s", 2)
    worst = max(abs(direct[k] - direct["outdoors"]) for k in ROOMS)
    c.expect("direct sound of the four rooms against outdoors", f"max {worst:.3f} dB", "within 0.1 dB", worst <= 0.1)

    # walk: the second burst 12.6 m farther
    k, sid = "walk", "reverb.probe.walk.burst"
    x = probes[k]
    d_band, r_band = band(x.stems["probe"], rate), band(x.stems["reverb"], rate)
    d, r, dist = [], [], []
    for s in WALK_CLAPS_S:
        arrive = (c.geo.arrival(sid, c.frame(k, s)) - c.windows[k][0]) / 30
        a = c.t(k, arrive)
        d.append(measure.rms_db(d_band[a:a + c.t(k, 0.1)]))
        r.append(10 * np.log10(np.sum(r_band[a:a + c.t(k, 4.5)] ** 2)))
        dist.append(float(c.geo.distance(sid, c.frame(k, s), c.frame(k, s))))
    want_d = 20 * np.log10(dist[0] / dist[1])
    want_r = send_db(dist[1], DECAY_S[k]) - send_db(dist[0], DECAY_S[k])
    c.near(f"walk: direct sound of the second burst against the first ({dist[0]:.2f} m, {dist[1]:.2f} m)",
           d[1] - d[0], want_d, 0.3, "dB", 2)
    c.near("walk: reverb stem of the second burst against the first", r[1] - r[0], want_r, 0.5, "dB", 2)
    c.near("walk: direct-to-reverberant ratio, change", (d[1] - d[0]) - (r[1] - r[0]), want_d - want_r, 0.6, "dB", 2)


if __name__ == "__main__":
    Check.main(run, "reverb")
