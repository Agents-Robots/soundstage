"""E12: synthetic EFX reverb: decay per octave band for all presets (1/3-octave bank against the
earlier STFT tail), the reverb send's direct-to-reverberant ratio over distance, and a click
through the hangar bus.
"""

import math

import numpy as np
from scipy.fft import next_fast_len
from scipy.signal import butter, istft, sosfilt, sosfiltfilt, spectrogram, stft

from soundstage.engine import reverb

from common import RATE, render, rms_db, sample, save, scene, sine, table

FILM = ("generic", "room", "concerthall", "hangar", "city", "alley", "forest", "mountains", "underwater",
        "sewerpipe", "spacestation_hall", "spacestation_alcove", "factory_hall", "castle_hall")
OCTAVES = 1000 * 2.0 ** np.arange(-4, 5)  # 62.5 Hz .. 16 kHz


def stft_tail(noise: np.ndarray, p: dict, rate: int) -> np.ndarray:
    """The earlier implementation: decay applied per frame of a 1024-point STFT (47 Hz bins)."""
    f, frames, z = stft(noise, fs=rate, window="hann", nperseg=1024, noverlap=768, boundary="zeros", padded=True)
    z = z * np.exp(-3.0 * math.log(10.0) * np.maximum(frames, 0.0)[None, :] / reverb.decay_curve(f, p)[:, None])
    _, y = istft(z, fs=rate, window="hann", nperseg=1024, noverlap=768, boundary=True)
    return y[: len(noise)]


def three_band_tail(p: dict, seconds: float, zero_phase: bool) -> np.ndarray:
    """An earlier alternative: noise split into three bands at the reference frequencies with
    4th-order Butterworth filters, each band decayed with its own decay time. Causal: 24 dB/octave;
    forward and backward: 48 dB/octave."""
    n = int(seconds * RATE)
    noise = np.random.default_rng(1).standard_normal(n)
    run = sosfiltfilt if zero_phase else sosfilt
    def sos(f, kind):
        return butter(4, f, kind, fs=RATE, output="sos")
    lo = run(sos(p["lf_reference"], "lowpass"), noise)
    hi = run(sos(p["hf_reference"], "highpass"), noise)
    mid = run(sos(p["lf_reference"], "highpass"), run(sos(p["hf_reference"], "lowpass"), noise))
    t = np.arange(n) / RATE
    return sum(x * np.exp(-3.0 * math.log(10.0) * t / t60) for x, t60 in zip((lo, mid, hi), reverb.decay_times(p)))


def band_errors(y: np.ndarray, p: dict) -> list[tuple[float, float, float, float]]:
    """(centre, expected, measured, relative error) per octave band longer than the filter's ringing."""
    out = []
    for c in OCTAVES:
        band = (c / math.sqrt(2), min(c * math.sqrt(2), 0.45 * RATE))
        expected = reverb.expected_rt60(p, RATE, band)
        if expected >= 12 / c:
            got = reverb.rt60(y, RATE, band)
            out.append((c, expected, got, got / expected - 1))
    return out


def main() -> None:
    rows = []
    for name in FILM:
        p = reverb.preset(name)
        ir = reverb.synthesize(p, RATE, reverb.seed_for(name))
        e = np.abs([r[3] for r in band_errors(ir, p)]) * 100
        rows.append([name] + [f"{t:.2f}" for t in reverb.decay_times(p)]
                    + [f"{np.median(e):.1f} %", f"{e.max():.1f} %", f"{10 * np.log10(np.sum(ir ** 2) / 2):.1f}"])
    print("Film-relevant presets: decay times (s), measured T30 per octave band 63 Hz-16 kHz against the\n"
          "T30 the decay curve predicts for that band; IR energy per channel (dB)\n")
    print(table(["preset", "low", "mid", "high", "median error", "max error", "energy dB"], rows))

    summary, worst = [], {}
    for method in ("1/3-octave bank", "STFT 1024"):
        errs = []
        for name in sorted(reverb.presets()):
            p = reverb.preset(name)
            n = next_fast_len(int(1.1 * max(reverb.decay_times(p)) * RATE) + RATE // 10, real=True)
            noise = np.random.default_rng(1).standard_normal(n)
            y = reverb._decaying(noise, p, RATE) if method.startswith("1/3") else stft_tail(noise, p, RATE)
            errs += [(abs(r[3]), name, r[0], r[1], r[2]) for r in band_errors(y, p)]
        e = np.array([x[0] for x in errs]) * 100
        summary.append([method, len(e), f"{np.median(e):.1f} %", f"{np.percentile(e, 95):.1f} %", f"{e.max():.1f} %",
                        int(np.sum(e > 10))])
        worst[method] = sorted(errs, reverse=True)[:3]
    print("\nLate tail alone (noise, no early reflections or shelves), all presets, all octave bands\n")
    print(table(["method", "bands", "median", "95th pct", "max", "over 10 %"], summary))
    for method, w in worst.items():
        print(f"\nworst {method}: " + "; ".join(f"{n} {c:.0f} Hz expected {x:.2f} s got {g:.2f} s"
                                               for _, n, c, x, g in w))

    p = reverb.preset("hangar")
    band = (1.5 * p["hf_reference"], 3 * p["hf_reference"])
    print(f"\nHangar high band {band[0]:.0f}-{band[1]:.0f} Hz, preset high decay {reverb.decay_times(p)[2]:.2f} s: "
          f"3 bands causal 24 dB/oct {reverb.rt60(three_band_tail(p, 15.0, False), RATE, band):.2f} s, "
          f"forward-backward 48 dB/oct {reverb.rt60(three_band_tail(p, 15.0, True), RATE, band):.2f} s, "
          f"1/3-octave bank {reverb.rt60(reverb.synthesize(p, RATE, reverb.seed_for('hangar')), RATE, band):.2f} s")

    tone = sample("sine.wav", sine())
    drr = []
    for d in (5.0, 10.0, 20.0, 40.0):
        res = render.render(scene([{"sample": tone, "ref_distance": 5.0}], [[0, d, 0]], frame_end=90,
                                  settings={"reverb": "concerthall", "air_absorption": 0.0}), stems=True)
        dry = res.audio - res.stems["reverb"]
        drr.append([f"{d:.0f}", f"{rms_db(dry[RATE:]) - rms_db(res.stems['reverb'][RATE:]):.2f}"])
    print("\nDirect-to-reverberant ratio, concert hall (room rolloff 0), 1 kHz tone, ref distance 5 m\n")
    print(table(["distance m", "DRR dB"], drr))

    p = reverb.preset("hangar")
    click = np.zeros(RATE // 10)
    click[0] = 1.0
    res = render.render(scene([{"sample": sample("click.wav", click), "mode": "once", "frame": 10, "spatial": False,
                                "reverb_send_db": 0.0}], [], frame_end=450, settings={"reverb": "hangar"}), stems=True)
    wet = res.stems["reverb"]
    mid = (1000 / math.sqrt(2), 1000 * math.sqrt(2))
    print(f"\nClick through the hangar bus: reverb return T30 at 1 kHz {reverb.rt60(wet, RATE, mid):.2f} s "
          f"(expected {reverb.expected_rt60(p, RATE, mid):.2f} s, preset decay time {p['decay_time']:.2f} s)")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ir = reverb.synthesize(p, RATE, reverb.seed_for("hangar"))
    fig, (a, b) = plt.subplots(1, 2, figsize=(12, 4))
    mono = ir.sum(axis=1)
    t = np.arange(len(mono)) / RATE
    for c in (125, 1000, 8000):
        band = (c / math.sqrt(2), c * math.sqrt(2))
        x = sosfiltfilt(butter(4, band, "bandpass", fs=RATE, output="sos"), mono)
        edc = np.cumsum((x ** 2)[::-1])[::-1]
        expected = reverb.expected_rt60(p, RATE, band)
        line, = a.plot(t, 10 * np.log10(edc / edc[0] + 1e-30), label=f"{c} Hz (expected {expected:.2f} s)")
        a.plot(t, -60 * t / expected, "--", color=line.get_color(), lw=0.8)
    a.set(xlabel="s", ylabel="energy decay (dB)", ylim=(-70, 3), xlim=(0, 12),
          title="hangar: decay per octave band, dashed = expected")
    a.legend()
    f, tt, s = spectrogram(mono, RATE, nperseg=2048, noverlap=1536)
    b.pcolormesh(tt, f, 10 * np.log10(s + 1e-20), shading="auto", vmin=-160, vmax=-60)
    b.set(yscale="symlog", ylim=(50, 20000), xlabel="s", ylabel="Hz", title="hangar impulse response")
    save(fig, "e12_reverb.png")


if __name__ == "__main__":
    main()
