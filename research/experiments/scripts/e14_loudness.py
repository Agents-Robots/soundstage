"""E14: loudness report and master processing: integrated loudness, loudness range and true peak
on EBU test signals and on a rendered mix, each against ffmpeg's ebur128 meter as an independent
implementation; the true-peak limiter on a loud mix with transients.

Writes research/figures/e14_limiter.png. Needs ffmpeg on PATH.
"""

import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample

from soundstage.engine import mix, report

from common import RATE, render, sample, save, scene, sine, table

TMP = Path(tempfile.mkdtemp(prefix="e14_"))


def tone(levels_db, seconds, f=1000.0) -> np.ndarray:
    parts = [10 ** (db / 20) * np.sin(2 * np.pi * f * np.arange(int(s * RATE)) / RATE) for db, s in zip(levels_db, seconds)]
    x = np.concatenate(parts)
    return np.stack([x, x], axis=1)


def ffmpeg_meter(audio: np.ndarray, name: str) -> dict:
    path = TMP / f"{name}.wav"
    sf.write(path, audio, RATE, subtype="FLOAT")
    out = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-filter_complex", "ebur128=peak=true",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    summary = out[out.rindex("Summary:"):]
    def value(label):
        m = re.search(label + r":\s+(-?[\d.]+|-inf)", summary)
        return float(m.group(1))
    return {"I": value("I"), "LRA": value("LRA"), "TP": value("Peak")}


def ours(audio: np.ndarray) -> dict:
    m = report.metrics(audio, RATE)
    return {"I": m["lufs_integrated"], "LRA": m["loudness_range_lu"], "TP": m["true_peak_dbtp"]}


def faded(x: np.ndarray, seconds: float = 0.1) -> np.ndarray:
    n = int(seconds * RATE)
    ramp = np.ones(len(x))
    ramp[:n] = np.linspace(0, 1, n)
    ramp[-n:] = np.linspace(1, 0, n)
    return x * ramp[:, None]


def main() -> None:
    t = np.arange(4 * RATE) / RATE
    tp = 0.5 * np.sin(2 * np.pi * RATE / 4 * t + np.pi / 4)
    cases = [
        ("Tech 3341 #1: 1 kHz at -23 dBFS", tone([-23], [20]), "I -23.0"),
        ("Tech 3341 #2: 1 kHz at -33 dBFS", tone([-33], [20]), "I -33.0"),
        ("Tech 3341 #3: -36/-23/-36 dBFS, 10/60/10 s", tone([-36, -23, -36], [10, 60, 10]), "I -23.0"),
        ("Tech 3341 #4: -72/-36/-23/-36/-72, 10/10/60/10/10 s", tone([-72, -36, -23, -36, -72], [10, 10, 60, 10, 10]),
         "I -23.0"),
        ("Tech 3342 #1: -20/-30 dBFS, 20 s each", tone([-20, -30], [20, 20]), "LRA 10"),
        ("Tech 3342 #2: -20/-15", tone([-20, -15], [20, 20]), "LRA 5"),
        ("Tech 3342 #3: -40/-20", tone([-40, -20], [20, 20]), "LRA 20"),
        ("Tech 3342 #4: -50/-35/-20/-35/-50", tone([-50, -35, -20, -35, -50], [20] * 5), "LRA 15"),
        ("true peak: fs/4 at 45 degrees, amplitude 0.5", faded(np.stack([tp, tp], axis=1)), "TP -6.02"),
    ]

    noise = np.random.default_rng(2).standard_normal(RATE * 4) * 0.2
    srcs = [{"sample": sample("noise.wav", noise), "group": "traffic"},
            {"sample": sample("sine.wav", sine(220.0, 3.0)), "group": "engines", "gain_db": -6},
            {"sample": sample("click.wav", np.r_[1.0, np.zeros(RATE // 4)]), "mode": "once", "frame": [40, 140, 240]}]
    path = np.stack([np.linspace(-60, 60, 361), np.full(361, 8.0), np.zeros(361)], axis=1)
    res = render.render(scene(srcs, np.stack([path, path[::-1] * [1, 2, 1], path * 0 + [3, 5, 0]], axis=1),
                              frame_end=360, settings={"reverb": "city"}), stems=True)
    cases.append(("rendered mix: 3 sources, city reverb, 12 s", res.audio, "-"))

    rows = []
    for label, audio, expected in cases:
        a, b = ours(audio), ffmpeg_meter(audio, label.split(":")[0].replace(" ", "_").replace("#", ""))
        def fmt(v):
            return "-" if v is None else f"{v:.2f}"
        rows.append([label, expected, f"{fmt(a['I'])} / {b['I']:.1f}", f"{fmt(a['LRA'])} / {b['LRA']:.1f}",
                     f"{fmt(a['TP'])} / {b['TP']:.1f}"])
    print("Integrated loudness (LUFS), loudness range (LU), true peak (dBTP): soundstage / ffmpeg ebur128\n")
    print(table(["signal", "expected", "I", "LRA", "TP"], rows))

    # limiter: the rendered mix pushed to -8 LUFS, limited at -1 dBTP
    audio, stems = res.audio.copy(), {k: v.copy() for k, v in res.stems.items()}
    before = ours(audio * mix.normalize_gain(audio, RATE, -8.0))
    info = mix.finish(audio, stems, RATE, normalize=-8.0, limit=-1.0)
    after = ours(audio)
    curve = audio[:, 0] / np.where(np.abs(res.audio[:, 0]) > 1e-9, res.audio[:, 0], np.nan) / \
        10 ** (info["normalize_gain_db"] / 20)
    gain = mix.true_peak_limiter(res.audio * 10 ** (info["normalize_gain_db"] / 20), RATE, -1.0)
    slope = np.abs(np.diff(20 * np.log10(gain))) * RATE / 1000  # dB per ms
    peaks = mix.true_peak(res.audio * 10 ** (info["normalize_gain_db"] / 20))
    first = int(np.argmax(peaks > 10 ** (-1 / 20)))
    lead = (first - int(np.argmax(gain < 0.999))) / RATE * 1000
    print(f"\nLimiter on the mix normalized to -8 LUFS (gain {info['normalize_gain_db']:+.2f} dB), ceiling -1 dBTP:\n")
    print(table(["", "I LUFS", "TP dBTP (ours)", "TP dBTP (ffmpeg)"],
                [["before", f"{before['I']:.2f}", f"{before['TP']:.2f}",
                  f"{ffmpeg_meter(res.audio * 10 ** (info['normalize_gain_db'] / 20), 'before')['TP']:.1f}"],
                 ["after", f"{after['I']:.2f}", f"{after['TP']:.2f}", f"{ffmpeg_meter(audio, 'after')['TP']:.1f}"]]))
    peak = int(np.argmax(mix.true_peak(audio)))
    seg = audio[max(0, peak - 4096): peak + 4096]
    sinc = 20 * np.log10(np.abs(resample(seg, len(seg) * 32, axis=0)).max())
    print(f"\nafter, ideal (sinc) reconstruction around the highest peak, 32x: {sinc:.3f} dBTP")
    print(f"max reduction {info['limiter_max_reduction_db']:.2f} dB, active {info['limiter_active_s']:.3f} s; "
          f"gain starts falling {lead:.1f} ms before the first overshoot; fastest gain change "
          f"{slope.max():.2f} dB/ms; stems after limiting sum to the master within "
          f"{np.abs(sum(stems.values()) - audio).max():.1e}")
    del curve

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    pre_all = res.audio * 10 ** (info["normalize_gain_db"] / 20)
    top = int(np.argmax(peaks))
    ch = int(np.argmax(np.abs(pre_all[top])))
    i0, i1 = top - int(0.03 * RATE), top + int(0.25 * RATE)
    tt = (np.arange(i0, i1) - top) / RATE * 1000
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(tt, pre_all[i0:i1, ch], lw=0.6, color="0.7", label="normalized input")
    ax.plot(tt, audio[i0:i1, ch], lw=0.6, label="limited output")
    ax.plot(tt, gain[i0:i1], lw=1.5, label="limiter gain")
    ax.axhline(10 ** (-1 / 20), ls="--", lw=0.8, color="k", label="ceiling -1 dBTP")
    ax.axhline(-10 ** (-1 / 20), ls="--", lw=0.8, color="k")
    ax.set(xlabel="ms from the highest input peak", ylabel="amplitude / gain",
           title=f"true-peak limiter at the loudest click ({'left' if ch == 0 else 'right'} channel)")
    ax.legend(loc="lower right")
    save(fig, "e14_limiter.png")


if __name__ == "__main__":
    main()
