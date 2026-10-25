"""E06: responses of the ear-model parts as implemented.

- Head shadow: magnitude of the discrete Brown-Duda shelf per angle from the ear axis, at full
  strength and at the default 0.5, against the analog response.
- Rear cue: response of the rho-weighted one-pole shelf for rho = 0 ... 1.
- Pan laws: channel gains of `sine` and `power` against the lateral angle.
- ITD: Woodworth delay against the lateral angle at itd_scale 1 and 0.5.
Writes research/figures/e06_ear_model.png.
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from common import RATE, save, table  # noqa: E402
from soundstage.engine import filters, panning  # noqa: E402

A, C = 0.0875, 343.0


def shelf_db(alpha: float, f: np.ndarray) -> np.ndarray:
    b0, b1, a1 = filters.head_shadow_coefficients(np.array([alpha]), A, C, RATE)
    z = np.exp(-2j * np.pi * f / RATE)
    return 20 * np.log10(np.abs((b0 + b1 * z) / (1 + a1 * z)))


def rear_db(rho: float, f: np.ndarray, cutoff: float = 6000.0) -> np.ndarray:
    g = filters.tpt_gain(np.array([cutoff]), RATE)[0] / (1 - filters.tpt_gain(np.array([cutoff]), RATE)[0])
    z = np.exp(-2j * np.pi * f / RATE)
    lp = g * (1 + z) / ((1 + g) + (g - 1) * z)  # bilinear one-pole low-pass
    return 20 * np.log10(np.abs(1 + rho * (lp - 1)))


def main() -> None:
    f = np.geomspace(50, 20000, 300)
    wp = 2 * C / A
    rows = []
    fig, ax = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    for theta in (0, 45, 90, 135, 150, 180):
        alpha = filters.head_shadow_alpha(np.cos(np.radians([theta])), 1.0)[0]
        half = filters.head_shadow_alpha(np.cos(np.radians([theta])), 0.5)[0]
        analog = 20 * np.log10(np.abs((1 + 1j * alpha * 2 * np.pi * f / wp) / (1 + 1j * 2 * np.pi * f / wp)))
        ax[0, 0].semilogx(f, shelf_db(alpha, f), label=f"{theta}°")
        ax[0, 0].semilogx(f, analog, "k:", lw=0.6)
        rows.append([f"{theta}°", f"{alpha:.3f}", f"{20 * np.log10(alpha):+.1f}", f"{shelf_db(alpha, np.array([10000.0]))[0]:+.1f}",
                     f"{half:.3f}", f"{shelf_db(half, np.array([10000.0]))[0]:+.1f}"])
    print("Head shadow (Brown-Duda), theta from the ear's axis:\n")
    print(table(["theta", "alpha (full)", "HF limit dB", "10 kHz dB (full)", "alpha (0.5)", "10 kHz dB (0.5)"], rows))
    ax[0, 0].set_title("head shadow, full strength (dotted: analog)")
    ax[0, 0].set_xlabel("Hz")
    ax[0, 0].set_ylabel("dB")
    ax[0, 0].legend(fontsize=8, title="angle from ear axis")
    ax[0, 0].grid(alpha=0.3, which="both")

    rows = []
    for rho in (0, 0.25, 0.5, 0.75, 1.0):
        r = rear_db(rho, f)
        ax[0, 1].semilogx(f, r, label=f"ρ = {rho}")
        rows.append([rho] + [f"{rear_db(rho, np.array([x]))[0]:+.2f}" for x in (1000, 6000, 12000, 18000)])
    print("\nRear cue shelf (before the rear gain), rear_cutoff_hz = 6000:\n")
    print(table(["rho", "1 kHz", "6 kHz", "12 kHz", "18 kHz"], rows))
    ax[0, 1].set_title("rear cue: x + ρ (LP(x) − x), LP at 6 kHz")
    ax[0, 1].set_xlabel("Hz")
    ax[0, 1].legend(fontsize=8)
    ax[0, 1].grid(alpha=0.3, which="both")

    theta = np.linspace(-90, 90, 181)
    lam = np.sin(np.radians(theta))
    rows = []
    for name, law in panning.PAN_LAWS.items():
        gl, gr = law(lam)
        ax[1, 0].plot(theta, 20 * np.log10(np.maximum(gl, 1e-6)), label=f"{name}: left")
        ax[1, 0].plot(theta, 20 * np.log10(np.maximum(gr, 1e-6)), "--", label=f"{name}: right")
        for t in (30, 60, 76, 90):
            l, r = law(np.array([np.sin(np.radians(t))]))
            rows.append([name, f"{t}°", f"{20 * np.log10(max(r[0], 1e-9) / max(l[0], 1e-9)):.1f}"])
    print("\nPan laws, channel balance R/L (dB) for a source on the right:\n")
    print(table(["law", "angle", "balance dB"], rows))
    ax[1, 0].set_ylim(-40, 1)
    ax[1, 0].set_title("pan laws (λ = sin θ)")
    ax[1, 0].set_xlabel("lateral angle θ (°), + right")
    ax[1, 0].set_ylabel("gain dB")
    ax[1, 0].legend(fontsize=8)
    ax[1, 0].grid(alpha=0.3)

    for scale in (1.0, 0.5):
        ax[1, 1].plot(theta, panning.woodworth_itd(lam, A, C, scale) * 1000, label=f"itd_scale {scale}")
    print(f"\nITD at 90°: {panning.woodworth_itd(np.array([1.0]), A, C, 1.0)[0] * 1000:.3f} ms (itd_scale 1)")
    ax[1, 1].set_title("Woodworth ITD")
    ax[1, 1].set_xlabel("lateral angle θ (°)")
    ax[1, 1].set_ylabel("ms (right ear leads for +)")
    ax[1, 1].legend(fontsize=8)
    ax[1, 1].grid(alpha=0.3)
    save(fig, "e06_ear_model.png")


if __name__ == "__main__":
    main()
