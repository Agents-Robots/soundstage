"""Render the showcase mix: one render per pass, placed on the timeline (runs in the repo venv).

A scene setting applies to a whole render, so every pass is rendered on its own: its frames only
(``--frames``), its sound entries only (``--solo <chapter>.<pass>.*``) and its settings from the
storyboard (``--set``). The renders are placed at their frames in one stereo mix. Each pass also
gets its own WAV, report and debug plot in ``<out>/passes/`` (and its reverb return, when it has a
reverb) for checking and A/B listening.

    .venv/bin/soundstage bake out/showcase/showcase.blend --out out/showcase/bake
    .venv/bin/python examples/showcase/audio.py [--scene out/showcase/bake/scene.json] [--out out/showcase]

Writes ``<out>/showcase.wav`` and ``<out>/showcase.report.json`` (with the first frame and fps
that ``soundstage preview`` reads).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import storyboard as sb  # noqa: E402

from soundstage.engine import mix, plot, render, report  # noqa: E402
from soundstage.engine.scene import load_scene  # noqa: E402

EDGE_S = 0.010
"""Fade at both ends of a pass render; the passes start and end in silence, this only guards the seam."""
TAIL_DBFS = -60.0
"""A pass whose last 50 ms are louder than this cuts off a tail: lengthen it in the storyboard."""


def render_pass(scene_json: Path, chapter: sb.Chapter, p: sb.Pass, window: sb.Window, out: Path, scenes: dict) -> dict:
    overrides = {"master_gain_db": sb.MASTER_GAIN_DB, **p.settings}
    cache_key = json.dumps(overrides, sort_keys=True)
    if cache_key not in scenes:
        scenes[cache_key] = load_scene(scene_json, overrides)
    scene = scenes[cache_key]
    result = render.render(scene, frames=(window.first, window.last), solo=[sb.solo(chapter.key, p.key)], stems=True)
    name = f"{chapter.key}.{p.key}"
    wav = out / "passes" / f"{name}.wav"
    result.warnings = [w for w in result.warnings if w not in scene.warnings]  # the bake's: printed once
    rep = report.build_report(scene, result, wav, overrides)
    tail = float(np.abs(result.audio[-int(0.05 * result.rate):]).max(initial=0.0))
    if tail > 10 ** (TAIL_DBFS / 20):
        rep["warnings"].append(f"the pass ends at {20 * np.log10(tail):.1f} dBFS: a tail is cut off")
    mix.write_wav(wav, result.audio, result.rate)
    if result.reverb:  # the return alone, for checking the reverb against the direct sound
        mix.write_wav(mix.stem_path(wav, "reverb"), result.stems["reverb"], result.rate)
    report.write_report(wav.with_suffix(".report.json"), rep)
    plot.write_plot(wav.with_suffix(".plot.png"), scene, result)
    return {"pass": name, "frames": [window.first, window.last], "settings": p.settings,
            "offset": scene.sample_of(window.first) - scene.sample_of(sb.FRAME_START),
            "audio": result.audio, "rate": result.rate, "master": rep["master"], "warnings": rep["warnings"]}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--scene", default="out/showcase/bake/scene.json")
    p.add_argument("--out", default="out/showcase")
    p.add_argument("--only", nargs="*", default=(), help="chapter keys to render (default: all)")
    a = p.parse_args()
    scene_json, out = Path(a.scene), Path(a.out)
    (out / "passes").mkdir(parents=True, exist_ok=True)
    scenes: dict = {}
    timeline = sb.timeline()
    rows = []
    for key, timed in timeline.items():
        if a.only and key not in a.only:
            continue
        for ps in timed.chapter.passes:
            row = render_pass(scene_json, timed.chapter, ps, timed.passes[ps.key], out, scenes)
            m = row["master"]
            print(f"{row['pass']:22s} frames {row['frames'][0]:5d}-{row['frames'][1]:5d}  peak {m['peak_dbfs']:>7} dBFS  "
                  f"true peak {m['true_peak_dbtp']:>7} dBTP  {m['lufs_integrated']} LUFS", flush=True)
            for w in row["warnings"]:
                print(f"  warning: {w}")
            rows.append(row)
    for w in next(iter(scenes.values())).warnings:
        print(f"bake warning: {w}")
    rate = rows[0]["rate"]
    length = next(iter(scenes.values())).length_samples()
    master = np.zeros((length, 2))
    edge = int(EDGE_S * rate)
    ramp = np.sin(0.5 * np.pi * np.arange(edge) / edge)[:, None] ** 2
    for row in rows:
        x = row.pop("audio").copy()
        x[:edge] *= ramp
        x[-edge:] *= ramp[::-1]
        master[row["offset"]:row["offset"] + len(x)] += x
    wav = out / "showcase.wav"
    mix.write_wav(wav, master, rate)
    summary = {"output": str(wav.resolve()), "sample_rate": rate, "frames": [sb.FRAME_START, sb.frame_end()],
               "fps": float(sb.FPS), "master_gain_db": sb.MASTER_GAIN_DB, "master": report.metrics(master, rate),
               "passes": [{k: v for k, v in r.items() if k not in ("rate", "offset")} for r in rows]}
    report.write_report(wav.with_suffix(".report.json"), summary)
    m = summary["master"]
    print(f"wrote {wav}: {length / rate:.1f} s, peak {m['peak_dbfs']} dBFS, true peak {m['true_peak_dbtp']} dBTP, "
          f"{m['lufs_integrated']} LUFS")


if __name__ == "__main__":
    main()
