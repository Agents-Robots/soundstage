"""E15: execution time of bake and render per option, against the number of sources.

Design: one factor at a time around a baseline, each level measured over a sweep of source counts
(the cost is close to a + b * N, so a level is summarised by its fixed cost a and per-source cost b),
plus a Plackett-Burman screening design of eleven render options at N = 100 that checks whether the
one-factor effects add up (interactions). Scenes are built in Blender by ``e15_scene.py``; every
case runs the real command line (``soundstage bake`` / ``soundstage render``) as a subprocess, timed
from outside (wall time, CPU time and peak memory from ``wait4``).

    python e15_option_costs.py run bake|render|pb [--reps N] [--only FACTOR ...] [--max-sources N]
    python e15_option_costs.py analyse [--figures DIR]
    python e15_option_costs.py list bake|render|pb

``run`` executes the cases that are not in the results file yet (resumable; the order is shuffled per
repetition, seeded) and appends one JSON line per run to ``out/e15/results.jsonl``. Run it on an
otherwise idle machine (the compute nodes: one ``run`` per node); render cases need the baked
scenes of the bake baseline (``run bake --only base noocc seconds``). ``analyse`` prints the
matrices and writes the figures (default ``out/e15/``).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "out" / "e15"
RESULTS = OUT / "results.jsonl"
SCENE_SCRIPT = Path(__file__).with_name("e15_scene.py")
EMPTY = OUT / "empty.blend"
SOURCES = [1, 3, 10, 30, 100, 300, 1000]

# --- bake cases: (factor, level, environment overrides) around the baseline ---
# culling off unless the cull_db factor sets it: the cases measure the engine as it was before culling (E16)
BAKE_BASE = {"kind": "objects", "buildings": 200, "seconds": 60, "settings": {"cull_db": None}}
BAKE_FACTORS: list[tuple[str, str, dict]] = [
    ("base", "baseline", {}),
    ("substeps", "1", {"settings": {"substeps": 1}}),
    ("substeps", "2", {"settings": {"substeps": 2}}),
    ("substeps", "8", {"settings": {"substeps": 8}}),
    ("substeps", "16", {"settings": {"substeps": 16}}),
    ("occlusion_rate", "0", {"settings": {"occlusion_rate": 0}}),
    ("occlusion_rate", "2.5", {"settings": {"occlusion_rate": 2.5}}),
    ("occlusion_rate", "5", {"settings": {"occlusion_rate": 5}}),
    ("occlusion_rate", "20", {"settings": {"occlusion_rate": 20}}),
    ("occlusion_rate", "40", {"settings": {"occlusion_rate": 40}}),
    ("occluder_min_size", "0.5", {"settings": {"occluder_min_size": 0.5}}),
    ("occluder_min_size", "8", {"settings": {"occluder_min_size": 8}}),
    ("pad_seconds", "0", {"settings": {"pad_seconds": 0}}),
    ("pad_seconds", "10", {"settings": {"pad_seconds": 10}}),
    ("buildings", "0", {"buildings": 0}),
    ("buildings", "50", {"buildings": 50}),
    ("buildings", "800", {"buildings": 800}),
    ("buildings", "3200", {"buildings": 3200}),
    ("kind", "collection", {"kind": "collection"}),
    ("kind", "nodes", {"kind": "nodes", "settings": {"instance_limit": 0}}),
    ("kind", "nodes, limit 32", {"kind": "nodes"}),
    ("seconds", "30", {"seconds": 30}),
    ("seconds", "120", {"seconds": 120}),
    ("cull_db", "-40", {"settings": {"cull_db": -40}}),
    ("cull_db", "-20", {"settings": {"cull_db": -20}}),
]
BAKE_DEFAULTS = {"substeps": "4", "occlusion_rate": "10", "occluder_min_size": "2", "pad_seconds": "3",
                 "buildings": "200", "kind": "objects", "seconds": "60", "cull_db": "off in these runs"}
# render cases use these baked scenes (kept on disk); the rest of the bake output is deleted
KEEP_SCENES = {("base", "baseline"): "base", ("occlusion_rate", "0"): "noocc", ("seconds", "30"): "s30",
               ("seconds", "120"): "s120"}

# --- render cases: (factor, level, scene, command-line arguments) ---
RENDER_FACTORS: list[tuple[str, str, str, list[str]]] = [
    ("base", "baseline", "base", []),
    ("visibility", "none (not baked)", "noocc", []),
    ("quality", "high", "base", ["--quality", "high"]),
    ("panner", "amplitude", "base", ["--set", "panner=amplitude"]),
    ("pan_law", "power", "base", ["--set", "pan_law=power"]),
    ("head_shadow", "0", "base", ["--set", "head_shadow=0"]),
    ("itd_scale", "0", "base", ["--set", "itd_scale=0"]),
    ("air_absorption", "0", "base", ["--set", "air_absorption=0"]),
    ("doppler_factor", "0", "base", ["--set", "doppler_factor=0"]),
    ("doppler_factor", "0.5", "base", ["--set", "doppler_factor=0.5"]),
    ("reverb", "room (0.4 s)", "base", ["--set", "reverb=room"]),
    ("reverb", "city (1.5 s)", "base", ["--set", "reverb=city"]),
    ("reverb", "hangar (10 s)", "base", ["--set", "reverb=hangar"]),
    ("stems", "on", "base", ["--stems"]),
    ("report", "on", "base", ["--report"]),
    ("normalize", "-23 LUFS", "base", ["--normalize", "-23"]),
    ("limit", "-1 dBTP", "base", ["--limit", "-1"]),
    ("plot", "on", "base", ["--plot"]),
    ("pcm24", "on", "base", ["--pcm24"]),
    ("seconds", "30", "s30", []),
    ("seconds", "120", "s120", []),
    ("delivery", "stems+report+plot+city+normalize+limit", "base",
     ["--stems", "--report", "--plot", "--set", "reverb=city", "--normalize", "-23", "--limit", "-1"]),
    ("cull_db", "-40", "base", ["--set", "cull_db=-40"]),
    ("cull_db", "-20", "base", ["--set", "cull_db=-20"]),
]
CULL_OFF = ["--set", "cull_db=null"]  # every other render case: culling off (scenes baked before it existed)
RENDER_DEFAULTS = {"visibility": "baked (10 Hz)", "quality": "standard", "panner": "hybrid", "pan_law": "sine",
                   "head_shadow": "0.5", "itd_scale": "0.5", "air_absorption": "1", "doppler_factor": "1",
                   "reverb": "none", "stems": "off", "report": "off", "normalize": "off", "limit": "off",
                   "plot": "off", "pcm24": "off", "seconds": "60", "delivery": "off", "cull_db": "off in these runs"}

# --- Plackett-Burman: 12 runs, 11 two-level render factors, at N = PB_SOURCES ---
PB_SOURCES = 100
PB_FACTORS = [("visibility", None), ("quality", ["--quality", "high"]), ("panner", ["--set", "panner=amplitude"]),
              ("air_absorption", ["--set", "air_absorption=0"]), ("doppler_factor", ["--set", "doppler_factor=0"]),
              ("reverb", ["--set", "reverb=hangar"]), ("stems", ["--stems"]), ("report", ["--report"]),
              ("normalize", ["--normalize", "-23"]), ("limit", ["--limit", "-1"]), ("plot", ["--plot"])]
PB_LEVEL = {"visibility": "none (not baked)", "quality": "high", "panner": "amplitude", "air_absorption": "0",
            "doppler_factor": "0", "reverb": "hangar (10 s)", "stems": "on", "report": "on", "normalize": "-23 LUFS",
            "limit": "-1 dBTP", "plot": "on"}
PB_ROW = [1, 1, -1, 1, 1, 1, -1, -1, -1, 1, -1]  # Plackett-Burman generator for N = 12


def pb_design() -> list[list[int]]:
    rows = [PB_ROW[-k:] + PB_ROW[:-k] for k in range(11)]
    return rows + [[-1] * 11]


# --- cases ---
def bake_cases(only: list[str] | None, max_sources: int) -> list[dict]:
    out = []
    for factor, level, over in BAKE_FACTORS:
        if only and factor not in only and not (factor == "occlusion_rate" and level == "0" and "noocc" in only):
            continue
        for n in SOURCES:
            if n > max_sources or (n == 1000 and factor not in ("base", "kind", "occlusion_rate", "cull_db")):
                continue
            cfg = {**BAKE_BASE, **over, "settings": {**BAKE_BASE["settings"], **over.get("settings", {})}}
            out.append({"stage": "bake", "factor": factor, "level": level, "n": n, "config": cfg,
                        "key": f"bake|{factor}|{level}|{n}"})
    return out


def render_cases(only: list[str] | None, max_sources: int) -> list[dict]:
    out = []
    for factor, level, scene, args in RENDER_FACTORS:
        if only and factor not in only:
            continue
        for n in SOURCES:
            if n > max_sources or (n == 1000 and factor not in ("base", "quality", "reverb", "delivery", "cull_db")):
                continue
            out.append({"stage": "render", "factor": factor, "level": level, "n": n, "scene": scene, "args": args,
                        "key": f"render|{factor}|{level}|{n}"})
    return out


def pb_cases() -> list[dict]:
    out = []
    for i, row in enumerate(pb_design()):
        args = [x for (name, a), s in zip(PB_FACTORS, row) if s > 0 and a for x in a]
        scene = "noocc" if row[0] > 0 else "base"
        out.append({"stage": "pb", "factor": "pb", "level": str(i), "n": PB_SOURCES, "scene": scene, "args": args,
                    "row": row, "key": f"pb|{i}|{PB_SOURCES}"})
    return out


def scene_dir(name: str, n: int) -> Path:
    return OUT / "scenes" / f"{name}_{n}"


# --- running ---
def timed(cmd: list[str], env: dict | None = None, cwd: Path | None = None) -> dict:
    """Run a command; wall and CPU seconds, peak RSS of the child (MB), output."""
    t0 = time.perf_counter()
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, cwd=cwd, text=True)
    out = p.stdout.read()
    _, status, ru = os.wait4(p.pid, 0)
    wall = time.perf_counter() - t0
    p.returncode = os.waitstatus_to_exitcode(status)
    return {"wall_s": round(wall, 3), "cpu_s": round(ru.ru_utime + ru.ru_stime, 2), "maxrss_mb": round(ru.ru_maxrss / 1024),
            "exit": p.returncode, "end": time.time(), "output": out}


def soundstage_cmd() -> list[str]:
    exe = shutil.which("soundstage")
    return [exe] if exe else [sys.executable, "-m", "soundstage.cli"]


RENDER_WRAPPER = (
    "import sys, json\n"
    "from soundstage import cli\n"
    "from soundstage.engine import render as R\n"
    "f = R.render\n"
    "def g(*a, **k):\n"
    "    r = f(*a, **k)\n"
    "    print('[e15] timing ' + json.dumps(r.timing_s), flush=True)\n"
    "    return r\n"
    "R.render = g\n"
    "sys.exit(cli.main(sys.argv[1:]))\n"
)


def run_bake(case: dict, rep: int) -> dict:
    cfg = case["config"]
    out = OUT / "work" / f"bake_{socket.gethostname()}"
    keep = KEEP_SCENES.get((case["factor"], case["level"]))
    if keep and rep == 0:
        out = scene_dir(keep, case["n"])
    if out.exists():
        shutil.rmtree(out)
    env = {**os.environ, "E15_SOURCES": str(case["n"]), "E15_KIND": cfg["kind"], "E15_BUILDINGS": str(cfg["buildings"]),
           "E15_SECONDS": str(cfg["seconds"]), "E15_SETTINGS": json.dumps(cfg["settings"])}
    r = timed(soundstage_cmd() + ["bake", str(EMPTY), "--run", str(SCENE_SCRIPT), "--out", str(out)], env=env)
    built_at = vis_s = None
    occluders = None
    for line in r["output"].splitlines():
        if "e15 built_at" in line:
            built_at = float(line.split()[-1])
        elif "visibility:" in line and " in " in line:
            vis_s = float(line.split(" in ")[1].split()[0])
        elif "occluders:" in line:
            occluders = int(line.split("occluders:")[1].split()[0])
    r["build_s"] = round(r["wall_s"] - (r["end"] - built_at), 2) if built_at else None
    r["bake_s"] = round(r["end"] - built_at, 2) if built_at else None
    r["visibility_s"] = vis_s
    r["occluders"] = occluders
    if r["exit"] == 0:
        m = json.loads((out / "scene.json").read_text())
        r["sources_baked"] = len(m["sources"])
    if not keep or rep > 0:
        shutil.rmtree(out, ignore_errors=True)
    return r


def run_render(case: dict, rep: int) -> dict:
    scene = scene_dir(case["scene"], case["n"]) / "scene.json"
    if not scene.exists():
        return {"exit": -1, "output": f"missing scene {scene}", "wall_s": None}
    work = OUT / "work" / f"render_{socket.gethostname()}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    env = {**os.environ, "PYTHONPATH": f"{REPO}{os.pathsep}{os.environ.get('PYTHONPATH', '')}"}
    py = os.environ.get("E15_PYTHON", sys.executable)
    args = case["args"] if any(a.startswith("cull_db=") for a in case["args"]) else CULL_OFF + case["args"]
    r = timed([py, "-c", RENDER_WRAPPER, "render", str(scene), "-o", str(work / "mix.wav"), *args], env=env)
    for line in r["output"].splitlines():
        if line.startswith("[e15] timing"):
            t = json.loads(line.split("timing ", 1)[1])
            r["setup_s"], r["dsp_s"], r["workers"] = t["load"], t["dsp"], t["workers"]
    shutil.rmtree(work, ignore_errors=True)
    return r


def done_keys() -> dict[str, int]:
    counts: dict[str, int] = {}
    if RESULTS.exists():
        for line in RESULTS.read_text().splitlines():
            r = json.loads(line)
            if r.get("exit") == 0:
                counts[r["key"]] = counts.get(r["key"], 0) + 1
    return counts


def cmd_run(a: argparse.Namespace) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if not EMPTY.exists():
        subprocess.run(["blender", "-b", "--factory-startup", "--python-expr",
                        f"import bpy; bpy.ops.wm.read_factory_settings(use_empty=True); "
                        f"bpy.ops.wm.save_as_mainfile(filepath={str(EMPTY)!r})"], check=True, capture_output=True)
    cases = {"bake": bake_cases, "render": render_cases}.get(a.stage, lambda o, m: pb_cases())(a.only, a.max_sources)
    if a.stage != "bake":  # warm the numba cache and the page cache, not recorded
        c = cases[0]
        print(f"warm-up: {c['key']}", flush=True)
        run_render(c, 0)
    host = socket.gethostname()
    for rep in range(a.reps):
        todo = [c for c in cases if done_keys().get(c["key"], 0) <= rep]
        random.Random(rep).shuffle(todo)
        if a.stage == "bake":  # scenes kept for the render stage first, small cases before large ones
            todo.sort(key=lambda c: (KEEP_SCENES.get((c["factor"], c["level"])) is None, c["n"] >= 300))
        for k, c in enumerate(todo):
            r = (run_bake if a.stage == "bake" else run_render)(c, rep)
            rec = {k2: v for k2, v in c.items() if k2 != "config"} | {"rep": rep, "host": host,
                                                                       "time": time.strftime("%Y-%m-%dT%H:%M:%S")}
            rec.update({k2: v for k2, v in r.items() if k2 not in ("output", "end")})
            if r["exit"] != 0:
                rec["tail"] = r["output"][-1500:]
            with RESULTS.open("a") as f:
                f.write(json.dumps(rec) + "\n")
            print(f"[{rep}:{k + 1}/{len(todo)}] {c['key']}: {r.get('wall_s')} s exit {r['exit']}", flush=True)


def cmd_list(a: argparse.Namespace) -> None:
    cases = {"bake": bake_cases, "render": render_cases}.get(a.stage, lambda o, m: pb_cases())(None, 10 ** 9)
    for c in cases:
        print(c["key"], c.get("args", c.get("config")))
    print(len(cases), "cases")


# --- analysis ---
def load_results() -> list[dict]:
    if not RESULTS.exists():
        return []
    return [r for r in map(json.loads, RESULTS.read_text().splitlines()) if r.get("exit") == 0 and r.get("wall_s")]


def medians(rows: list[dict], stage: str, value: str = "wall_s") -> dict[tuple[str, str], dict[int, float]]:
    import numpy as np
    groups: dict[tuple[str, str], dict[int, list[float]]] = {}
    for r in rows:
        if r["stage"] == stage and r.get(value) is not None:
            groups.setdefault((r["factor"], r["level"]), {}).setdefault(r["n"], []).append(r[value])
    return {k: {n: float(np.median(v)) for n, v in sorted(d.items())} for k, d in groups.items()}


def fit(points: dict[int, float]) -> tuple[float, float] | None:
    """t = a + b N, least squares on relative error (weights 1/t)."""
    import numpy as np
    if len(points) < 2:
        return None
    n = np.array(list(points), float)
    t = np.array(list(points.values()))
    A = np.stack([np.ones_like(n), n], axis=1) / t[:, None]
    (a, b), *_ = np.linalg.lstsq(A, np.ones_like(t), rcond=None)
    return float(a), float(b)


def order(stage: str) -> list[tuple[str, str]]:
    if stage == "bake":
        return [(f, l) for f, l, _ in BAKE_FACTORS]
    return [(f, l) for f, l, *_ in RENDER_FACTORS]


def fmt_s(t: float) -> str:
    return f"{t:.0f}" if t >= 100 else f"{t:.1f}" if t >= 10 else f"{t:.2f}"


def capped(rows: list[dict]) -> set[tuple[str, str, int]]:
    """Bake cases that baked fewer sources than the scene has (instance_limit)."""
    return {(r["factor"], r["level"], r["n"]) for r in rows
            if r["stage"] == "bake" and r.get("sources_baked") is not None and r["sources_baked"] < r["n"]}


def matrix_table(stage: str, med: dict, ns: list[int], cap: set = frozenset()) -> str:
    defaults = BAKE_DEFAULTS if stage == "bake" else RENDER_DEFAULTS
    base = med.get(("base", "baseline"), {})
    head = ["factor", "level", *[f"N={n}" for n in ns], "a (s)", "b (ms/source)", "× base at N=100"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for key in order(stage):
        if key not in med:
            continue
        pts = med[key]
        cells = []
        for n in ns:
            if n not in pts:
                cells.append("")
            elif key == ("base", "baseline") or n not in base:
                cells.append(fmt_s(pts[n]) + ("†" if (*key, n) in cap else ""))
            else:
                cells.append(f"{fmt_s(pts[n])}{'†' if (*key, n) in cap else ''} ({pts[n] / base[n]:.2f}×)")
        f = fit({n: t for n, t in pts.items() if (*key, n) not in cap})  # capped cases have fewer sources
        fb = fit(base)
        at = ""
        if f and fb:
            at = f"{(f[0] + 100 * f[1]) / (fb[0] + 100 * fb[1]):.2f}"
        label = key[1] if key[0] == "base" else f"{key[1]} (default {defaults.get(key[0], '-')})"
        lines.append("| " + " | ".join([key[0], label, *cells, f"{f[0]:.1f}" if f else "",
                                         f"{1000 * f[1]:.1f}" if f else "", at]) + " |")
    return "\n".join(lines)


def figures(stage: str, med: dict, ns: list[int], directory: Path, value_label: str,
            cap: set = frozenset()) -> list[Path]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    base = med.get(("base", "baseline"), {})
    keys = [k for k in order(stage) if k in med]
    paths = []
    # matrix: ratio to the baseline per N, annotated with seconds
    ratio = np.full((len(keys), len(ns)), np.nan)
    text = [["" for _ in ns] for _ in keys]
    for i, k in enumerate(keys):
        for j, n in enumerate(ns):
            if n in med[k]:
                text[i][j] = fmt_s(med[k][n]) + ("†" if (*k, n) in cap else "")
                if n in base:
                    ratio[i, j] = med[k][n] / base[n]
    fig, ax = plt.subplots(figsize=(1.1 * len(ns) + 4, 0.38 * len(keys) + 1.6))
    lim = max(1.0, np.nanmax(np.abs(np.log2(ratio)))) if np.isfinite(ratio).any() else 1.0
    im = ax.imshow(np.log2(ratio), cmap="RdBu_r", vmin=-lim, vmax=lim, aspect="auto")
    for i in range(len(keys)):
        for j in range(len(ns)):
            if text[i][j]:
                r = ratio[i, j]
                ax.text(j, i, text[i][j] + ("" if not np.isfinite(r) or keys[i][0] == "base" else f"\n{r:.2f}×"),
                        ha="center", va="center", fontsize=7,
                        color="white" if np.isfinite(r) and abs(np.log2(r)) > 0.6 * lim else "black")
    ax.set_xticks(range(len(ns)), [str(n) for n in ns])
    ax.set_yticks(range(len(keys)), [k[1] if k[0] == "base" else f"{k[0]} = {k[1]}" for k in keys], fontsize=8)
    ax.set_xlabel("sources")
    ax.set_title(f"{stage}: {value_label} (s) and ratio to the baseline", fontsize=10)
    cb = fig.colorbar(im, ax=ax, shrink=0.6)
    ticks = [t for t in (-4, -3, -2, -1, 0, 1, 2, 3, 4) if abs(t) <= lim]
    cb.set_ticks(ticks, labels=[f"{2.0 ** t:g}×" for t in ticks])
    p = directory / f"e15_{stage}_matrix.png"
    fig.savefig(p, dpi=110, bbox_inches="tight")
    plt.close(fig)
    paths.append(p)

    # lines: time against N per factor, baseline in every panel
    factors = list(dict.fromkeys(k[0] for k in keys if k[0] != "base"))
    if not factors:
        return paths
    cols = 4
    rows_ = -(-len(factors) // cols)
    fig, axes = plt.subplots(rows_, cols, figsize=(4 * cols, 3.1 * rows_), squeeze=False, sharex=True)
    for ax, factor in zip(axes.flat, factors):
        if base:
            ax.plot(list(base), list(base.values()), "k--", marker=".", lw=1.2, label="baseline")
        for k in keys:
            if k[0] == factor:
                ax.plot(list(med[k]), list(med[k].values()), marker="o", ms=3, lw=1.3, label=k[1])
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_title(factor, fontsize=9)
        ax.grid(True, which="both", alpha=0.25)
        ax.legend(fontsize=6.5, loc="upper left")
    for ax in axes.flat[len(factors):]:
        ax.axis("off")
    for ax in axes[-1]:
        ax.set_xlabel("sources")
    for ax in axes[:, 0]:
        ax.set_ylabel(f"{value_label} (s)")
    fig.suptitle(f"{stage}: {value_label} against the number of sources (median of repetitions)", fontsize=11)
    fig.tight_layout()
    p = directory / f"e15_{stage}_lines.png"
    fig.savefig(p, dpi=100, bbox_inches="tight")
    plt.close(fig)
    paths.append(p)

    # summary: each level's fixed cost a and per-source cost b (t = a + b N) against the baseline's
    fb = fit(base)
    fits = [(k, fit({n: t for n, t in med[k].items() if (*k, n) not in cap})) for k in keys if k[0] != "base"]
    fits = [(k, f) for k, f in fits if f]
    if fb and fits:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 0.3 * len(fits) + 1.4), sharey=True)
        y = np.arange(len(fits))[::-1]
        da = [f[0] - fb[0] for _, f in fits]
        rb = [f[1] / fb[1] for _, f in fits]
        ax1.barh(y, da, color=["#c0504d" if v > 0 else "#4f81bd" for v in da])
        ax1.axvline(0, color="k", lw=0.8)
        ax1.set_xlabel(f"fixed cost a: change (s), baseline {fb[0]:.1f} s")
        ax2.barh(y, [v - 1 for v in rb], left=1, color=["#c0504d" if v > 1 else "#4f81bd" for v in rb])
        ax2.axvline(1, color="k", lw=0.8)
        ax2.set_xscale("log")
        ax2.set_xlabel(f"per-source cost b: ratio, baseline {1000 * fb[1]:.0f} ms")
        ticks = [t for t in (0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4) if min(rb) / 1.1 <= t <= max(rb) * 1.1]
        ax2.set_xticks(ticks, [f"{t:g}×" for t in ticks])
        ax2.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
        ax1.set_yticks(y, [f"{k[0]} = {k[1]}" for k, _ in fits], fontsize=8)
        for ax in (ax1, ax2):
            ax.grid(True, axis="x", alpha=0.3)
        fig.suptitle(f"{stage}: fit t = a + b·N per level (60 s shot unless the level changes it)", fontsize=10)
        fig.tight_layout()
        p = directory / f"e15_{stage}_costs.png"
        fig.savefig(p, dpi=110, bbox_inches="tight")
        plt.close(fig)
        paths.append(p)
    return paths


def pb_analysis(rows: list[dict], render_med: dict) -> str:
    """Main effects from the screening design, and how well the one-factor effects predict each run."""
    import numpy as np
    runs: dict[int, list[float]] = {}
    for r in rows:
        if r["stage"] == "pb":
            runs.setdefault(int(r["level"]), []).append(r["wall_s"])
    if len(runs) < 12:
        return f"Plackett-Burman: {len(runs)}/12 runs so far"
    design = np.array(pb_design())
    y = np.array([np.median(runs[i]) for i in range(12)])
    base = render_med.get(("base", "baseline"), {}).get(PB_SOURCES)
    lines = ["| factor | effect from the design (s) | one-factor effect (s) |", "|---|---|---|"]
    for j, (name, _) in enumerate(PB_FACTORS):
        eff = y[design[:, j] > 0].mean() - y[design[:, j] < 0].mean()
        ofat = render_med.get((name, PB_LEVEL[name]), {}).get(PB_SOURCES)
        lines.append(f"| {name} | {eff:+.1f} | {'' if ofat is None or base is None else f'{ofat - base:+.1f}'} |")
    if base is not None:
        pred_add, pred_mul = [], []
        for row in design:
            d_add, d_mul = 0.0, 1.0
            for s, (name, _) in zip(row, PB_FACTORS):
                if s > 0:
                    ofat = render_med.get((name, PB_LEVEL[name]), {}).get(PB_SOURCES, base)
                    d_add += ofat - base
                    d_mul *= ofat / base
            pred_add.append(base + d_add)
            pred_mul.append(base * d_mul)
        err_a = np.abs(np.array(pred_add) / y - 1)
        err_m = np.abs(np.array(pred_mul) / y - 1)
        lines.append("")
        lines.append(f"runs: measured {', '.join(f'{v:.1f}' for v in y)} s")
        lines.append(f"additive prediction from the one-factor effects: median error {100 * np.median(err_a):.1f} %, "
                     f"max {100 * err_a.max():.1f} %")
        lines.append(f"multiplicative prediction: median error {100 * np.median(err_m):.1f} %, max {100 * err_m.max():.1f} %")
        # fixed costs add, per-source costs multiply: t = a0 + sum(a_i - a0) + N b0 prod(b_i / b0)
        fb = fit(render_med.get(("base", "baseline"), {}))
        fits = {name: fit(render_med.get((name, PB_LEVEL[name]), {})) for name, _ in PB_FACTORS}
        if fb and all(fits.values()):
            pred = []
            for row in design:
                a_, b_ = fb[0], fb[1]
                on = [name for s_, (name, _) in zip(row, PB_FACTORS) if s_ > 0]
                if "stems" in on and "report" in on:
                    on.remove("report")  # both build and measure the same group buses
                for name in on:
                    a_ += fits[name][0] - fb[0]
                    b_ *= fits[name][1] / fb[1]
                pred.append(a_ + PB_SOURCES * b_)
            err = np.abs(np.array(pred) / y - 1)
            lines.append(f"fixed costs added, per-source costs multiplied, stems and report counted once: median error {100 * np.median(err):.1f} %, "
                         f"max {100 * err.max():.1f} %")
            lines.append(f"  predicted {', '.join(f'{v:.1f}' for v in pred)} s")
    return "\n".join(lines)


def cmd_analyse(a: argparse.Namespace) -> None:
    rows = load_results()
    directory = Path(a.figures) if a.figures else OUT
    directory.mkdir(parents=True, exist_ok=True)
    for stage, label in (("bake", "wall time"), ("render", "wall time")):
        med = medians(rows, stage)
        if not med:
            continue
        ns = sorted({n for d in med.values() for n in d})
        reps = sum(1 for r in rows if r["stage"] == stage)
        print(f"\n## {stage} ({reps} runs)\n")
        cap = capped(rows)
        print(matrix_table(stage, med, ns, cap))
        if cap and stage == "bake":
            print("\n† fewer sources baked than in the scene (instance_limit 32 per tagged object; 10 tagged assets); "
                  "left out of the fit")
        for p in figures(stage, med, ns, directory, label, cap):
            print(f"figure: {p}")
        if stage == "bake":
            vis = medians(rows, "bake", "visibility_s")
            bk = medians(rows, "bake", "bake_s")
            bl = medians(rows, "bake", "build_s")
            b = ("base", "baseline")
            if b in bk:
                print("\nbaseline split: " + ", ".join(
                    f"N={n}: build {bl[b].get(n, float('nan')):.1f} s, bake {bk[b][n]:.1f} s "
                    f"(visibility {vis.get(b, {}).get(n, 0):.1f} s)" for n in bk[b]))
        else:
            dsp = medians(rows, "render", "dsp_s")
            st = medians(rows, "render", "setup_s")
            b = ("base", "baseline")
            if b in dsp:
                print("\nbaseline split: " + ", ".join(
                    f"N={n}: setup {st[b][n]:.2f} s, dsp {dsp[b][n]:.2f} s, other {med[b][n] - st[b][n] - dsp[b][n]:.2f} s"
                    for n in dsp[b]))
    if any(r["stage"] == "pb" for r in rows):
        print("\n## interactions (Plackett-Burman, N = %d)\n" % PB_SOURCES)
        print(pb_analysis(rows, medians(rows, "render")))
    mem = medians(rows, "render", "maxrss_mb")
    if ("base", "baseline") in mem:
        print("\nrender peak memory (MB), baseline: " + ", ".join(f"N={n}: {v:.0f}" for n, v in mem[("base", "baseline")].items()))
    mem = medians(rows, "bake", "maxrss_mb")
    if ("base", "baseline") in mem:
        print("bake peak memory (MB), baseline: " + ", ".join(f"N={n}: {v:.0f}" for n, v in mem[("base", "baseline")].items()))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("stage", choices=("bake", "render", "pb"))
    r.add_argument("--reps", type=int, default=3)
    r.add_argument("--only", nargs="*", help="factors to run (bake: 'noocc' adds occlusion_rate 0)")
    r.add_argument("--max-sources", type=int, default=10 ** 9)
    r.set_defaults(func=cmd_run)
    l_ = sub.add_parser("list")
    l_.add_argument("stage", choices=("bake", "render", "pb"))
    l_.set_defaults(func=cmd_list)
    an = sub.add_parser("analyse")
    an.add_argument("--figures", help="directory for the figures (default out/e15/)")
    an.set_defaults(func=cmd_analyse)
    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
