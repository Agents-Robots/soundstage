"""E16: culling (FR-68): render and bake time against the budget and the number of sources, and the error.

Scenes: the E15 city with every source within 120 m of the camera's path ("dense", E15's baked
scenes ``base_N``), and the same city with the sources spread over a band of +-1000 m around the
path ("spread", baked here with culling off and with the default culling in the bake; 5000 sources
are baked only, their render did not fit in memory). Every render
case runs once for its time (no stems) and once with stems for its error against the render without
culling of the same sources: error energy of the master and of the worst stem, over the whole shot
and in the worst 0.4 s window. The bake cases measure the bake time; the render of a scene baked
with culling against the render of the one baked without measures what the skipped visibility
costs.

    python e16_culling.py run bake|render [--only dense|spread] [--sizes N ...] [--reverse]
    python e16_culling.py analyse [--figures DIR]
    python e16_culling.py list bake|render

Runs the real command lines as subprocesses (timing and memory as in E15); one ``run`` per idle
machine. ``run render`` needs E15's ``base`` scenes and this experiment's bakes.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from e15_option_costs import EMPTY, SCENE_SCRIPT, soundstage_cmd, timed
from e15_option_costs import scene_dir as e15_scene_dir

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "out" / "e16"
RESULTS = OUT / "results.jsonl"
SPREAD_M = 1000
SPREAD_N = [100, 300, 1000, 2000, 5000]
OFF_MAX = 2000  # larger scenes are baked with culling only
RENDER_MAX = 2000  # 5000 sources ran out of memory in the render even with culling (killed at 73 and 111 GB)
DENSE_N = [100, 300, 1000]
BUDGETS = [None, -60, -40, -30, -20]
WINDOW_S = 0.4

WRAPPER = (
    "import sys, json\n"
    "from soundstage import cli\n"
    "from soundstage.engine import render as R\n"
    "f = R.render\n"
    "def g(*a, **k):\n"
    "    r = f(*a, **k)\n"
    "    print('[e16] result ' + json.dumps({'timing': r.timing_s, 'culling': r.culling}), flush=True)\n"
    "    return r\n"
    "R.render = g\n"
    "sys.exit(cli.main(sys.argv[1:]))\n"
)


def label(budget: float | None) -> str:
    return "off" if budget is None else f"{budget:g}"


def scene_path(scene: str) -> Path:
    """``base_N`` (E15) or ``spread_<off|cull>_N`` (this experiment)."""
    if scene.startswith("base_"):
        return e15_scene_dir("base", int(scene.split("_")[1]))
    return OUT / "scenes" / scene


# --- cases ---
def bake_cases() -> list[dict]:
    out = []
    for n in SPREAD_N:
        for bake in (["off", "cull"] if n <= OFF_MAX else ["cull"]):
            out.append({"stage": "bake", "scene": f"spread_{bake}_{n}", "n": n, "bake": bake,
                        "key": f"bake|spread_{bake}_{n}"})
    return out


def render_cases() -> list[dict]:
    """Per scene: the reference (culling off, with stems) first, then the others."""
    out = []

    def add(scene: str, n: int, kind: str, budget, ref: str | None, extra: list[str] = ()):
        for mode in ("error", "time"):
            out.append({"stage": "render", "scene": scene, "n": n, "kind": kind, "budget": label(budget),
                        "mode": mode, "ref": ref, "extra": list(extra),
                        "key": f"render|{scene}|{kind}|{label(budget)}|{mode}"})

    for n in DENSE_N:
        for b in BUDGETS:
            add(f"base_{n}", n, "dense", b, f"base_{n}|dense")
    for n in SPREAD_N:
        if n <= OFF_MAX:
            for b in BUDGETS:
                add(f"spread_off_{n}", n, "spread", b, f"spread_off_{n}|spread")
        if n <= RENDER_MAX:
            for b in (None, -40):
                add(f"spread_cull_{n}", n, "spread, bake culled", b, f"spread_off_{n}|spread")
    for n in (100, 300):  # one voice per trigger (doppler_factor != 1): culling skips the silent voices
        for b in (None, -40):
            add(f"base_{n}", n, "dense, doppler 0.5", b, f"base_{n}|dense, doppler 0.5",
                ["--set", "doppler_factor=0.5"])
    # references first, so every error case finds its reference
    out.sort(key=lambda c: not (c["budget"] == "off" and c["mode"] == "error" and c["ref"] == f"{c['scene']}|{c['kind']}"))
    return out


# --- running ---
def run_bake(case: dict) -> dict:
    out = scene_path(case["scene"])
    shutil.rmtree(out, ignore_errors=True)
    settings = {"cull_db": None} if case["bake"] == "off" else {}
    env = {**os.environ, "E15_SOURCES": str(case["n"]), "E15_SPREAD": str(SPREAD_M),
           "E15_SETTINGS": json.dumps(settings)}
    r = timed(soundstage_cmd() + ["bake", str(EMPTY), "--run", str(SCENE_SCRIPT), "--out", str(out)], env=env)
    for line in r["output"].splitlines():
        if "e15 built_at" in line:
            r["bake_s"] = round(r["end"] - float(line.split()[-1]), 2)
        elif "visibility:" in line and " in " in line:
            r["visibility_s"] = float(line.split(" in ")[1].split()[0])
        elif "culling: visibility skipped for" in line:
            r["culled_pct"] = float(line.split("skipped for ")[1].split(" %")[0])
    return r


def ref_dir(ref: str) -> Path:
    return OUT / "ref" / ref.replace("|", "__").replace(" ", "_").replace(",", "")


def errors(ref: Path, work: Path) -> dict:
    import numpy as np
    import soundfile as sf

    def db(x: float) -> float:
        return round(10 * np.log10(max(x, 1e-30)), 1)

    def compare(a_path: Path, b_path: Path) -> tuple[float, float]:
        a, rate = sf.read(a_path, dtype="float64")
        b, _ = sf.read(b_path, dtype="float64")
        e, r = np.square(a - b).sum(axis=1), np.square(a).sum(axis=1)
        w = int(WINDOW_S * rate)
        n = len(e) // w
        ew, rw = e[:n * w].reshape(n, w).sum(axis=1), r[:n * w].reshape(n, w).sum(axis=1)
        ok = rw > 1e-12 * rw.max()  # windows with sound in the reference
        return db(e.sum() / r.sum()), db(float(np.max(ew[ok] / rw[ok])) if ok.any() else 0.0)

    out = {}
    out["error_db"], out["error_window_db"] = compare(ref / "mix.wav", work / "mix.wav")
    stems = sorted(p.name for p in ref.glob("mix_stem_*.wav"))
    per = {p.split("mix_stem_")[1][:-4]: compare(ref / p, work / p) for p in stems if (work / p).exists()}
    if per:
        out["stems"] = per
        out["stem_error_db"] = max(v[0] for v in per.values())
        out["stem_error_window_db"] = max(v[1] for v in per.values())
    return out


def run_render(case: dict) -> dict:
    scene = scene_path(case["scene"]) / "scene.json"
    if not scene.exists():
        return {"exit": -1, "output": f"missing scene {scene}", "wall_s": None}
    work = OUT / "work" / f"render_{socket.gethostname()}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    args = ["--set", f"cull_db={'null' if case['budget'] == 'off' else case['budget']}", *case["extra"]]
    if case["mode"] == "error":
        args.append("--stems")
    env = {**os.environ, "PYTHONPATH": f"{REPO}{os.pathsep}{os.environ.get('PYTHONPATH', '')}"}
    r = timed([sys.executable, "-c", WRAPPER, "render", str(scene), "-o", str(work / "mix.wav"), *args], env=env)
    for line in r["output"].splitlines():
        if line.startswith("[e16] result"):
            res = json.loads(line.split("result ", 1)[1])
            t = res["timing"]
            r["setup_s"], r["dsp_s"], r["cull_s"] = t["load"], t["dsp"], t.get("cull")
            r["culling"] = res["culling"]
    if r["exit"] == 0 and case["mode"] == "error" and case["ref"]:
        own = case["ref"] == f"{case['scene']}|{case['kind']}" and case["budget"] == "off"
        ref = ref_dir(case["ref"])
        if own:
            shutil.rmtree(ref, ignore_errors=True)
            shutil.copytree(work, ref)
        elif ref.exists():
            r.update(errors(ref, work))
    shutil.rmtree(work, ignore_errors=True)
    return r


def done() -> set[str]:
    if not RESULTS.exists():
        return set()
    return {r["key"] for r in map(json.loads, RESULTS.read_text().splitlines()) if r.get("exit") == 0}


def cmd_run(a: argparse.Namespace) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if not EMPTY.exists():
        subprocess.run(["blender", "-b", "--factory-startup", "--python-expr",
                        f"import bpy; bpy.ops.wm.read_factory_settings(use_empty=True); "
                        f"bpy.ops.wm.save_as_mainfile(filepath={str(EMPTY)!r})"], check=True, capture_output=True)
    cases = bake_cases() if a.stage == "bake" else render_cases()
    if a.only:  # scene kinds by prefix ("dense" also takes "dense, doppler 0.5")
        cases = [c for c in cases if any(c.get("kind", c["scene"]).startswith(k) for k in a.only)]
    if a.sizes:
        cases = [c for c in cases if c["n"] in a.sizes]
    if a.reverse:  # a second machine works from the other end; references stay first
        refs = [c for c in cases if c.get("budget") == "off" and c.get("mode") == "error"]
        cases = refs + [c for c in reversed(cases) if c not in refs]
    todo = [c for c in cases if c["key"] not in done()]
    if a.stage == "render" and todo:  # warm the numba cache and the page cache, not recorded
        run_render({**todo[0], "mode": "time"})
    host = socket.gethostname()
    for k, c in enumerate(todo):
        if c["key"] in done():  # finished by another machine meanwhile
            continue
        r = (run_bake if a.stage == "bake" else run_render)(c)
        rec = c | {"host": host, "time": time.strftime("%Y-%m-%dT%H:%M:%S")}
        rec.update({k2: v for k2, v in r.items() if k2 not in ("output", "end")})
        if r["exit"] != 0:
            rec["tail"] = r["output"][-1500:]
        with RESULTS.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"[{k + 1}/{len(todo)}] {c['key']}: {r.get('wall_s')} s exit {r['exit']}", flush=True)


def cmd_list(a: argparse.Namespace) -> None:
    cases = bake_cases() if a.stage == "bake" else render_cases()
    for c in cases:
        print(c["key"])
    print(len(cases), "cases")


# --- analysis ---
def load() -> list[dict]:
    if not RESULTS.exists():
        return []
    rows = {}
    for r in map(json.loads, RESULTS.read_text().splitlines()):
        if r.get("exit") == 0:
            rows[r["key"]] = r  # the latest run of a case
    return list(rows.values())


def fmt(x, unit: str = "") -> str:
    if x is None:
        return ""
    return (f"{x:.0f}" if abs(x) >= 100 else f"{x:.1f}" if abs(x) >= 10 else f"{x:.2f}") + unit


def table(head: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def by_distance(scene: str, step_s: float = WINDOW_S) -> tuple[list[list], dict]:
    """Power of each source at the camera every ``step_s`` (gain, distance law, sample mean square,
    one-shots while they sound; no travel time, cone, occlusion or filters), summed per octave of
    distance and over the shot; and the share of sources the rule (per group) would drop at each
    moment if a source's power were its value at that moment."""
    import numpy as np

    from soundstage.engine import signals
    from soundstage.engine.scene import load_scene
    from soundstage.levels import distance_gain, skip_mask

    sc = load_scene(scene_path(scene) / "scene.json")
    t_all = np.asarray(sc.seconds(sc.frames), dtype=np.float64)
    pick = np.unique(np.searchsorted(t_all, np.arange(t_all[0], t_all[-1], step_s)))
    t, lpos = t_all[pick], sc.listener_matrix[pick, :3, 3]
    spatial = [src for src in sc.sources if src.spatial]
    power = np.zeros((len(spatial), len(t)))
    dist = np.zeros_like(power)
    for i, src in enumerate(spatial):
        p = src.params
        ms, _, length_s = signals.sample_stats(p["sample"])
        if p["mode"] == "once":
            frames = p["frame"] if isinstance(p["frame"], list) else [p["frame"]]
            on = np.zeros(len(t), dtype=bool)
            for f in frames:
                t0 = float(sc.seconds(f))
                on |= (t >= t0) & (t <= t0 + length_s / p["pitch"])
        else:
            on = np.ones(len(t), dtype=bool)
        dist[i] = np.linalg.norm(sc.src_pos[pick, src.track] - lpos, axis=1)
        dg = distance_gain(dist[i], p["distance_model"], p["ref_distance"], p["max_distance"], p["rolloff"])
        power[i] = 10 ** (p["gain_db"] / 10) * ms * dg ** 2 * on
    edges = [0] + [15 * 2 ** k for k in range(8)] + [np.inf]
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (dist >= lo) & (dist < hi)
        if m.any():
            name = f"{lo:g}–{hi:g} m" if np.isfinite(hi) else f"over {lo:g} m"
            rows.append([name, f"{m.sum(axis=0).mean():.0f}", f"{100 * power[m].sum() / power.sum():.1f} %"])
    groups = [src.group for src in spatial]
    sounding = (power > 0).sum()
    drop = {b: f"{100 * (skip_mask(power, groups, b) & (power > 0)).sum() / sounding:.0f} %" for b in (-60, -40, -20)}
    return rows, {"sources": len(spatial), "sounding": f"{100 * sounding / power.size:.0f} %", "drop": drop}


def cmd_analyse(a: argparse.Namespace) -> None:
    rows = load()
    by = {(r["stage"], r["scene"], r.get("kind"), r.get("budget"), r.get("mode")): r for r in rows}
    out = []
    kinds = ["dense", "spread", "spread, bake culled", "dense, doppler 0.5"]
    head = ["scenes", "N", "cull_db", "render (s)", "× vs off", "setup / audio (s)", "memory (GB)",
            "voice time rendered", "skipped before setup", "error (dB)", f"worst {WINDOW_S:g} s (dB)",
            "worst stem (dB)", f"worst stem, {WINDOW_S:g} s (dB)"]
    body = []
    for kind in kinds:
        scenes = sorted({(r["n"], r["scene"]) for r in rows if r["stage"] == "render" and r["kind"] == kind})
        for n, scene in scenes:
            off = by.get(("render", scene, kind, "off", "time"))
            for b in [label(x) for x in BUDGETS]:
                t = by.get(("render", scene, kind, b, "time"))
                e = by.get(("render", scene, kind, b, "error"))
                if t is None:
                    continue
                c = t.get("culling") or {}
                show = e is not None and (b != "off" or kind.endswith("culled"))
                err = [fmt(e.get(k)) if show else "" for k in
                       ("error_db", "error_window_db", "stem_error_db", "stem_error_window_db")]
                body.append([kind, n, b, fmt(t["wall_s"]), fmt(off["wall_s"] / t["wall_s"]) + "×" if off else "",
                             f"{fmt(t.get('setup_s'))} / {fmt(t.get('dsp_s'))}", fmt(t["maxrss_mb"] / 1024),
                             f"{100 * c['rendered_share']:.0f} %" if c else "100 %",
                             c.get("skipped_before_setup", "") if c else "", *err])
    out.append("## render\n")
    out.append(table(head, body))
    out.append("\nError: energy of (render - reference) against the reference, where the reference is the render "
               "without culling of the same sources (for 'bake culled': of the scene baked without culling).")

    bh = ["N", "bake culling", "bake (s)", "of which visibility (s)", "visibility skipped", "memory (GB)"]
    bb = []
    for n in SPREAD_N:
        for bake in ("off", "cull"):
            r = by.get(("bake", f"spread_{bake}_{n}", None, None, None))
            if r:
                bb.append([n, "off" if bake == "off" else "-40 dB (default)", fmt(r["wall_s"]),
                           fmt(r.get("visibility_s")), f"{r['culled_pct']:.0f} %" if "culled_pct" in r else "",
                           fmt(r["maxrss_mb"] / 1024)])
    out.append("\n## bake (spread scenes)\n")
    out.append(table(bh, bb))
    for scene in ("base_1000", "spread_off_1000"):
        if (scene_path(scene) / "scene.json").exists():
            dr, info = by_distance(scene)
            drop = ", ".join(f"{b} dB: {k}" for b, k in info["drop"].items())
            out.append(f"\n## power at the camera by distance: {scene} ({info['sources']} spatial sources)\n")
            out.append(table(["distance at the moment", "sources (mean)", "share of the power"], dr))
            out.append(f"\nSounding: {info['sounding']} of source time. Share of the sounding source time the rule "
                       f"drops, per {WINDOW_S:g} s moment and group: {drop}.")
    text = "\n".join(out)
    print(text)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "analysis.md").write_text(text + "\n")
    if a.figures:
        figures(rows, Path(a.figures))


def figures(rows: list[dict], where: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    where.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    styles = {"off": ("k", "o", "-"), "-40": ("C0", "s", "-"), "-20": ("C3", "^", "-")}
    for ax, kinds, title in ((axes[0], ("dense",), "dense: every source within 120 m of the path"),
                             (axes[1], ("spread", "spread, bake culled"), f"spread: sources within ±{SPREAD_M} m")):
        for b, (color, marker, ls) in styles.items():
            pts = sorted((r["n"], r["wall_s"]) for r in rows if r["stage"] == "render" and r["kind"] in kinds
                         and r["budget"] == b and r["mode"] == "time"
                         and not (r["kind"] == "spread, bake culled" and r["n"] <= OFF_MAX))
            if pts:
                n, t = zip(*pts)
                ax.plot(n, t, color=color, marker=marker, ls=ls, label="culling off" if b == "off" else f"cull_db {b}")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("sources")
        ax.set_title(title, fontsize=10)
        ax.grid(True, which="both", alpha=0.3)
        ax.legend(fontsize=8)
    axes[0].set_ylabel("render time (s), 60 s shot")
    fig.tight_layout()
    fig.savefig(where / "e16_render_time.png", dpi=110)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    for key, marker, name in (("error_db", "o", "master, whole shot"), ("error_window_db", "s", f"master, worst {WINDOW_S:g} s"),
                              ("stem_error_window_db", "^", f"worst stem, worst {WINDOW_S:g} s")):
        pts = [(float(r["budget"]), r[key]) for r in rows if r["stage"] == "render" and r.get("mode") == "error"
               and r.get("budget") not in (None, "off") and r.get(key) is not None and r["kind"] in ("dense", "spread")]
        if pts:
            x, y = zip(*pts)
            ax.scatter(np.array(x) + {"o": -0.6, "s": 0, "^": 0.6}[marker], y, marker=marker, label=name, alpha=0.8)
    ax.plot([-65, -15], [-65, -15], "k--", lw=1, label="error = budget")
    ax.set_xlabel("cull_db (dB)")
    ax.set_ylabel("measured error (dB)")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    ax.set_title("error of culled renders against the full render", fontsize=10)
    fig.tight_layout()
    fig.savefig(where / "e16_error.png", dpi=110)
    plt.close(fig)
    print(f"figures: {where / 'e16_render_time.png'}, {where / 'e16_error.png'}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("stage", choices=["bake", "render"])
    r.add_argument("--only", nargs="+", help="scene kinds (render: dense, spread)")
    r.add_argument("--sizes", nargs="+", type=int, help="numbers of sources")
    r.add_argument("--reverse", action="store_true", help="last case first (a second machine on the same list)")
    an = sub.add_parser("analyse")
    an.add_argument("--figures")
    ls = sub.add_parser("list")
    ls.add_argument("stage", choices=["bake", "render"])
    a = p.parse_args()
    {"run": cmd_run, "analyse": cmd_analyse, "list": cmd_list}[a.cmd](a)


if __name__ == "__main__":
    main()
