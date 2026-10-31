"""E19: the reverb send over distance (the revised law) and the far field's send.

1. The revised send law per preset: mid-frequency T60, the radius R = c T / ln(1000), and the send
   level at 10 m ... 3 km (EFX: 0 dB everywhere for these presets).
2. Sources spread evenly over a plane out to a radius D (traffic around a camera): the reverberant
   energy (sum of the send gains squared) and the direct energy (inverse distance, reference 8 m),
   relative to D = 100 m, for the EFX law (room rolloff 0), the EFX law with room rolloff 1, and the
   revised law (city_streets).
3. Renders of the E18 traffic scenes (cars on looping lanes in a canyon of towers, 60 s, baked by
   e18_traffic.py) with the city_streets reverb and the three send laws, at detail_voices 64: the
   loudness of the cars stem and of the reverb return, the share of the reverb send from cars beyond
   100 m and 1 km (from the baked distances), render time and memory.
4. The far field's send: the reverb return per octave band at detail_voices 64 against null (every
   car in the full chain), law efx (constant: the far cars send the most), 1000 cars. ``--checkout``
   renders with another checkout: the far field before its send had air absorption (c81a028).

    python e19_reverb_send.py run [--checkout DIR --tag before] [--again PATTERN ...]
    python e19_reverb_send.py analyse
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import math
import os
import shutil
import socket
import sys
import time
from pathlib import Path

import numpy as np
from e15_option_costs import timed

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
OUT = REPO / "out" / "e19"
RESULTS = OUT / "results.jsonl"
SCENES = REPO / "out" / "e18" / "scenes"
PRESETS = ("livingroom", "concerthall", "city_streets", "forest", "hangar", "mountains")
DISTANCES = (10.0, 30.0, 100.0, 300.0, 1000.0, 3000.0)
REVERB = "city_streets"
LAWS = {"efx": ["reverb_send_law=efx"], "efx-rolloff-1": ["reverb_send_law=efx", "reverb_room_rolloff=1"],
        "revised": ["reverb_send_law=revised"]}
OCTAVES = 1000.0 * 2.0 ** np.arange(-4, 5)  # 62.5 Hz ... 16 kHz
OCTAVE_NAMES = ("63", "125", "250", "500", "1k", "2k", "4k", "8k", "16k")

WRAPPER = (
    "import sys, json\n"
    "from soundstage import cli\n"
    "from soundstage.engine import render as R\n"
    "f = R.render\n"
    "def g(*a, **k):\n"
    "    r = f(*a, **k)\n"
    "    print('[e19] result ' + json.dumps({'timing': r.timing_s, 'lod': r.lod}), flush=True)\n"
    "    return r\n"
    "R.render = g\n"
    "sys.exit(cli.main(sys.argv[1:]))\n"
)


def cases(tag: str) -> list[dict]:
    out = []
    if tag == "after":
        for n in (2000, 10000):
            for law in LAWS:
                out.append({"n": n, "law": law, "detail": "64", "key": f"{tag}|{n}|{law}|64"})
    for detail in ("null", "64"):
        out.append({"n": 1000, "law": "efx", "detail": detail, "key": f"{tag}|1000|efx|{detail}"})
    return out


def run(case: dict, checkout: Path, tag: str) -> dict:
    scene = SCENES / f"cars_{case['n']}" / "scene.json"
    work = OUT / "work" / f"{tag}_{case['n']}_{case['law']}_{case['detail']}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    env = {**os.environ, "PYTHONPATH": f"{checkout}{os.pathsep}{os.environ.get('PYTHONPATH', '')}"}
    sets = [f"reverb={REVERB}", f"detail_voices={case['detail']}"]
    if tag == "after":
        sets += LAWS[case["law"]]  # the earlier checkout has the EFX law only
    r = timed([sys.executable, "-c", WRAPPER, "render", str(scene), "-o", str(work / "mix.wav"), "--stems",
               "--report", *(x for kv in sets for x in ("--set", kv))], env=env)
    for line in r["output"].splitlines():
        if line.startswith("[e19] result"):
            res = json.loads(line.split("result ", 1)[1])
            r["setup_s"], r["dsp_s"] = res["timing"]["load"], res["timing"]["dsp"]
    if r["exit"] == 0:
        rep = json.loads((work / "mix.report.json").read_text())
        r["master_lufs"] = rep["master"]["lufs_integrated"]
        r["cars_lufs"] = rep["groups"]["cars"]["lufs_integrated"]
        r["reverb_lufs"] = rep["groups"]["reverb"]["lufs_integrated"]
        r["reverb_octaves_db"] = octave_levels(work / "mix_stem_reverb.wav")
    shutil.rmtree(work, ignore_errors=True)
    return r


def octave_levels(path: Path) -> list[float]:
    """Level per octave band (dB, both channels) of a WAV."""
    import soundfile as sf

    x, rate = sf.read(path, dtype="float64")
    spec = np.abs(np.fft.rfft(x, axis=0)) ** 2
    f = np.fft.rfftfreq(len(x), 1.0 / rate)
    out = []
    for c in OCTAVES:
        sel = (f >= c / math.sqrt(2.0)) & (f < c * math.sqrt(2.0))
        out.append(round(float(10 * np.log10(spec[sel].sum() + 1e-30)), 2))
    return out


def done() -> set[str]:
    if not RESULTS.exists():
        return set()
    return {r["key"] for r in map(json.loads, RESULTS.read_text().splitlines()) if r.get("exit") == 0}


def cmd_run(a: argparse.Namespace) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    checkout = Path(a.checkout).resolve() if a.checkout else REPO
    host = socket.gethostname()
    for c in cases(a.tag):
        again = any(fnmatch.fnmatchcase(c["key"], p) for p in a.again or [])
        if c["key"] in done() and not again:
            continue
        r = run(c, checkout, a.tag)
        rec = c | {"tag": a.tag, "checkout": str(checkout), "host": host, "time": time.strftime("%Y-%m-%dT%H:%M:%S")}
        rec.update({k: v for k, v in r.items() if k not in ("output", "end")})
        if r["exit"] != 0:
            rec["tail"] = r["output"][-1500:]
        with RESULTS.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"{c['key']}: {r.get('wall_s')} s exit {r['exit']}", flush=True)


def send_shares(n: int, law) -> tuple[float, float]:
    """Share of the reverb send energy from cars beyond 100 m and 1 km over the shot (straight-line
    distance at each baked sample; every car's loop plays throughout)."""
    from soundstage.engine.filters import distance_gain
    from soundstage.engine.scene import load_scene

    sc = load_scene(SCENES / f"cars_{n}" / "scene.json")
    lpos = sc.listener_matrix[:, :3, 3]
    total = far100 = far1k = 0.0
    for src in sc.sources:
        p = src.params
        d = np.linalg.norm(sc.src_pos[:, src.track] - lpos, axis=1)
        g2 = (distance_gain(d, p["distance_model"], p["ref_distance"], p["max_distance"], law.room_rolloff)
              * law.factor(d)) ** 2 * 10 ** (p["gain_db"] / 10)
        total += g2.sum()
        far100 += g2[d > 100.0].sum()
        far1k += g2[d > 1000.0].sum()
    return far100 / total, far1k / total


def laws() -> dict:
    from soundstage.engine import reverb

    env = reverb.environment(REVERB, 48000)
    return {"efx": reverb.SendLaw(0.0), "efx-rolloff-1": reverb.SendLaw(1.0),
            "revised": reverb.send_law(env, "revised", None, 343.0)}


def plane(law, d_max: float, ref: float = 8.0) -> tuple[float, float]:
    """Reverberant and direct energy of sources spread evenly over a plane from 1 m to d_max (per
    unit density): integrals of 2 pi r g(r)^2 dr."""
    r = np.geomspace(1.0, d_max, 20000)
    w = 2 * np.pi * r * np.gradient(r)
    from soundstage.engine.filters import distance_gain

    send = distance_gain(r, "inverse_clamped", ref, None, law.room_rolloff) * law.factor(r)
    direct = distance_gain(r, "inverse_clamped", ref, None, 1.0)
    return float((w * send ** 2).sum()), float((w * direct ** 2).sum())


def load() -> list[dict]:
    rows = {}
    if RESULTS.exists():
        for r in map(json.loads, RESULTS.read_text().splitlines()):
            if r.get("exit") == 0:
                rows[r["key"]] = r
    return list(rows.values())


def table(header: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return "\n".join(out + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def cmd_analyse(a: argparse.Namespace) -> None:
    from soundstage.engine import reverb

    rows = []
    for name in PRESETS:
        env = reverb.environment(name, 48000)
        law = reverb.send_law(env, "revised", None, 343.0)
        rows.append([name, f"{env.decay_s:.2f}", f"{law.radius:.0f}",
                     *(f"{20 * np.log10(law.factor(np.array([d]))[0]):.1f}" for d in DISTANCES)])
    print("1. Revised send law: T60 (s), radius R (m) and send level (dB) by distance:\n")
    print(table(["preset", "T60", "R", *(f"{d:g} m" for d in DISTANCES)], rows))

    ls = laws()
    rows = []
    base = {k: plane(law, 100.0) for k, law in ls.items()}
    for d_max in (300.0, 1000.0, 3000.0, 10000.0):
        row = [f"{d_max:g} m"]
        for k, law in ls.items():
            rev, _ = plane(law, d_max)
            row.append(f"{10 * np.log10(rev / base[k][0]):+.1f}")
        _, direct = plane(ls["efx"], d_max)
        row.append(f"{10 * np.log10(direct / base['efx'][1]):+.1f}")
        rows.append(row)
    print(f"\n2. Sources spread evenly over a plane out to D: reverberant energy relative to D = 100 m, per send "
          f"law ({REVERB}), and the direct energy (inverse distance) (dB):\n")
    print(table(["D", *ls, "direct"], rows))

    res = {r["key"]: r for r in load()}
    rows = []
    for n in (2000, 10000):
        for law in LAWS:
            r = res.get(f"after|{n}|{law}|64")
            if not r:
                continue
            s100, s1k = send_shares(n, ls[law])
            rows.append([n, law, r["cars_lufs"], r["reverb_lufs"], f"{r['cars_lufs'] - r['reverb_lufs']:.1f}",
                         r["master_lufs"], f"{100 * s100:.0f}", f"{100 * s1k:.0f}", f"{r['wall_s']:.0f}",
                         f"{r['maxrss_mb'] / 1024:.1f}"])
    print(f"\n3. E18 traffic, {REVERB}, detail_voices 64: loudness (LUFS) of the cars stem and the reverb return, "
          f"their difference, the master, the share of the reverb send from cars beyond 100 m and 1 km (%), "
          f"render time (s) and peak memory (GB):\n")
    print(table(["cars", "law", "cars", "reverb", "cars - reverb", "master", "> 100 m", "> 1 km", "time", "GB"], rows))

    rows = []
    for tag in ("before", "after"):
        full, far = res.get(f"{tag}|1000|efx|null"), res.get(f"{tag}|1000|efx|64")
        if full and far:
            ref = np.array(full["reverb_octaves_db"])
            if tag == "after":
                rows.append(["level of the full chain's return", *(f"{x:.0f}" for x in ref - ref.max()), ""])
            diff = np.array(far["reverb_octaves_db"]) - ref
            rows.append([tag, *(f"{x:+.1f}" for x in diff), f"{far['wall_s']:.0f}"])
    print("\n4. Reverb return per octave band, detail_voices 64 minus null (every car in the full chain), "
          "1000 cars, law efx (dB), and the render time at 64 (s); the first row: the full chain's level "
          "per octave against its loudest:\n")
    print(table(["far field", *(f"{c} Hz" for c in OCTAVE_NAMES), "time"], rows))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--checkout", help="render with this checkout (PYTHONPATH)")
    r.add_argument("--tag", default="after", choices=["before", "after"])
    r.add_argument("--again", nargs="+", metavar="PATTERN", help="rerun the cases whose key matches (fnmatch)")
    sub.add_parser("analyse")
    a = p.parse_args()
    {"run": cmd_run, "analyse": cmd_analyse}[a.cmd](a)


if __name__ == "__main__":
    main()
