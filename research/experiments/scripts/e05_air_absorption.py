"""E05: ISO 9613-1 implementation and the choice of air-absorption filter.

1. The ISO 9613-1 formula against ISO 9613-2 Table 2 (octave bands, six climates).
2. Filter structures against the ISO loss (20 C, 50 % RH), fitted per distance by least squares on
   the loss in dB, at the 96 kHz emission rate: the original spec's one-pole at the 3 dB point of an
   f^2 law; one-poles fitted where the loss is below 20 dB (the earlier engine: 4); one-poles and
   second-order sections (with and without a pair of zeros each) fitted to follow ISO below 60 dB
   and to attenuate at least 60 dB beyond. Largest error over 1 m - 20 km in three regions: loss
   below 20 dB, 20-60 dB (50 Hz - 16 kHz), and how far the filter stays short of 60 dB where ISO
   exceeds it (up to 0.45 of the rate).
3. The engine's table (two sections with zeros) at 48 and 96 kHz, between its distances too, and
   its smoothness: the largest response change between distances 0.46 % apart.
4. The far field (48 kHz, a voice between two distance bands is the sum of their filters) against
   the full chain (96 kHz) and ISO, bands sqrt(2) and an octave apart.
5. Cost: the emission-side stage alone (ns per sample, one thread) and a full-chain render with air
   absorption on and off (48 moving sources, 20 s, one worker).
6. Doppler: one source approaching or receding at 80 m/s (or standing) 450-700 m away, rendered by
   the full chain (air absorption before the delay line, at the emitted frequency) and by the far
   field (after the read, at the received frequency): the far field minus the full chain per band.
   ``--doppler`` runs this section alone.
Writes research/figures/e05_air_absorption.png.
"""

import math
import sys
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numba  # noqa: E402
import numpy as np  # noqa: E402
from scipy.optimize import least_squares  # noqa: E402

from common import RATE, render, sample, save, scene, table  # noqa: E402
from soundstage.engine import farfield, filters, kernels  # noqa: E402

TABLE_2 = {
    (10, 70): [0.1, 0.4, 1.0, 1.9, 3.7, 9.7, 32.8, 117],
    (20, 70): [0.1, 0.3, 1.1, 2.8, 5.0, 9.0, 22.9, 76.6],
    (30, 70): [0.1, 0.3, 1.0, 3.1, 7.4, 12.7, 23.1, 59.3],
    (15, 20): [0.3, 0.6, 1.2, 2.7, 8.2, 28.2, 88.8, 202],
    (15, 50): [0.1, 0.5, 1.2, 2.2, 4.2, 10.8, 36.2, 129],
    (15, 80): [0.1, 0.3, 1.1, 2.4, 4.1, 8.3, 23.7, 82.8],
}
RATE_E = 96000
LMAX = filters.AIR_FIT_MAX_LOSS_DB
F = np.geomspace(50.0, 0.45 * RATE_E, 240)
T = np.tan(np.pi * F / RATE_E)
ALPHA = filters.iso9613_alpha(F)
COMPARE_M = np.geomspace(1.0, 20000.0, 40)


def onepole_loss(x: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Loss in dB of bilinear one-poles with log warped corners x."""
    w = t[:, None] / np.exp(x)[None, :]
    return (10.0 * np.log10(1.0 + w * w)).sum(axis=1)


def section_loss(x: np.ndarray, t: np.ndarray, zeros: bool) -> np.ndarray:
    """Loss in dB of second-order sections (log g, log R[, log z]) per section."""
    if zeros:
        return filters._air_loss(x, t, False)[0]
    p = np.exp(x.reshape(-1, 2))
    params = np.stack([p[:, 0], p[:, 1], np.zeros(len(p)), np.zeros(len(p))], axis=1)
    return -10.0 * np.log10(filters.section_power(t, params).prod(axis=0))


def structure(kind: str, n: int):
    """(loss function, start, lower, upper) of a structure with n poles (one-poles) or n sections."""
    g_lo, g_hi = math.log(math.tan(math.pi * 20.0 / RATE_E)), math.log(math.tan(math.pi * 0.49))
    if kind == "one-poles":
        return (lambda x: onepole_loss(x, T), np.log(np.full(n, 0.4)) + np.linspace(0, 1, n),
                np.full(n, g_lo), np.full(n, g_hi))
    zeros = kind == "sections with zeros"
    per = 3 if zeros else 2
    x0 = np.tile([math.log(math.tan(math.pi * 0.4)), math.log(0.7), math.log(3.0)][:per], n)
    x0[0::per] -= 0.2 * np.arange(n)
    lo = np.tile([g_lo, math.log(filters.AIR_DAMPING[0]), math.log(1.02)][:per], n)
    hi = np.tile([g_hi, math.log(filters.AIR_DAMPING[1]), math.log(60.0)][:per], n)
    return (lambda x: section_loss(x, T, zeros)), x0, lo, hi


def errors(loss: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Largest |error| where the loss is below 20 dB and 20-60 dB (50 Hz - 16 kHz), and how far the
    filter stays short of 60 dB where ISO exceeds it (up to 0.45 of the rate)."""
    e, band = np.abs(loss - target), F <= 16000.0
    low, mid = band & (target < 20.0), band & (target >= 20.0) & (target < LMAX)
    short = (np.minimum(target, LMAX) - loss)[target >= LMAX]
    return np.array([e[low].max() if low.any() else 0.0, e[mid].max() if mid.any() else 0.0,
                     short.max() if len(short) else -np.inf])


def compare(kind: str, n: int, region: float) -> np.ndarray:
    """Worst errors over COMPARE_M of a structure fitted where ISO is below ``region`` dB (and, for
    60 dB, made to attenuate at least that much beyond)."""
    loss_of, x, lo, hi = structure(kind, n)
    worst = np.full(3, -np.inf)
    for d in COMPARE_M:
        target = ALPHA * d
        if target[F <= 20000.0][-1] < filters.AIR_BYPASS_DB:
            continue
        follow = (F <= 20000.0) & (target < region)
        floor = np.minimum(target, LMAX)

        def res(v):
            loss = loss_of(v)
            beyond = np.minimum(loss - floor, 0.0) if region > 20.0 else 0.0 * loss
            return np.where(follow, loss - target, beyond)

        best = None
        for start in (x, x + 0.3):  # the warm start, and a nudged one
            r = least_squares(res, np.clip(start, lo + 1e-9, hi - 1e-9), bounds=(lo, hi))
            if best is None or r.cost < best.cost:
                best = r
        x = best.x
        worst = np.maximum(worst, errors(loss_of(x), target))
    return worst


def engine_errors(rate: int) -> tuple[float, ...]:
    """Worst errors of the engine's table over 2000 distances 1 m - 20 km (between its rows too), the
    largest response change between neighbouring ones where the loss is below 20 and 60 dB (to
    20 kHz), and the largest error at 16-20 kHz where the loss is below 20 dB."""
    air = filters.AirAbsorption(20, 50, rate)
    f = np.geomspace(50.0, 0.45 * rate, 240)
    alpha = filters.iso9613_alpha(f)
    worst, step20, step60, top, prev = np.full(3, -np.inf), 0.0, 0.0, 0.0, None
    for d in np.geomspace(1.0, 20000.0, 2000):
        loss, target = air.loss_db(f, d), alpha * d
        e, band = np.abs(loss - target), f <= 16000.0
        low, mid = band & (target < 20.0), band & (target >= 20.0) & (target < LMAX)
        short = (np.minimum(target, LMAX) - loss)[target >= LMAX]
        worst = np.maximum(worst, [e[low].max() if low.any() else 0.0, e[mid].max() if mid.any() else 0.0,
                                   short.max() if len(short) else -np.inf])
        hi = (f > 16000.0) & (f <= 20000.0) & (target < 20.0)
        top = max(top, float(e[hi].max()) if hi.any() else 0.0)
        if prev is not None:
            change = np.abs(loss - prev)
            step20 = max(step20, float(change[(loss < 20.0) & (f <= 20000.0)].max(initial=0.0)))
            step60 = max(step60, float(change[(loss < LMAX) & (f <= 20000.0)].max(initial=0.0)))
        prev = loss
    return (*worst, step20, step60, top)


def response(params: np.ndarray, f: np.ndarray, rate: int) -> np.ndarray:
    """Complex response of sections (S, 4) = (g, R, c, m) (bilinear transform)."""
    z = np.exp(2j * np.pi * f / rate)
    s = (1.0 - 1.0 / z) / (1.0 + 1.0 / z)
    out = np.ones(len(f), dtype=complex)
    for g, r, c, m in params:
        x = s / g
        out *= (1.0 + c * x + m * x * x) / (1.0 + 2.0 * r * x + x * x)
    return out


def tiers(ratio: float) -> np.ndarray:
    """Far field (bands ``ratio`` apart, 48 kHz) against the full chain (96 kHz) and both against ISO:
    largest |difference| where the loss is below 20 dB, 100 Hz - 6.5 kHz, over 25 m - 3 km."""
    far, full = filters.AirAbsorption(20, 50, RATE), filters.AirAbsorption(20, 50, RATE_E)
    f = np.geomspace(100.0, 6500.0, 80)
    alpha = filters.iso9613_alpha(f)
    first = farfield.BAND_FIRST_M
    bands = first * ratio ** np.arange(int(math.log(12800.0 / first) / math.log(ratio)) + 2)
    out = np.zeros(3)
    for d in np.geomspace(first, 3000.0, 300):
        sel = alpha * d < 20.0
        if not sel.any():
            continue
        k = min(int(math.floor(math.log(d / first) / math.log(ratio))), len(bands) - 2)
        w = math.log(d / bands[k]) / math.log(ratio)
        mix = ((1 - w) * response(far.params(bands[k:k + 1])[0], f, RATE)
               + w * response(far.params(bands[k + 1:k + 2])[0], f, RATE))
        exact = response(full.params(np.array([d]))[0], f, RATE_E)
        lm, le, iso = -20 * np.log10(np.abs(mix)), -20 * np.log10(np.abs(exact)), alpha * d
        out = np.maximum(out, [np.abs(lm - le)[sel].max(), np.abs(lm - iso)[sel].max(), np.abs(le - iso)[sel].max()])
    return out


@numba.njit(cache=True, nogil=True)
def onepole_track(x, a, rate, times, gains, state, out):
    """The earlier engine's emission-side kernel: TPT one-poles, gains interpolated per sample."""
    n, n_poles = times.shape[0], gains.shape[1]
    j = 0
    for i in range(x.shape[0]):
        tt = (a + i) / rate
        if tt <= times[0]:
            j, f = 0, 0.0
        elif tt >= times[n - 1]:
            j, f = n - 2, 1.0
        else:
            if times[j] > tt:
                j = 0
            while times[j + 1] < tt:
                j += 1
            w = times[j + 1] - times[j]
            f = 0.0 if w <= 0 else (tt - times[j]) / w
        v = x[i]
        for p in range(n_poles):
            g = gains[j, p] + (gains[j + 1, p] - gains[j, p]) * f
            u = g * (v - state[p])
            y = u + state[p]
            state[p] = y + u
            v = y
        out[i] = v
    return out


def _timed(fn) -> float:
    t0 = time.perf_counter()
    fn()
    return time.perf_counter() - t0


def stage_cost() -> tuple[float, float, float]:
    """ns per emission sample: four one-poles (earlier) and two sections, a source moving from 10 m
    to 2 km over 60 s (control points every 1 ms); and how far the per-sample interpolated
    coefficient h strays from 1 / (1 + g k) of the interpolated g and k (relative, largest)."""
    n = 60 * RATE_E
    times = np.arange(0.0, 60.0005, 0.001)
    d = np.geomspace(10.0, 2000.0, len(times))
    x = np.random.default_rng(1).standard_normal(n)
    coef = np.ascontiguousarray(kernels.svf_coefficients(filters.AirAbsorption(20, 50, RATE_E).params(d)))
    u = np.linspace(0.0, 1.0, 97)[None, :, None]  # within each control interval, at the emission rate
    g = coef[:-1, None, :, 0] + (coef[1:, None, :, 0] - coef[:-1, None, :, 0]) * u
    k = coef[:-1, None, :, 1] + (coef[1:, None, :, 1] - coef[:-1, None, :, 1]) * u
    h = coef[:-1, None, :, 2] + (coef[1:, None, :, 2] - coef[:-1, None, :, 2]) * u
    stray = float(np.abs(h * (1.0 + g * k) - 1.0).max())
    gains = np.ascontiguousarray(np.tile(np.linspace(0.9, 0.2, len(times))[:, None], (1, 4)))
    out = []
    for run in (lambda: onepole_track(x, 0, RATE_E, times, gains, np.zeros(4), np.empty(n)),
                lambda: kernels.svf_cascade_track(x, 0, RATE_E, times, coef, np.zeros((2, 2)), np.empty(n))):
        run()  # compile
        out.append(min(_timed(run) for _ in range(3)) / n * 1e9)
    return (*out, stray)


def render_cost() -> tuple[float, float]:
    """Full-chain render time (s) with air absorption on and off: 48 sources moving at up to 30 m/s
    within 300 m, 20 s, one worker (best of two)."""
    noise = sample("e05_noise.wav", np.random.default_rng(1).standard_normal(3 * RATE) * 0.1)
    rng = np.random.default_rng(2)
    frames = 601
    t = np.arange(frames + 1)[:, None, None] / 30.0
    pos = rng.uniform(-300, 300, (1, 48, 3)) + rng.uniform(-30, 30, (1, 48, 3)) * t
    out = []
    for air in (1.0, 0.0):
        sc = scene([{"sample": noise, "id": f"s{i}"} for i in range(48)], pos, frame_end=frames,
                   settings={"air_absorption": air, "cull_db": None, "detail_voices": None})
        render.render(sc, workers=1)  # warm up (kernels, the fit)
        out.append(min(_timed(lambda: render.render(sc, workers=1)) for _ in range(2)))
    return tuple(out)


def doppler() -> list[list]:
    """Far field minus full chain (dB) at 1, 3.2 and 6.4 kHz for a source at 80 m/s towards and away
    from the listener and a standing one, 3 s of noise (welch), and what the Doppler factor r of the
    playback rate predicts if the full chain's loss is that of the emitted frequency f / r."""
    from scipy.signal import welch

    from soundstage.engine import farfield as ff

    noise = sample("e05_doppler.wav", np.random.default_rng(1).standard_normal(4 * RATE) * 0.1)
    f = np.array([1000.0, 3200.0, 6400.0])
    rows = []
    for v, d0 in ((80.0, 700.0), (-80.0, 300.0), (0.0, 450.0)):
        t = np.arange(151)[:, None, None] / 30.0
        pos = np.array([[[0.0, d0, 0.0]]]) - np.array([[[0.0, v, 0.0]]]) * t
        sc = scene([{"sample": noise}], pos, frame_end=150,
                   settings={"panner": "amplitude", "cull_db": None, "detail_voices": None})
        full = render.render(sc).audio[RATE: 4 * RATE, 0]
        assign = ff.assign_tiers
        ff.assign_tiers = lambda e, g, sp, spans, n, d: np.zeros((len(e), n), dtype=bool)  # every source far
        try:
            sc.settings["detail_voices"] = 1
            far = render.render(sc).audio[RATE: 4 * RATE, 0]
        finally:
            ff.assign_tiers = assign
        fr, pa = welch(full, RATE, nperseg=4096)
        _, pb = welch(far, RATE, nperseg=4096)
        k = [int(np.argmin(np.abs(fr - x))) for x in f]
        r = 1.0 / (1.0 - v / 343.0)
        d = d0 - v * 2.5  # distance at the middle of the measured 3 s
        predicted = -filters.iso9613_alpha(f) * d * (1.0 - 1.0 / r ** 2)
        rows.append([f"{v:+.0f} m/s, {d0:.0f} m", *(f"{x:+.1f}" for x in 10 * np.log10(pb[k] / pa[k])),
                     *(f"{x:+.1f}" for x in predicted)])
    return rows


def main() -> None:
    if "--doppler" in sys.argv:
        print_doppler()
        return
    octave = np.array([63, 125, 250, 500, 1000, 2000, 4000, 8000])
    centres = 1000 * 10 ** (np.arange(-12, 10, 3) / 10)  # exact band centres
    for freqs, label in ((octave, "nominal band frequencies"), (centres, "exact band centres")):
        rows = []
        for (tc, rh), ref in TABLE_2.items():
            got = filters.iso9613_alpha(freqs, tc, rh) * 1000
            rows.append([f"{tc} °C, {rh} %"] + [f"{g:.1f} ({r:g})" for g, r in zip(got, ref)])
        print(f"1. ISO 9613-1 formula at the {label}, dB/km (ISO 9613-2 Table 2 in brackets):\n")
        print(table(["climate"] + [f"{f} Hz" for f in octave], rows) + "\n")

    spec = np.full(3, -np.inf)
    for d in COMPARE_M:
        fc = np.clip(8000 * np.sqrt(3 / (0.1 * d)), 300, 20000)
        spec = np.maximum(spec, errors(onepole_loss(np.log([math.tan(math.pi * fc / RATE_E)]), T), ALPHA * d))
    rows = [["spec one-pole", 1, *(f"{v:.1f}" for v in spec)]]
    for kind, n, region, name in (("one-poles", 4, 20.0, "one-poles fitted below 20 dB (earlier engine)"),
                                  ("one-poles", 4, LMAX, "one-poles"), ("one-poles", 8, LMAX, "one-poles"),
                                  ("one-poles", 12, LMAX, "one-poles"),
                                  ("sections", 2, LMAX, "sections"), ("sections", 3, LMAX, "sections"),
                                  ("sections", 6, LMAX, "sections"),
                                  ("sections with zeros", 1, LMAX, "sections with zeros"),
                                  ("sections with zeros", 2, LMAX, "sections with zeros (engine)"),
                                  ("sections with zeros", 3, LMAX, "sections with zeros")):
        order = n if kind == "one-poles" else 2 * n
        rows.append([name, order, *(f"{v:.1f}" for v in compare(kind, n, region))])
    print(f"2. Largest error (dB) against ISO 9613-1 over 1 m - 20 km, 96 kHz: where the loss is below "
          f"20 dB and 20-{LMAX:.0f} dB (50 Hz - 16 kHz), and how far the filter stays short of {LMAX:.0f} dB "
          f"beyond (negative: more):\n")
    print(table(["structure", "order", "< 20 dB", f"20-{LMAX:.0f} dB", f"short of {LMAX:.0f} dB"], rows))

    rows = []
    for rate in (RATE, RATE_E):
        filters._air_table.cache_clear()
        fit_s = _timed(lambda: filters.AirAbsorption(20, 50, rate))
        low, mid, short, step20, step60, top = engine_errors(rate)
        rows.append([f"{rate // 1000} kHz", f"{low:.2f}", f"{mid:.2f}", f"{short:.1f}", f"{top:.1f}",
                     f"{step20:.2f} / {step60:.2f}", f"{fit_s:.2f}"])
    print("\n3. The engine's table (two sections with zeros) over 2000 distances 1 m - 20 km (dB):\n")
    print(table(["rate", "< 20 dB (to 16 kHz)", f"20-{LMAX:.0f} dB (to 16 kHz)", f"short of {LMAX:.0f} dB",
                 "< 20 dB, 16-20 kHz", f"largest step 0.46 % apart (< 20 / {LMAX:.0f} dB)", "fit (s)"], rows))

    rows = [[name, *(f"{v:.2f}" for v in tiers(ratio))]
            for name, ratio in (("sqrt(2) (engine)", math.sqrt(2.0)), ("octave", 2.0))]
    print("\n4. Far field (48 kHz, two bands mixed) against the full chain (96 kHz) and ISO, largest "
          "|difference| in dB where the loss is below 20 dB, 100 Hz - 6.5 kHz, 25 m - 3 km:\n")
    print(table(["band spacing", "far - full chain", "far - ISO", "full chain - ISO"], rows))

    old, new, stray = stage_cost()
    on, off = render_cost()
    print(f"\n5. Cost: the emission-side stage takes {old:.2f} ns per sample with four one-poles (earlier) "
          f"and {new:.2f} ns with two sections; the full chain (48 sources, 20 s, one worker) "
          f"{on:.2f} s with air absorption and {off:.2f} s without (+{100 * (on / off - 1):.1f} %). "
          f"Interpolating h with the other coefficients keeps h (1 + g k) within {stray:.1e} of 1.")

    print_doppler()

    air = filters.AirAbsorption(20, 50, RATE_E)
    f = np.geomspace(50, 20000, 400)
    alpha = filters.iso9613_alpha(f)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for d, color in zip((10, 100, 300, 1000, 3000), ("C0", "C1", "C2", "C3", "C4")):
        ax.semilogx(f, -alpha * d, color=color, label=f"ISO 9613-1, {d} m")
        ax.semilogx(f, -air.loss_db(f, d), "--", color=color, label=f"engine, {d} m")
    ax.axhline(-LMAX, color="0.6", lw=0.8)
    ax.set_ylim(-80, 1)
    ax.set_xlabel("Hz")
    ax.set_ylabel("dB")
    ax.set_title("air absorption, 20 °C, 50 % RH: two sections with zeros, 96 kHz")
    ax.grid(alpha=0.3, which="both")
    ax.legend(fontsize=7, ncol=2)
    save(fig, "e05_air_absorption.png")


def print_doppler() -> None:
    print("\n6. Doppler: far field minus full chain (dB), and what the full chain's loss at the emitted frequency "
          "f / r predicts (r: the Doppler factor):\n")
    print(table(["source", "1 kHz", "3.2 kHz", "6.4 kHz", "predicted 1 kHz", "3.2 kHz", "6.4 kHz"], doppler()))


if __name__ == "__main__":
    main()
