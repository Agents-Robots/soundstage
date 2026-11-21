"""Known answers of ``doppler`` (README.md), asserted on the 1 kHz probes: the frequency heard at the
start and the end of each pass-by and along the whole sweep, against the playback rate from the
baked geometry; no shift without Doppler and on the camera's own train.

    .venv/bin/python examples/showcase/sections/doppler/check.py [--dir out/showcase/doppler]
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1]), str(HERE)]

import numpy as np  # noqa: E402
from kit import measure  # noqa: E402
from kit.checks import Check  # noqa: E402
from section import FADE_IN_S, FADE_OUT_S, PASSBYS, pass_seconds  # noqa: E402

NOMINAL = {"siren": (1061.7, 945.1, 0.003), "race": (1255.8, 830.8, 0.005), "plane": (1203.4, 855.4, 0.005),
           "train": (1087.2, 912.8, 0.003)}
"""README.md: first and last 0.25 s at the travel's ends, and the tolerance (relative)."""
TRACK_TOL = 0.005
"""Largest relative difference between the measured frequency track (50 ms windows) and the rate
from the geometry, over the whole sweep: a step or a glitch in the Doppler shift exceeds it."""


def audible_span(key: str) -> tuple[float, float]:
    """Seconds into the pass between which the probe sounds at full level (fades excluded)."""
    p = PASSBYS[key]
    end = p.end_s(pass_seconds(key)) - FADE_OUT_S
    start = 0.0 if key == "train" else p.heard(FADE_IN_S)
    return start, p.heard(end)


def run(c: Check) -> None:
    rate = c.rate
    sid = lambda k, n="sine": f"doppler.probe.{k}.{n}"  # noqa: E731
    tracks = {}

    def at(k: str, t: float) -> float:
        return c.frame(k, t)

    # siren rendered with Doppler off (for this check only, not shown): one pitch throughout. Each ear's
    # delay still follows the time difference between the ears, which swings by 0.3 ms as the ambulance
    # passes: up to 0.5 Hz up in one ear and down in the other, so the mono sum is measured, over 0.25 s
    x = c.probe("siren", extra={"doppler_factor": 0.0}).audio
    a, b = audible_span("siren")
    _, f = measure.frequency_track(x[int(a * rate):int(b * rate)], rate, 0.25, 0.05)
    err = float(np.nanmax(np.abs(f - 1000)))
    c.expect("siren, doppler_factor=0: probe at 1000 Hz throughout", f"max error {err:.2f} Hz", "within 0.5 Hz",
             err <= 0.5)

    for k in ("siren", "race", "plane", "train"):
        x = c.probe(k, "sine").audio
        a, b = audible_span(k)
        lo, hi, tol = NOMINAL[k]
        for label, (u, v), nominal in (("first", (a, a + 0.25), lo), ("last", (b - 0.25, b), hi)):
            got = measure.frequency(x[int(u * rate):int(v * rate)], rate, 1000)
            want = 1000 * c.geo.rate(sid(k), at(k, (u + v) / 2))
            c.near(f"{k}: {label} 0.25 s heard, against the geometry", got, want, tol * want, "Hz", 1)
            c.near(f"{k}: {label} 0.25 s against README.md", got, nominal, tol * nominal + abs(want - nominal), "Hz", 1)
        # the whole sweep against the geometry
        t, f = measure.frequency_track(x[int(a * rate):int(b * rate)], rate, 0.05, 0.02, 1000)
        t = t + a
        want = np.array([1000 * c.geo.rate(sid(k), at(k, s)) for s in t])
        dev = float(np.nanmax(np.abs(f / want - 1)))
        c.expect(f"{k}: frequency track = geometry over the pass ({len(t)} windows)", f"max {100 * dev:.2f} %",
                 f"within {100 * TRACK_TOL:g} %", dev <= TRACK_TOL)
        tracks[k] = (t, f, want)
        p = PASSBYS[k]
        mid = p.heard(-p.start_m / p.speed) if k != "train" else -p.start_m / p.speed
        storyboard = 1000 * p.rate(mid + 0.5)
        c.near(f"{k}: storyboard rate = baked geometry, 0.5 s after the pass", storyboard,
               1000 * c.geo.rate(sid(k), at(k, mid + 0.5)), 0.5, "Hz", 2)

    # siren: 1000 Hz at the moment of passing plus 8 m / 343 m/s
    t, f, _ = tracks["siren"]
    i = int(np.flatnonzero((f[:-1] >= 1000) & (f[1:] < 1000))[0])
    cross = t[i] + (f[i] - 1000) / (f[i] - f[i + 1]) * (t[i + 1] - t[i])
    c.near("siren: passes 1000 Hz after the pass starts", cross, 4.5 + 8 / 343, 0.02, "s", 3)

    # the probe on the camera's own train: no shift
    x = c.probe("train", "cab").audio
    a, b = audible_span("train")
    _, f = measure.frequency_track(x[int((a + FADE_IN_S) * rate):int(b * rate)], rate, 0.1, 0.05)
    err = float(np.nanmax(np.abs(f - 1000)))
    c.expect("train: probe on the train itself at 1000 Hz", f"max error {err:.2f} Hz", "within 0.5 Hz", err <= 0.5)

    for k in ("race", "plane"):
        rates = [s["rate"] for s in c.pass_report(k)["sources"] if s["id"].endswith(".engine")][0]
        quality = next(p for p in c.man["passes"] if p["key"] == k)["settings"].get("quality")
        c.expect(f"{k}: engine played faster than 1.09 and rendered with quality=high (R4)",
                 f"up to {rates[1]:.3f}, quality {quality}", "> 1.09, high", rates[1] > 1.09 and quality == "high")
    clamps = [w for k in c.windows for w in c.pass_report(k)["warnings"] if "clamp" in w]
    c.expect("report: no playback-rate clamp warning", clamps or "none", "none", not clamps)
    plot(c, tracks)


def plot(c: Check, tracks: dict) -> None:
    """Measured and expected frequency of each probe (read as an image)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, len(tracks), figsize=(4 * len(tracks), 3))
    for a, (k, (t, f, want)) in zip(ax, tracks.items()):
        a.plot(t, want, color="0.6", lw=3, label="geometry")
        a.plot(t, f, color="C1", lw=1, label="measured")
        a.set_title(k)
        a.set_xlabel("s into the pass")
    ax[0].set_ylabel("probe frequency (Hz)")
    ax[0].legend()
    fig.tight_layout()
    fig.savefig(c.dir / "probe_tracks.png", dpi=80)


if __name__ == "__main__":
    Check.main(run, "doppler")
