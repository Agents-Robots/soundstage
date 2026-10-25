"""E05: ISO 9613-1 implementation and the choice of air-absorption filter.

1. The ISO 9613-1 formula against ISO 9613-2 Table 2 (octave bands, six climates).
2. Filter realizations against the ISO loss (20 C, 50 % RH, 100 Hz-20 kHz, where the loss is below
   20 dB): the original spec's one-pole at the 3 dB point of an f^2 law, and 1-4 cascaded one-poles
   fitted per distance (least squares on the loss in dB) at the 96 kHz emission rate.
3. Smoothness of the fitted table: largest response change between neighbouring distances.
Writes research/figures/e05_air_absorption.png.
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy.optimize import least_squares  # noqa: E402

from common import save, table  # noqa: E402
from soundstage.engine import filters  # noqa: E402

TABLE_2 = {
    (10, 70): [0.1, 0.4, 1.0, 1.9, 3.7, 9.7, 32.8, 117],
    (20, 70): [0.1, 0.3, 1.1, 2.8, 5.0, 9.0, 22.9, 76.6],
    (30, 70): [0.1, 0.3, 1.0, 3.1, 7.4, 12.7, 23.1, 59.3],
    (15, 20): [0.3, 0.6, 1.2, 2.7, 8.2, 28.2, 88.8, 202],
    (15, 50): [0.1, 0.5, 1.2, 2.2, 4.2, 10.8, 36.2, 129],
    (15, 80): [0.1, 0.3, 1.1, 2.4, 4.1, 8.3, 23.7, 82.8],
}
RATE_E = 96000


def fit(f, target, n):
    def res(x):
        return filters._onepole_loss_db(f, np.exp(x), RATE_E) - target
    x0 = np.log(np.full(n, 8000.0)) + np.linspace(0, 1, n)
    return least_squares(res, x0, bounds=(np.log(20.0), np.log(0.49 * RATE_E))).fun


def main() -> None:
    octave = np.array([63, 125, 250, 500, 1000, 2000, 4000, 8000])
    centres = 1000 * 10 ** (np.arange(-12, 10, 3) / 10)  # exact band centres
    for freqs, label in ((octave, "nominal band frequencies"), (centres, "exact band centres")):
        rows = []
        for (tc, rh), ref in TABLE_2.items():
            got = filters.iso9613_alpha(freqs, tc, rh) * 1000
            rows.append([f"{tc} °C, {rh} %"] + [f"{g:.1f} ({r:g})" for g, r in zip(got, ref)])
        print(f"1. ISO 9613-1 formula at the {label}, dB/km (ISO 9613-2 Table 2 in brackets):\n")
        print(table(["climate"] + [f"{f} Hz" for f in octave], rows) + "\n")

    f = np.geomspace(100, 20000, 300)
    alpha = filters.iso9613_alpha(f)
    rows = []
    for d in (10, 30, 100, 300, 1000, 3000):
        target = alpha * d
        m = target < 20
        fc_spec = np.clip(8000 * np.sqrt(3 / (0.1 * d)), 300, 20000)
        spec = np.abs(filters._onepole_loss_db(f[m], np.array([fc_spec]), RATE_E) - target[m]).max()
        row = [d, f"{spec:.1f}"] + [f"{np.abs(fit(f[m], target[m], n)).max():.2f}" for n in (1, 2, 3, 4)]
        air = filters.AirAbsorption(20, 50, RATE_E).cutoffs(np.array([float(d)]))[0]
        used = filters._onepole_loss_db(f, air[np.isfinite(air)], RATE_E) if np.isfinite(air).any() else 0 * f
        row.append(f"{np.abs(used[m] - target[m]).max():.2f}")
        row.append(f"{used[~m].min():.1f}" if (~m).any() else "-")
        rows.append(row)
    print("\n2. Largest error (dB) against ISO 9613-1 where the loss is below 20 dB:\n")
    print(table(["distance (m)", "spec one-pole", "fit 1", "fit 2", "fit 3", "fit 4", "engine table (4)",
                 "engine: min loss above"], rows))

    air = filters.AirAbsorption(20, 50, RATE_E)
    ds = np.geomspace(2, 20000, 2000)
    prev, worst = None, (0.0, 0.0, 0.0)
    for d, fc in zip(ds, air.cutoffs(ds)):
        got = filters._onepole_loss_db(f, fc[np.isfinite(fc)], RATE_E) if np.isfinite(fc).any() else 0 * f
        if prev is not None:
            m = alpha * d < 20
            step = np.abs(got - prev)[m]
            if step.max() > worst[0]:
                worst = (float(step.max()), float(d), float(f[m][np.argmax(step)]))
        prev = got
    print(f"\n3. Largest response change between neighbouring distances (0.46 % apart), where the loss is "
          f"below 20 dB: {worst[0]:.2f} dB at {worst[1]:.0f} m, {worst[2]:.0f} Hz")

    fig, ax = plt.subplots(figsize=(8, 4.5))
    for d, color in zip((10, 100, 300, 1000), ("C0", "C1", "C2", "C3")):
        fc = air.cutoffs(np.array([float(d)]))[0]
        ax.semilogx(f, -alpha * d, color=color, label=f"ISO 9613-1, {d} m")
        ax.semilogx(f, -filters._onepole_loss_db(f, fc[np.isfinite(fc)], RATE_E), "--", color=color,
                    label=f"4-pole fit, {d} m")
    ax.set_ylim(-40, 1)
    ax.set_xlabel("Hz")
    ax.set_ylabel("dB")
    ax.set_title("air absorption, 20 °C, 50 % RH")
    ax.grid(alpha=0.3, which="both")
    ax.legend(fontsize=7, ncol=2)
    save(fig, "e05_air_absorption.png")


if __name__ == "__main__":
    main()
