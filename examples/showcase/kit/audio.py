"""Render a section's sound: one render per pass, placed at its frames (repo venv).

A scene setting applies to a whole render, so each pass is rendered alone: its frames, its sound
entries (``--solo <key>.<pass>.*``), its settings from the manifest, the section's gain
(sections/README.md, "Sound"). The title page is silent by construction. No normalization and no
limiter (S1). Writes, under the section's output folder:

- ``passes/<key>.<pass>.wav`` with its stems, report and debug plot;
- ``<key>.wav``: the whole section, frames 1 to the last, 1600 samples per frame;
- ``<key>.report.json``: per pass and for the section: peak, true peak, loudness, warnings, render
  time and the process's peak memory.
"""

from __future__ import annotations

import json
import resource
import time
from pathlib import Path

import numpy as np

from soundstage.engine import mix, plot, render, report
from soundstage.engine.scene import Scene, load_scene

from . import story

TAIL_DBFS = -60.0
TAIL_S = (0.055, 0.005)
"""Where a pass's tail is measured: from 55 to 5 ms before its end. The last 5 ms are half of the
engine's 10 ms crossfade into the next shot when a camera cut follows the pass: the sound of this
pass's sources at the next camera, not a tail that this pass cuts off."""
EDGE_S = 0.2


def manifest(section_dir: Path) -> dict:
    return json.loads((section_dir / "section.json").read_text())


class Scenes:
    """Scene files loaded once per set of overrides."""

    def __init__(self, section_dir: Path, man: dict):
        self.dir, self.man, self.cache = section_dir, man, {}

    def get(self, p: dict, extra: dict | None = None) -> Scene:
        overrides = {"master_gain_db": self.man["gain_db"], **p.get("settings", {}), **(extra or {})}
        bake = self.dir / (f"bake_{p['bake']}" if p.get("bake") else "bake") / "scene.json"
        k = json.dumps([str(bake), overrides], sort_keys=True)
        if k not in self.cache:
            self.cache[k] = load_scene(bake, overrides)
        return self.cache[k]


def render_frames(scene: Scene, first: int, last: int, solo: list[str], stems: bool = False):
    """Render frames [first, last] of the selected sources; a selection that matches nothing is
    digital silence of the right length."""
    if not any(render.matches(s, pat) for s in scene.sources for pat in solo):
        n = scene.length_samples(first, last)
        return render.RenderResult(np.zeros((n, 2)), scene.sample_rate, (first, last), [])
    return render.render(scene, frames=(first, last), solo=solo, stems=stems)


def render_section(section_dir: Path) -> dict:
    man = manifest(section_dir)
    key, fps = man["key"], man["fps"]
    spf = man["sample_rate"] // fps
    scenes = Scenes(section_dir, man)
    out = section_dir / "passes"
    out.mkdir(exist_ok=True)
    total = np.zeros((man["frames"][1] * spf, 2))
    rows = []
    for p in man["passes"]:
        first, last = p["window"]
        scene = scenes.get(p)
        t0 = time.perf_counter()
        result = render_frames(scene, first, last, [f"{key}.{p['key']}.*"], stems=True)
        seconds = time.perf_counter() - t0
        n = (last - first + 1) * spf
        if len(result.audio) != n:
            raise SystemExit(f"{key}.{p['key']}: {len(result.audio)} samples for {last - first + 1} frames")
        wav = out / f"{key}.{p['key']}.wav"
        mix.write_wav(wav, result.audio, result.rate)
        for group, audio in result.stems.items():
            mix.write_wav(mix.stem_path(wav, group), audio, result.rate)
        result.warnings = [w for w in result.warnings if w not in scene.warnings]
        rep = report.build_report(scene, result, wav, {"master_gain_db": man["gain_db"], **p["settings"]})
        tail = float(np.abs(result.audio[-int(TAIL_S[0] * result.rate):-int(TAIL_S[1] * result.rate)]).max(initial=0.0))
        if tail > 10 ** (TAIL_DBFS / 20):
            rep["warnings"].append(f"the pass ends at {20 * np.log10(tail):.1f} dBFS: a tail is cut off (S3)")
        report.write_report(wav.with_suffix(".report.json"), rep)
        if result.sources:
            plot.write_plot(wav.with_suffix(".plot.png"), scene, result)
        total[(first - 1) * spf:last * spf] = result.audio
        rows.append({"pass": p["key"], "frames": [first, last], "settings": p["settings"], "master": rep["master"],
                     "audible": sum(1 for s in rep["sources"] if s.get("audible_frames", 1)),
                     "sources": len(rep["sources"]), "render_seconds": round(seconds, 2),
                     # the process's peak so far: the largest pass rendered up to here
                     "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
                     "warnings": rep["warnings"]})
    wav = section_dir / f"{key}.wav"
    mix.write_wav(wav, total, man["sample_rate"])
    edge = int(EDGE_S * man["sample_rate"])
    ends = [float(np.abs(total[:edge]).max()), float(np.abs(total[-edge:]).max())]
    reference = next(r for r in rows if r["pass"] == man["reference"])
    summary = {"output": str(wav.resolve()), "sample_rate": man["sample_rate"], "fps": float(fps),
               "frames": man["frames"], "gain_db": man["gain_db"], "master": report.metrics(total, man["sample_rate"]),
               "reference": {"pass": man["reference"], **reference["master"]},
               "ends_dbfs": [None if e == 0 else round(20 * np.log10(e), 1) for e in ends], "passes": rows,
               "bake_warnings": sorted({w for s in scenes.cache.values() for w in s.warnings})}
    report.write_report(wav.with_suffix(".report.json"), summary)
    return summary


def describe(summary: dict) -> str:
    lines = []
    for r in summary["passes"]:
        m = r["master"]
        lines.append(f"  {r['pass']:12s} {r['frames'][0]:5d}-{r['frames'][1]:5d}  peak {m['peak_dbfs']!s:>7} dBFS  "
                     f"true peak {m['true_peak_dbtp']!s:>7} dBTP  {m['lufs_integrated']!s:>7} LUFS")
        lines += [f"    warning: {w}" for w in r["warnings"]]
    m, ref = summary["master"], summary["reference"]
    lines.append(f"  section: true peak {m['true_peak_dbtp']} dBTP; reference pass {ref['pass']}: "
                 f"{ref['lufs_integrated']} LUFS; ends {summary['ends_dbfs']} dBFS")
    lines += [f"  bake warning: {w}" for w in summary["bake_warnings"]]
    return "\n".join(lines)


def spf() -> int:
    return story.SAMPLES_PER_FRAME
