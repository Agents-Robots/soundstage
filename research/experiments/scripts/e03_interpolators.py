"""E03: fractional-delay read error per interpolator and frequency.

Reads a sine at fractional positions with a slowly varying rate (0.95-1.05) and compares with the
exact sine at those times. Interpolators: 4-point Hermite on 1x and 2x input, the optimal-2x
6-point polynomial on 2x input with and without the 63-tap pre-emphasis, and the Kaiser sinc on 1x
input. Prints error in dB re. the signal and writes research/figures/e03_interpolators.png.
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from soundstage.engine import kernels as k  # noqa: E402

from common import RATE, save, table  # noqa: E402


def error_db(read, f: float, oversample: int, prefilter=None) -> float:
    fe = RATE * oversample
    buf = np.sin(2 * np.pi * f * np.arange(int(0.2 * fe)) / fe)
    if prefilter is not None:
        buf = np.convolve(buf, prefilter, mode="same")
    n = np.arange(int(0.1 * RATE))
    t_out = 0.05 + n / RATE * (1 + 0.05 * np.sin(n / 300))
    y = read(buf, t_out * fe, t_out)
    err = y - np.sin(2 * np.pi * f * t_out)
    return float(20 * np.log10(np.sqrt(np.mean(err ** 2)) / np.sqrt(0.5)))


def main() -> None:
    table_sinc = k.sinc_table()
    pre = k.optimal2x_preemphasis()
    readers = {
        "hermite4 @1x": (lambda b, p, t: k.read_hermite4(b, p, np.empty(len(p))), 1, None),
        "hermite4 @2x": (lambda b, p, t: k.read_hermite4(b, p, np.empty(len(p))), 2, None),
        "optimal2x @2x, no pre-emphasis": (lambda b, p, t: k.read_optimal2x(b, p, np.empty(len(p))), 2, None),
        "optimal2x @2x + pre-emphasis (standard)": (lambda b, p, t: k.read_optimal2x(b, p, np.empty(len(p))), 2, pre),
        "sinc @1x (high)": (lambda b, p, t: k.read_sinc(b, p, np.ones(len(p)), table_sinc, k.SINC_ZERO_CROSSINGS,
                                                        k.SINC_TABLE_PER_CROSSING, k.SINC_CUTOFF, np.empty(len(p))),
                            1, None),
    }
    freqs = [100, 1000, 5000, 10000, 15000, 18000, 20000]
    dense = np.geomspace(100, 21000, 40)
    rows = []
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for name, (read, os_, prefilter) in readers.items():
        rows.append([name] + [f"{error_db(read, f, os_, prefilter):.1f}" for f in freqs])
        ax.semilogx(dense, [error_db(read, f, os_, prefilter) for f in dense], label=name)
    print("Read error (dB re. signal) at:\n")
    print(table(["interpolator"] + [f"{f} Hz" for f in freqs], rows))
    ax.set_xlabel("frequency (Hz), output rate 48 kHz")
    ax.set_ylabel("read error (dB re. signal)")
    ax.grid(alpha=0.3, which="both")
    ax.legend(fontsize=8)
    save(fig, "e03_interpolators.png")


if __name__ == "__main__":
    main()
