"""E18: thousands of sources with the far field (FR-56): render time, memory and the difference to
the full render, against the number of cars and ``detail_voices``.

Scene: ``e18_traffic_scene.py`` (flying cars on looping lanes in a canyon of towers, a camera
flying through, 60 s), baked with N = 500 ... 10 000 cars. Every render case runs the real command
line as a subprocess (wall time and peak memory as in E15). ``detail_voices`` null (every car
through the full chain) is the reference for N up to 2000; larger references do not fit in memory
(E16). The difference to the reference is measured on the master, per 0.4 s block: the waveform
error (as in E16), the level in 1/3-octave bands (L + R) and the left/right balance per octave
band, over the bands within 60 dB of the block's loudest. The far field starts each car's loop at
another point than the full chain when its pitch is not 1 (it reads the shared unpitched cycle), so
the case ``phase`` measures what that alone changes: the full render again with other random loop
phases (the source ids renamed), against the reference. The cases ``unpitched`` render the scene
with every pitch set to 1 (both tiers then read the same loop phase), at ``detail_voices`` null
(their own reference) and 64: what the far field's simplifications alone change.

The scenes are baked with every visibility path for every car (``detail_voices`` null in the bake),
so the render cases differ from the reference by the far field alone. The ``direct`` bakes use the
default (64): the cars ranked beyond 128 get the direct path only; the render case ``direct``
renders them at 64 against the same reference (far field and far visibility together).

The two ``clutter`` bakes (500 cars, 20 s, a million instanced balconies on the canyon walls) time
how the moving occluders are placed per visibility sample: the cars by their instancer's matrix
(the default) against the lookup in the depsgraph's instances, a walk over every instance.

    python e18_traffic.py run bake|render [--sizes N ...] [--reverse] [--again PATTERN ...]
    python e18_traffic.py analyse [--figures DIR]
    python e18_traffic.py list bake|render
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import socket
import sys
import time
from pathlib import Path

import numpy as np

from e15_option_costs import EMPTY, soundstage_cmd, timed

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "out" / "e18"
RESULTS = OUT / "results.jsonl"
SCENE_SCRIPT = Path(__file__).with_name("e18_traffic_scene.py")
CARS = [500, 1000, 2000, 5000, 10000]
REFERENCE_MAX = 2000
UNPITCHED_MAX = 2000
DETAIL = [None, 16, 32, 64, 128]
BAKE_ARGS = ["--substeps", "2", "--pad", "6"]
VIS_STEP = 6  # the bake's visibility step at 30 fps, substeps 2 and occlusion_rate 10 Hz
CLUTTER = {"n": 500, "seconds": 20, "balconies": 1_000_000}
WALK_SCRIPT = OUT / "walk.py"  # makes the bake look every moving instance up in the depsgraph
WINDOW_S = 0.4
FLOOR_DB = 60.0  # bands this far below the block's loudest are left out of the band comparisons

WRAPPER = (
    "import sys, json\n"
    "from soundstage import cli\n"
    "from soundstage.engine import render as R\n"
    "f = R.render\n"
    "def g(*a, **k):\n"
    "    r = f(*a, **k)\n"
    "    print('[e18] result ' + json.dumps({'timing': r.timing_s, 'lod': r.lod, 'culling': r.culling}), flush=True)\n"
    "    return r\n"
    "R.render = g\n"
    "sys.exit(cli.main(sys.argv[1:]))\n"
)


def label(detail: int | None) -> str:
    return "null" if detail is None else str(detail)


def scene_dir(n: int, direct: bool = False) -> Path:
    return OUT / "scenes" / (f"cars_{n}_direct" if direct else f"cars_{n}")


def bake_cases() -> list[dict]:
    return ([{"stage": "bake", "n": n, "key": f"bake|{n}"} for n in CARS]
            + [{"stage": "bake", "n": n, "direct": True, "key": f"bake|{n}|direct"} for n in CARS]
            + [{"stage": "bake", "n": CLUTTER["n"], "clutter": how, "key": f"bake|clutter|{how}"}
               for how in ("instancer", "walk")])


def render_cases() -> list[dict]:
    out = []
    for n in CARS:
        for d in DETAIL:
            if d is None and n > REFERENCE_MAX:
                continue
            out.append({"stage": "render", "n": n, "detail": label(d), "key": f"render|{n}|{label(d)}"})
        if n <= REFERENCE_MAX:
            out.append({"stage": "render", "n": n, "detail": "phase", "key": f"render|{n}|phase"})
        out.append({"stage": "render", "n": n, "detail": "direct", "key": f"render|{n}|direct"})
        if n <= UNPITCHED_MAX:
            out += [{"stage": "render", "n": n, "detail": d, "key": f"render|{n}|{d}"}
                    for d in ("unpitched-null", "unpitched-64")]
    out.sort(key=lambda c: not c["detail"].endswith("null"))  # references first
    return out


def run_bake(case: dict) -> dict:
    direct = case.get("direct", False)
    clutter = case.get("clutter")
    out = OUT / "work" / f"clutter_{socket.gethostname()}" if clutter else scene_dir(case["n"], direct)
    shutil.rmtree(out, ignore_errors=True)
    env = {**os.environ, "E18_CARS": str(case["n"]), "E18_SECONDS": str(CLUTTER["seconds"] if clutter else 60),
           "E18_CLUTTER": str(CLUTTER["balconies"] if clutter else 0),
           "E18_SETTINGS": "{}" if direct or clutter else json.dumps({"detail_voices": None})}
    run = ["--run", str(SCENE_SCRIPT)]
    if clutter == "walk":
        WALK_SCRIPT.write_text(f"import sys\nsys.path.insert(0, {str(REPO)!r})\n"
                               "from soundstage.blender import occlusion\nocclusion.BY_INSTANCER = False\n")
        run += ["--run", str(WALK_SCRIPT)]
    r = timed(soundstage_cmd() + ["bake", str(EMPTY), *run, "--out", str(out), *BAKE_ARGS], env=env)
    if clutter:
        shutil.rmtree(out, ignore_errors=True)
    for line in r["output"].splitlines():
        if "e18 built_at" in line:
            r["bake_s"] = round(r["end"] - float(line.split()[-1]), 2)
        elif "visibility:" in line and " in " in line:
            r["visibility_s"] = float(line.split(" in ")[1].split()[0])
            if "moving the occluders" in line:
                r["vis_ms"] = float(line.split("(")[1].split()[0])
                r["update_ms"] = float(line.split(", ")[1].split()[0])
        elif line.startswith("occluders:") or " occluders: " in line:
            r["static_occluders"] = int(line.split("occluders:")[1].split()[0])
        elif "level of detail: direct path only for" in line:
            r["direct_pct"] = float(line.split(" for ")[1].split()[0])
    return r


def ref_wav(n: int, unpitched: bool = False) -> Path:
    return OUT / "ref" / (f"cars_{n}_unpitched.wav" if unpitched else f"cars_{n}.wav")


def bands(x: np.ndarray, rate: int) -> tuple[np.ndarray, np.ndarray]:
    """Power per 0.4 s block and 1/3-octave band (50 Hz .. 16 kHz), (blocks, bands, channels)."""
    w = int(WINDOW_S * rate)
    m = len(x) // w
    spec = np.abs(np.fft.rfft(x[:m * w].reshape(m, w, x.shape[1]) * np.hanning(w)[None, :, None], axis=1)) ** 2
    f = np.fft.rfftfreq(w, 1.0 / rate)
    edges = 50.0 * 2.0 ** (np.arange(0, 25) / 3.0)  # 50 Hz .. 12.7 kHz lower edges, 25 bands to 16 kHz
    idx = np.searchsorted(edges, f) - 1
    ok = (idx >= 0) & (idx < len(edges) - 1)
    out = np.zeros((m, len(edges) - 1, x.shape[1]))
    for b in range(len(edges) - 1):
        out[:, b] = spec[:, ok & (idx == b)].sum(axis=1)
    return out, edges[:-1]


def compare(ref: Path, work: Path) -> dict:
    import soundfile as sf

    a, rate = sf.read(ref, dtype="float64")
    b, _ = sf.read(work, dtype="float64")
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    out = {}
    e, r = np.square(a - b).sum(axis=1), np.square(a).sum(axis=1)
    w = int(WINDOW_S * rate)
    m = n // w
    ew, rw = e[:m * w].reshape(m, w).sum(axis=1), r[:m * w].reshape(m, w).sum(axis=1)
    out["error_db"] = round(float(10 * np.log10(e.sum() / r.sum())), 1)
    out["error_window_db"] = round(float(10 * np.log10(np.max(ew / np.maximum(rw, 1e-30)))), 1)
    pa, _ = bands(a, rate)
    pb, _ = bands(b, rate)
    sa, sb = pa.sum(axis=2), pb.sum(axis=2)
    keep = sa > sa.max(axis=1, keepdims=True) * 10 ** (-FLOOR_DB / 10)
    level = 10 * np.log10(np.maximum(sb, 1e-30) / np.maximum(sa, 1e-30))[keep]
    out["band_level_median_db"] = round(float(np.median(level)), 2)
    out["band_level_p95_db"] = round(float(np.percentile(np.abs(level), 95)), 2)
    # median level difference per octave (three 1/3-octave bands each, 50 Hz .. 12.8 kHz): where a bias sits
    diff = 10 * np.log10(np.maximum(sb, 1e-30) / np.maximum(sa, 1e-30))
    out["octave_median_db"] = [round(float(np.median(diff[:, 3 * k:3 * k + 3][keep[:, 3 * k:3 * k + 3]])), 2)
                               if keep[:, 3 * k:3 * k + 3].any() else None for k in range(8)]
    # balance per octave band (three 1/3-octave bands each)
    oa, ob = pa[:, :24].reshape(len(pa), 8, 3, 2).sum(axis=2), pb[:, :24].reshape(len(pb), 8, 3, 2).sum(axis=2)
    ka = oa.sum(axis=2) > oa.sum(axis=2).max(axis=1, keepdims=True) * 10 ** (-FLOOR_DB / 10)
    bal_a = 10 * np.log10(np.maximum(oa[..., 1], 1e-30) / np.maximum(oa[..., 0], 1e-30))
    bal_b = 10 * np.log10(np.maximum(ob[..., 1], 1e-30) / np.maximum(ob[..., 0], 1e-30))
    out["balance_p95_db"] = round(float(np.percentile(np.abs(bal_b - bal_a)[ka], 95)), 2)
    lvl = 10 * np.log10(np.maximum(sb.sum(axis=1), 1e-30) / np.maximum(sa.sum(axis=1), 1e-30))
    out["block_level_p95_db"] = round(float(np.percentile(np.abs(lvl), 95)), 2)
    return out


def run_render(case: dict) -> dict:
    scene = scene_dir(case["n"], case["detail"] == "direct") / "scene.json"
    if not scene.exists():
        return {"exit": -1, "output": f"missing scene {scene}", "wall_s": None}
    work = OUT / "work" / f"render_{socket.gethostname()}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    env = {**os.environ, "PYTHONPATH": f"{REPO}{os.pathsep}{os.environ.get('PYTHONPATH', '')}"}
    detail = case["detail"]
    unpitched = detail.startswith("unpitched")
    if detail == "phase" or unpitched:  # the same scene with renamed sources (other random loop phases) or pitch 1
        manifest = json.loads(scene.read_text())
        for src in manifest["sources"]:
            if unpitched:
                src["pitch"] = 1.0
            else:
                src["id"] = f"{src['id']}~"
        manifest["arrays"] = str(scene.parent / manifest.get("arrays", "scene.npz"))
        scene = work / "scene.json"
        scene.write_text(json.dumps(manifest))
        detail = detail.split("-")[1] if unpitched else "null"
    elif detail == "direct":
        detail = "64"
    r = timed([sys.executable, "-c", WRAPPER, "render", str(scene), "-o", str(work / "mix.wav"),
               "--set", f"detail_voices={detail}"], env=env)
    for line in r["output"].splitlines():
        if line.startswith("[e18] result"):
            res = json.loads(line.split("result ", 1)[1])
            r["setup_s"], r["dsp_s"] = res["timing"]["load"], res["timing"]["dsp"]
            r["lod"], r["culling"] = res["lod"], res["culling"]
    if r["exit"] == 0:
        ref = ref_wav(case["n"], unpitched)
        if case["detail"].endswith("null"):
            ref.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(work / "mix.wav", ref)
        elif ref.exists():
            r.update(compare(ref, work / "mix.wav"))
    shutil.rmtree(work, ignore_errors=True)
    return r


def done() -> set[str]:
    if not RESULTS.exists():
        return set()
    return {r["key"] for r in map(json.loads, RESULTS.read_text().splitlines()) if r.get("exit") == 0}


def cmd_run(a: argparse.Namespace) -> None:
    import subprocess

    OUT.mkdir(parents=True, exist_ok=True)
    if not EMPTY.exists():
        EMPTY.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["blender", "-b", "--factory-startup", "--python-expr",
                        f"import bpy; bpy.ops.wm.read_factory_settings(use_empty=True); "
                        f"bpy.ops.wm.save_as_mainfile(filepath={str(EMPTY)!r})"], check=True, capture_output=True)
    cases = bake_cases() if a.stage == "bake" else render_cases()
    if a.sizes:
        cases = [c for c in cases if c["n"] in a.sizes]
    if a.reverse:
        refs = [c for c in cases if c.get("detail", "").endswith("null")]
        cases = refs + [c for c in reversed(cases) if c not in refs]
    def again(key: str) -> bool:
        return any(fnmatch.fnmatchcase(key, pat) for pat in a.again or [])

    todo = [c for c in cases if c["key"] not in done() or again(c["key"])]
    host = socket.gethostname()
    for k, c in enumerate(todo):
        if c["key"] in done() and not again(c["key"]):
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


def load() -> list[dict]:
    if not RESULTS.exists():
        return []
    rows = {}
    for r in map(json.loads, RESULTS.read_text().splitlines()):
        if r.get("exit") == 0:
            rows[r["key"]] = r
    return list(rows.values())


FIT_HZ = (3200.0, 6400.0, 9000.0)
FIT_M = (141.0, 283.0, 566.0, 1131.0)


def air_fits() -> list[tuple[float, list[tuple[float, float, float]]]]:
    """Loss of the air-absorption cascades at the far field's rate and the full chain's (2x), and ISO."""
    from soundstage.engine import filters

    f = np.array(FIT_HZ)
    iso = filters.iso9613_alpha(f, 20.0, 50.0)

    def loss(rate: int, d: float) -> np.ndarray:
        cut = filters.AirAbsorption(20.0, 50.0, rate).cutoffs(np.array([d]))[0]
        t = np.tan(np.pi * f / rate)
        return -sum(10 * np.log10(1 + (t / np.tan(np.pi * min(c, 0.49 * rate) / rate)) ** 2)
                    for c in cut if np.isfinite(c))

    return [(d, list(zip(-iso * d, loss(48000, d), loss(96000, d)))) for d in FIT_M]


def fmt(x, digits: int = 1) -> str:
    return "" if x is None else f"{x:.{digits}f}"


def cmd_analyse(a: argparse.Namespace) -> None:
    rows = load()
    # visibility samples of a 60 s bake: every VIS_STEP-th of (60 + 2 pad) s x 30 fps x substeps, from the first
    samples = (60 + 2 * int(BAKE_ARGS[3])) * 30 * int(BAKE_ARGS[1]) + 1
    vis_samples = len(range(0, samples, VIS_STEP))
    lines = ["## bake", "", f"60 s shot, {vis_samples} visibility samples.", "",
             "| cars | visibility paths | bake (s) | per car (s) | of which visibility (s) | "
             "visibility per car and sample (ms) | share of the bake | direct path only | memory (GB) |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in sorted((r for r in rows if r["stage"] == "bake" and not r.get("clutter")),
                    key=lambda r: (r["n"], r.get("direct", False))):
        vis = r.get("visibility_s")
        lines.append(f"| {r['n']} | {'far: direct' if r.get('direct') else 'all'} | {fmt(r.get('bake_s'), 0)} | "
                     f"{fmt(r.get('bake_s') and r['bake_s'] / r['n'], 2)} | {fmt(vis, 0)} | {fmt(vis and 1000 * vis / (vis_samples * r['n']), 3)} | "
                     f"{fmt(vis and 100 * vis / r['bake_s'], 0)} % | "
                     f"{fmt(r.get('direct_pct'), 0) + ' %' if r.get('direct') else ''} | "
                     f"{r['maxrss_mb'] / 1024:.1f} |")
    lines += ["", "## moving occluders (clutter)", "",
              "| placed by | static occluders | visibility per sample (ms) | of which moving the occluders (ms) | "
              "bake (s) |", "|---|---|---|---|---|"]
    for r in sorted((r for r in rows if r.get("clutter")), key=lambda r: r["clutter"]):
        lines.append(f"| {r['clutter']} | {r.get('static_occluders', '')} | {fmt(r.get('vis_ms'), 0)} | "
                     f"{fmt(r.get('update_ms'), 0)} | {fmt(r.get('bake_s'), 0)} |")
    lines += ["", "## render", "",
              "| cars | detail_voices | render (s) | setup / audio (s) | memory (GB) | far share | near voices (max) | "
              "error (dB) | worst 0.4 s (dB) | band level median / p95 (dB) | balance p95 (dB) | block level p95 (dB) |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    order = {label(d): k for k, d in enumerate(DETAIL)} | {"phase": -1, "direct": len(DETAIL),
                                                           "unpitched-null": len(DETAIL) + 1,
                                                           "unpitched-64": len(DETAIL) + 2}
    for r in sorted((r for r in rows if r["stage"] == "render"), key=lambda r: (r["n"], order[r["detail"]])):
        lod = r.get("lod") or {}
        lines.append(
            f"| {r['n']} | {r['detail']} | {fmt(r['wall_s'], 0)} | {fmt(r.get('setup_s'), 0)} / {fmt(r.get('dsp_s'), 0)} | "
            f"{r['maxrss_mb'] / 1024:.1f} | {fmt(100 * lod['far_share'], 0) + ' %' if lod else ''} | "
            f"{lod.get('near_voices_max', '')} | {fmt(r.get('error_db'))} | {fmt(r.get('error_window_db'))} | "
            f"{fmt(r.get('band_level_median_db'), 2)} / {fmt(r.get('band_level_p95_db'), 2)} | "
            f"{fmt(r.get('balance_p95_db'), 2)} | {fmt(r.get('block_level_p95_db'), 2)} |")
    with_oct = [r for r in rows if r["stage"] == "render" and r.get("octave_median_db")]
    lines += ["", "## median band level difference per octave (dB)", "",
              "| cars | detail_voices | " + " | ".join(f"{50 * 2 ** k:g} Hz" for k in range(8)) + " |",
              "|---|---|" + "---|" * 8]
    for r in sorted(with_oct, key=lambda r: (r["n"], order[r["detail"]])):
        lines.append(f"| {r['n']} | {r['detail']} | " + " | ".join(fmt(v, 2) for v in r["octave_median_db"]) + " |")
    lines += ["", "## air absorption fits: far field (48 kHz) and full chain (96 kHz) against ISO 9613-1 (dB)", "",
              "20 degC, 50 % humidity; the fits follow ISO where its loss is below 20 dB.", "",
              "| distance (m) | " + " | ".join(f"{f / 1000:g} kHz ISO / 48k / 96k" for f in FIT_HZ) + " |",
              "|---|" + "---|" * len(FIT_HZ)]
    for d, row in air_fits():
        lines.append(f"| {d:g} | " + " | ".join(f"{a:.1f} / {b:.1f} / {c:.1f}" for a, b, c in row) + " |")
    lines += ["", "## render memory against near voices", "",
              "Least squares over detail_voices 16-128: peak memory (render time) = base + per voice x near "
              "voices (max).", "",
              "| cars | base (GB) | per near voice (MB) | base (s) | per near voice (s) |", "|---|---|---|---|---|"]
    for n in CARS:
        pts = [(r["lod"]["near_voices_max"], r["maxrss_mb"], r["wall_s"]) for r in rows
               if r["stage"] == "render" and r["n"] == n and r["detail"] in {label(d) for d in DETAIL[1:]}]
        if len(pts) > 1:
            v, mb, sec = np.array(pts, dtype=float).T
            slope, base = np.polyfit(v, mb, 1)
            tslope, tbase = np.polyfit(v, sec, 1)
            lines.append(f"| {n} | {base / 1024:.1f} | {slope:.0f} | {tbase:.0f} | {tslope:.2f} |")
    text = "\n".join(lines)
    print(text)
    (OUT / "analysis.md").write_text(text + "\n")
    if a.figures:
        figures(rows, Path(a.figures))


def figures(rows: list[dict], where: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    where.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(17, 4.6))
    for k, d in enumerate(DETAIL):
        pts = sorted((r["n"], r["wall_s"], r["maxrss_mb"] / 1024) for r in rows
                     if r["stage"] == "render" and r["detail"] == label(d))
        if not pts:
            continue
        n, t, m = zip(*pts)
        name = "every car near (null)" if d is None else f"detail_voices {d}"
        style = dict(color="k" if d is None else f"C{k}", marker="o", label=name)
        axes[0].plot(n, t, **style)
        axes[1].plot(n, m, **style)
    ax = axes[2]
    shades = ["0.65", "0.4", "0.0"]  # grey to black with the number of cars (the colours are detail_voices)
    for k, n in enumerate(c for c in CARS if c <= REFERENCE_MAX):
        pts = sorted((int(r["detail"]), r["band_level_p95_db"]) for r in rows
                     if r["stage"] == "render" and r["n"] == n and r["detail"].isdigit() and "band_level_p95_db" in r)
        if pts:
            ax.plot(*zip(*pts), marker="o", color=shades[k], label=f"{n} cars: far field")
        phase = [r["band_level_p95_db"] for r in rows if r["stage"] == "render" and r["n"] == n
                 and r["detail"] == "phase" and "band_level_p95_db" in r]
        if phase:
            ax.axhline(phase[0], color=shades[k], ls="--", lw=1, label=f"{n} cars: other loop phases")
        flat = [r["band_level_p95_db"] for r in rows if r["stage"] == "render" and r["n"] == n
                and r["detail"] == "unpitched-64" and "band_level_p95_db" in r]
        if flat:
            ax.plot([64], flat, marker="s", ls="none", color=shades[k], mfc="white", label=f"{n} cars: pitch 1, 64")
    ax.set_xscale("log", base=2)
    ax.set_xticks(DETAIL[1:], [str(d) for d in DETAIL[1:]])
    ax.set_xlabel("detail_voices")
    ax.set_ylabel("1/3-octave band level difference, p95 (dB)")
    ax.set_ylim(bottom=0)
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(fontsize=7)
    for ax, ylabel in ((axes[0], "render time (s), 60 s shot"), (axes[1], "peak memory (GB)")):
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("cars")
        ax.set_ylabel(ylabel)
        ax.grid(True, which="both", alpha=0.3)
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(where / "e18_scaling.png", dpi=110)
    plt.close(fig)
    print(f"figure: {where / 'e18_scaling.png'}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("stage", choices=["bake", "render"])
    r.add_argument("--sizes", nargs="+", type=int, help="numbers of cars")
    r.add_argument("--reverse", action="store_true", help="last case first (a second machine on the same list)")
    r.add_argument("--again", nargs="+", metavar="PATTERN",
                   help="run the cases matching these keys or patterns again (the newest result counts)")
    an = sub.add_parser("analyse")
    an.add_argument("--figures")
    ls = sub.add_parser("list")
    ls.add_argument("stage", choices=["bake", "render"])
    a = p.parse_args()
    {"run": cmd_run, "analyse": cmd_analyse, "list": cmd_list}[a.cmd](a)


if __name__ == "__main__":
    main()
