"""Debug plot (``<mix>.plot.png``, FR-65): per-source tracks over a frame axis.

Rows: propagation distance, level (distance, cone, rear and occlusion gains with the pan law's
power), pan (lateral sine, -1 left .. +1 right), propagation delay, playback rate (Doppler), and
occlusion visibility when baked. Up to ``MAX_SOURCES`` of the loudest spatial sources are drawn, so
an agent can check a render by looking at it (NFR-6). Needs matplotlib (extra ``plot``).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

MAX_SOURCES = 12
ROWS = [("distance_m", "distance (m)"), ("level_db", "level (dB)"), ("pan", "pan (−1 L … +1 R)"),
        ("delay_ms", "delay (ms)"), ("rate", "playback rate"), ("visibility", "visibility")]


def write_plot(path: str | Path, scene, result) -> Path:
    sources = [s for s in result.sources if s.get("_track") is not None]
    sources.sort(key=lambda s: -(s["peak_dbfs"] if s["peak_dbfs"] is not None else -999))
    sources = sources[:MAX_SOURCES]
    rows = [r for r in ROWS if any(r[0] in s["_track"] for s in sources)]
    fig, axes = plt.subplots(len(rows), 1, figsize=(12, 2.0 * len(rows) + 1), sharex=True, constrained_layout=True)
    axes = [axes] if len(rows) == 1 else axes
    for ax, (key, label) in zip(axes, rows):
        for s in sources:
            tr = s["_track"]
            if key in tr:
                ax.plot(tr["frame"], tr[key], lw=1.1, label=s["id"])
        ax.set_ylabel(label)
        ax.grid(alpha=0.3)
        if key == "visibility":
            ax.set_ylim(-0.05, 1.05)
    axes[0].set_title(f"{Path(scene.path).parent.name}: frames {result.frames[0]}–{result.frames[1]} @ "
                      f"{scene.fps:g} fps, {len(sources)} of {len(result.sources)} sources (loudest)")
    axes[-1].set_xlabel("frame")
    axes[0].legend(fontsize=7, ncol=4, loc="upper right")
    path = Path(path)
    fig.savefig(path, dpi=80)
    plt.close(fig)
    return path
