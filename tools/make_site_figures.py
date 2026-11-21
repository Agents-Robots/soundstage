"""Make the charts of the project page's science section in site/img/ (run in the repo venv).

Every chart is measured on audio the engine rendered for the feature video: the passes and probes
of ``out/showcase/<section>`` (built by ``examples/showcase``), with the measurement functions of
the sections' own ``check.py``. Solid coloured lines are the engine, dashed light lines the
expectation from the geometry, the standard or the preset.

- ``sci-spectrogram``: frequency over time of the propeller plane's pass-by, with the harmonics
  expected from the baked geometry.
- ``sci-doppler``: the frequency of a 1 kHz tone on four vehicles against the geometry.
- ``sci-air``: the air-absorption filter per distance against ISO 9613-1.
- ``sci-occlusion``: the motorbike behind the houses with occlusion off and on.
- ``sci-reverb``: the decay of three rooms against their presets' decay times.

Usage::

    .venv/bin/python tools/make_site_figures.py [--only sci-doppler,sci-air] [--showcase DIR]
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from PIL import Image  # noqa: E402
from scipy import signal  # noqa: E402

from soundstage.engine import filters  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
IMG = REPO / "site" / "img"
SECTIONS = REPO / "examples" / "showcase" / "sections"

# the page's colours (site/style.css); series colours checked against the card surface for
# colour-vision deficiencies and contrast
SURFACE, GRID, INK, SOFT, MUTED = "#181d26", "#2b3340", "#f3f0ea", "#c5c8cc", "#8b929c"
SERIES = ("#3987e5", "#d95926", "#199e70", "#c98500")
RAMP = ("#184f95", "#256abf", "#3987e5", "#6da7ec", "#b7d3f6")
"""One hue from dark to light, for an ordered quantity (here: distance)."""
LEVEL = LinearSegmentedColormap.from_list("level", ("#0d1016", "#112a4f", "#184f95", "#3987e5", "#9cc4f3", "#f3f7fd"))
"""The same hue for the level in a spectrogram: louder is lighter."""
SIZE, DPI = (6.0, 3.75), 240

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10.5, "axes.labelsize": 10.5, "xtick.labelsize": 9.5,
    "ytick.labelsize": 9.5, "legend.fontsize": 9.5, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE, "text.color": INK, "axes.labelcolor": SOFT, "xtick.color": MUTED,
    "ytick.color": MUTED, "axes.edgecolor": GRID, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "axes.axisbelow": True, "lines.linewidth": 2.0,
    "legend.frameon": False, "legend.labelcolor": INK, "legend.handlelength": 1.6,
})


def showcase_check(key: str, showcase: Path):
    """A section's check module (its measurement functions and storyboard constants) and its
    ``Check`` on the rendered section."""
    if not (showcase / key / "section.json").exists():
        raise SystemExit(f"{showcase / key} is missing: build the showcase section first (examples/showcase/README.md)")
    sys.modules.pop("section", None)  # every section has its own section.py
    spec = importlib.util.spec_from_file_location(f"showcase_check_{key}", SECTIONS / key / "check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, mod.Check(showcase / key)


def save(fig, name: str, lossless: bool) -> None:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI)
    plt.close(fig)
    im = Image.open(buf).convert("RGB")
    out = IMG / f"{name}.webp"
    im.save(out, "WEBP", lossless=lossless, quality=88, method=6)
    print(f"{out.relative_to(REPO)}  {im.width}×{im.height}  {out.stat().st_size / 1024:.0f} kB")


def level_db(x: np.ndarray, rate: int, window: int, hop: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Spectrogram of the mono sum in dB."""
    f, t, p = signal.spectrogram(x.mean(axis=1), fs=rate, nperseg=window, noverlap=window - hop)
    return f, t, 10 * np.log10(p + 1e-20)


def colorbar(fig, mesh, axes, label: str = "level (dB below the loudest)") -> None:
    bar = fig.colorbar(mesh, ax=axes, pad=0.02, aspect=28, fraction=0.035)
    bar.outline.set_visible(False)
    bar.ax.tick_params(length=0, labelsize=8.5)
    bar.set_label(label, color=SOFT, fontsize=9)


def spectrogram(showcase: Path) -> None:
    """Frequency over time of the plane's pass-by; dashed: harmonics of the propeller's sample
    times the playback rate from the baked geometry."""
    mod, c = showcase_check("doppler", showcase)
    key, sid = "plane", "doppler.plane.engine"
    f, t, level = level_db(c.pass_audio(key), c.rate, 8192, 512)
    sel = f <= 1400
    level -= level[sel].max()
    fig, ax = plt.subplots(figsize=SIZE, layout="constrained")
    mesh = ax.pcolormesh(t, f[sel], level[sel], vmin=-70, vmax=0, cmap=LEVEL, shading="gouraud", rasterized=True)

    entry = c.geo.entry(sid)
    sample, rate = sf.read(entry["sample"], always_2d=True)
    spec = np.abs(np.fft.rfft(sample.mean(axis=1) * np.hanning(len(sample))))
    freqs = np.fft.rfftfreq(len(sample), 1 / rate)
    a, b = mod.audible_span(key)
    times = np.linspace(a, b, 200)
    heard = np.array([c.geo.rate(sid, c.frame(key, s)) for s in times])
    print(f"sci-spectrogram: playback rate {heard.max():.3f} to {heard.min():.3f}")
    for nominal in (360, 720, 1080):  # every fourth harmonic of the blade passing at 90 Hz
        near = np.abs(freqs - nominal) < 20
        emitted = freqs[near][np.argmax(spec[near])] * entry["pitch"]
        ax.plot(times, emitted * heard, color=INK, lw=1.1, dashes=(5, 4))
        print(f"  harmonic {emitted:.1f} Hz: heard {emitted * heard.max():.0f} to {emitted * heard.min():.0f} Hz")
    ax.set(xlim=(a - 0.6, b + 0.4), ylim=(0, 1400), xlabel="time (s)", ylabel="frequency (Hz)")
    ax.legend(handles=[Line2D([], [], color=INK, lw=1.1, dashes=(5, 4), label="expected from the plane's path")],
              loc="upper right")
    colorbar(fig, mesh, ax)
    save(fig, "sci-spectrogram", lossless=False)


VEHICLES = {"race": "Race car, 252 km/h", "plane": "Propeller plane, 216 km/h", "train": "From a moving train, 108 km/h",
            "siren": "Ambulance, 72 km/h"}


def doppler(showcase: Path) -> None:
    """The 1 kHz probe of four pass-bys: frequency measured in 50 ms windows against the rate from
    the baked geometry, on a time axis from the moment the tone passes 1 kHz."""
    mod, c = showcase_check("doppler", showcase)
    fig, ax = plt.subplots(figsize=SIZE, layout="constrained")
    for (key, label), colour in zip(VEHICLES.items(), SERIES):
        x = c.probe(key, "sine").audio
        a, b = mod.audible_span(key)
        t, f = mod.measure.frequency_track(x[int(a * c.rate):int(b * c.rate)], c.rate, 0.05, 0.02, 1000)
        t = t + a
        want = np.array([1000 * c.geo.rate(f"doppler.probe.{key}.sine", c.frame(key, s)) for s in t])
        passing = np.interp(-1000, -want, t)  # want falls
        ax.plot(t - passing, f, color=colour, label=label)
        ax.plot(t - passing, want, color=INK, lw=1.0, dashes=(4, 4))
        print(f"sci-doppler: {key:6s} {f[0]:7.1f} to {f[-1]:6.1f} Hz, largest difference to the geometry "
              f"{100 * np.nanmax(np.abs(f / want - 1)):.2f} % ({len(t)} windows)")
    ax.axhline(1000, color=GRID, lw=0.8, zorder=0)
    ax.set(xlim=(-3.5, 3.5), ylim=(800, 1300), xlabel="time from the moment of passing, as heard (s)",
           ylabel="frequency of a 1 kHz tone (Hz)")
    ax.grid(axis="y")
    handles, _ = ax.get_legend_handles_labels()
    handles.append(Line2D([], [], color=INK, lw=1.0, dashes=(4, 4), label="expected from the geometry"))
    ax.legend(handles=handles, loc="upper right")
    save(fig, "sci-doppler", lossless=True)


def air(showcase: Path) -> None:
    """The loss of the engine's air-absorption filter at the five camera distances of the showcase's
    ``distance`` section against ISO 9613-1 (20 °C, 50 % relative humidity). The axis ends at
    -50 dB: the filter follows the standard to about 60 dB of loss and stays near that beyond."""
    distances = (42.875, 85.75, 171.5, 343.0, 686.0)
    stage = filters.AirAbsorption(20.0, 50.0, 96000)  # the rate the filter runs at
    f = np.geomspace(250, 16000, 200)
    alpha = filters.iso9613_alpha(f)
    fig, ax = plt.subplots(figsize=SIZE, layout="constrained")
    for d, colour in zip(distances, RAMP):
        ax.plot(f, -stage.loss_db(f, d), color=colour, label=f"{d:.0f} m")
        ax.plot(f, -alpha * d, color=INK, lw=1.0, dashes=(4, 4))
        shown = alpha * d <= 50
        print(f"sci-air: {d:6.1f} m  filter within {np.max(np.abs(stage.loss_db(f, d) - alpha * d)[shown]):.2f} dB of ISO "
              f"9613-1 down to -50 dB; at 4 kHz {-alpha[np.argmin(np.abs(f - 4000))] * d:.1f} dB")
    ax.set_xscale("log")
    ticks = (250, 500, 1000, 2000, 4000, 8000, 16000)
    ax.set_xticks(ticks, [f"{v // 1000} k" if v >= 1000 else str(v) for v in ticks])
    ax.minorticks_off()
    ax.set(xlim=(250, 16000), ylim=(-50, 2), xlabel="frequency (Hz)", ylabel="loss in the air (dB)")
    ax.grid(axis="y")
    handles, _ = ax.get_legend_handles_labels()
    handles.append(Line2D([], [], color=INK, lw=1.0, dashes=(4, 4), label="ISO 9613-1"))
    ax.legend(handles=handles, loc="lower left", title="distance", title_fontsize=9.5, alignment="left")
    save(fig, "sci-air", lossless=True)


def occlusion(showcase: Path) -> None:
    """The motorbike riding behind four houses, occlusion off and on, on one level scale; the marks
    are the moments the showcase's check measures it fully hidden."""
    _, c = showcase_check("occlusion", showcase)
    passes = {"bike_off": "occlusion off", "bike": "occlusion on"}
    specs = {k: level_db(c.pass_audio(k), c.rate, 2048, 512) for k in passes}
    top = max(level[f <= 8000].max() for f, _, level in specs.values())
    hidden = sorted({float(m.group(1)) for r in c_results(c) if (m := re.search(r"behind house \d \(([\d.]+) s heard\)", r))})
    fig, axes = plt.subplots(2, 1, figsize=SIZE, layout="constrained", sharex=True)
    for ax, (k, label) in zip(axes, passes.items()):
        f, t, level = specs[k]
        sel = f <= 8000
        mesh = ax.pcolormesh(t, f[sel] / 1000, level[sel] - top, vmin=-70, vmax=0, cmap=LEVEL, shading="gouraud",
                             rasterized=True)
        ax.set(ylim=(0, 8), yticks=(0, 4, 8))
        ax.set_title(label, loc="left", color=INK, fontsize=10.5, pad=5)
    for s in hidden:
        axes[1].plot([s], [7.2], marker="v", ms=6, color=INK, ls="none")
    axes[1].text(hidden[0] + 0.18, 7.2, "behind a house", color=INK, fontsize=9, va="center")
    axes[1].set_xlabel("time (s)")
    fig.supylabel("frequency (kHz)", color=SOFT, fontsize=10.5)
    colorbar(fig, mesh, axes)
    print(f"sci-occlusion: fully hidden at {', '.join(f'{s:g} s' for s in hidden)}")
    save(fig, "sci-occlusion", lossless=False)


def c_results(c) -> list[str]:
    """Names of the checks the section's last check run recorded (``check.json``)."""
    return [r["name"] for r in json.loads((c.dir / "check.json").read_text())]


ROOM_NAMES = {"livingroom": "Living room", "gym": "Gymnasium", "church": "Chapel"}


def reverb(showcase: Path) -> None:
    """Energy decay (Schroeder integral, 500 Hz to 2 kHz) of the reverb stem after the last click in
    three rooms; dashed: the slope of the preset's decay time, from the curve's -5 dB point."""
    mod, c = showcase_check("reverb", showcase)
    fig, ax = plt.subplots(figsize=SIZE, layout="constrained")
    for (key, name), colour in zip(ROOM_NAMES.items(), SERIES):
        stem = c.probe(key, stems=True).stems["reverb"]
        start = (c.geo.arrival(f"reverb.probe.{key}.click_clap", c.frame(key, mod.CLAPS_S[-1])) - c.windows[key][0]) / 30
        x = mod.band(stem, c.rate)[c.t(key, start):]
        energy = np.cumsum((x ** 2)[::-1])[::-1]
        decay = 10 * np.log10(energy / energy[0] + 1e-30)
        t = np.arange(len(x)) / c.rate
        keep = decay >= -62
        nominal = mod.DECAY_S[key]
        ax.plot(t[keep], decay[keep], color=colour, label=f"{name}: {mod.t30(x, c.rate):.2f} s measured, {nominal:.2f} s set")
        t5 = t[np.argmax(decay <= -5)]
        ax.plot([t5, t5 + 55 / 60 * nominal], [-5, -60], color=INK, lw=1.0, dashes=(4, 4))
        print(f"sci-reverb: {key:10s} T30 {mod.t30(x, c.rate):.2f} s, preset {nominal:.2f} s")
    ax.set(xlim=(0, 5), ylim=(-60, 0), xlabel="time after the click (s)", ylabel="energy still to come (dB)")
    ax.grid(axis="y")
    handles, _ = ax.get_legend_handles_labels()
    handles.append(Line2D([], [], color=INK, lw=1.0, dashes=(4, 4), label="the preset's decay time"))
    ax.legend(handles=handles, loc="upper right")
    save(fig, "sci-reverb", lossless=True)


FIGURES = {"sci-spectrogram": spectrogram, "sci-doppler": doppler, "sci-air": air, "sci-occlusion": occlusion,
           "sci-reverb": reverb}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--only", default="", help=f"comma-separated charts (default: all): {', '.join(FIGURES)}")
    p.add_argument("--showcase", type=Path, default=REPO / "out" / "showcase", help="the rendered showcase sections")
    a = p.parse_args()
    only = a.only.split(",") if a.only else list(FIGURES)
    if unknown := set(only) - set(FIGURES):
        p.error(f"unknown chart: {', '.join(sorted(unknown))}")
    IMG.mkdir(parents=True, exist_ok=True)
    for name in only:
        FIGURES[name](a.showcase)


if __name__ == "__main__":
    main()
