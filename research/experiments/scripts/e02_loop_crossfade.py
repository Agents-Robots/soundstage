"""E02: level at a loop seam for equal-power, linear and correlation-adaptive crossfades.

Builds one loop cycle with each law for a tone with whole cycles (head and tail fully correlated),
white noise (uncorrelated) and a constant, tiles it, and measures the RMS in 400-sample windows
around the seam relative to the material's RMS. Writes research/figures/e02_loop_crossfade.png.
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from soundstage.engine import signals  # noqa: E402

from common import RATE, save, table  # noqa: E402

FADE = int(0.05 * RATE)


def cycle(x: np.ndarray, law: str) -> np.ndarray:
    if law == "adaptive":
        return signals.loop_cycle(x, FADE)
    n, c = len(x), FADE
    u = (np.arange(c) + 0.5) / c
    fin, fout = (np.sin(0.5 * np.pi * u), np.cos(0.5 * np.pi * u)) if law == "equal power" else (u, 1 - u)
    out = x[: n - c].copy()
    out[:c] = x[:c] * fin + x[n - c:] * fout
    return out


def seam_levels(x: np.ndarray, law: str) -> np.ndarray:
    cyc = cycle(x, law)
    tiled = np.tile(cyc, 3)
    seam = len(cyc)  # first seam: end of cycle 1 = the crossfaded head of cycle 2
    w = tiled[seam - 2000: seam + FADE + 2000]
    w = w[: len(w) // 400 * 400].reshape(-1, 400)
    return 20 * np.log10(np.sqrt((w ** 2).mean(axis=1)) / np.sqrt((x ** 2).mean()))


def main() -> None:
    rng = np.random.default_rng(2)
    materials = {
        "tone (correlated)": np.sin(2 * np.pi * np.arange(RATE) / 48),
        "noise (uncorrelated)": rng.standard_normal(RATE),
        "constant": np.full(RATE, 0.5),
    }
    laws = ["equal power", "linear", "adaptive"]
    rows = []
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.2), sharey=True)
    for ax, (name, x) in zip(axes, materials.items()):
        row = [name]
        for law in laws:
            lv = seam_levels(x, law)
            row.append(f"{lv.min():+.2f} / {lv.max():+.2f}")
            ax.plot(np.arange(len(lv)) * 400 / RATE * 1000, lv, label=law)
        rows.append(row)
        ax.set_title(name)
        ax.set_xlabel("ms around the seam")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("level re. material (dB)")
    axes[0].legend()
    print("Seam level, min / max of 400-sample windows (dB re. the material's RMS):\n")
    print(table(["material"] + laws, rows))
    save(fig, "e02_loop_crossfade.png")


if __name__ == "__main__":
    main()
