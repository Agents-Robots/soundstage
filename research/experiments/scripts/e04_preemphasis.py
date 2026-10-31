"""E04: passband droop of the optimal-2x polynomial and the pre-emphasis FIR that corrects it.

Computes the interpolator's frequency response (Fourier transform of its continuous impulse
response), designs the least-squares pre-emphasis for several lengths (same method as
kernels.optimal2x_preemphasis) and measures the read error of the pre-emphasized 2x signal.
Writes research/figures/e04_preemphasis.png.
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from e03_interpolators import error_db  # noqa: E402

from soundstage.engine import kernels as k  # noqa: E402

from common import RATE, save, table  # noqa: E402


def response(f_rel: np.ndarray) -> np.ndarray:
    """Magnitude response of the optimal-2x read at frequencies in units of the 2x rate."""
    step = 1.0 / 512
    impulse = np.zeros(41)
    impulse[20] = 1.0
    t = np.arange(16.0, 24.0, step)
    h = k.read_optimal2x(impulse, t, np.empty(len(t)))
    return (h[None, :] * np.cos(2 * np.pi * np.outer(f_rel, t - 20.0))).sum(axis=1) * step


def main() -> None:
    fe = 2 * RATE
    f = np.linspace(0, 24000, 400)
    h = response(f / fe)
    droop = [[f"{x} Hz", f"{20 * np.log10(response(np.array([x / fe]))[0]):+.2f}"] for x in (1000, 5000, 10000, 15000, 20000)]
    print("Passband response of the optimal-2x read (48 kHz audio at the 2x rate):\n")
    print(table(["frequency", "gain (dB)"], droop))
    rows = []
    read = lambda b, p, t: k.read_optimal2x(b, p, np.empty(len(p)))  # noqa: E731
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4))
    a1.plot(f / 1000, 20 * np.log10(np.abs(h)), "k", label="interpolator alone")
    for taps in (15, 31, 47, 63):
        pre = k.optimal2x_preemphasis.__wrapped__(taps)
        errs = [error_db(read, x, 2, pre) for x in (1000, 10000, 15000, 18000, 20000)]
        rows.append([taps] + [f"{e:.1f}" for e in errs])
        m = (len(pre) - 1) // 2
        fir = pre[m] + 2 * sum(pre[m + j] * np.cos(2 * np.pi * f / fe * j) for j in range(1, m + 1))
        a1.plot(f / 1000, 20 * np.log10(np.abs(fir * h)), label=f"with {taps}-tap pre-emphasis")
        a2.plot([1, 10, 15, 18, 20], errs, "o-", label=f"{taps} taps")
    print("\nRead error (dB re. signal) of the pre-emphasized 2x signal:\n")
    print(table(["taps", "1 kHz", "10 kHz", "15 kHz", "18 kHz", "20 kHz"], rows))
    a1.set_ylim(-8, 2)
    a1.set_xlabel("kHz")
    a1.set_ylabel("dB")
    a1.set_title("passband response")
    a1.legend(fontsize=8)
    a1.grid(alpha=0.3)
    a2.set_xlabel("kHz")
    a2.set_ylabel("read error (dB)")
    a2.set_title("read error after pre-emphasis")
    a2.legend(fontsize=8)
    a2.grid(alpha=0.3)
    save(fig, "e04_preemphasis.png")


if __name__ == "__main__":
    main()
