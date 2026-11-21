"""Known answers of ``city`` (README.md): the sources the instances give, the Doppler shift of one
car passing the camera among all the others (a 1 kHz probe on it), the far field and the render time
that the callout states.

    .venv/bin/python examples/showcase/sections/city/check.py [--dir out/showcase/city]
"""

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1]), str(HERE)]

import numpy as np  # noqa: E402
from kit import measure, story  # noqa: E402
from kit.checks import C, Check  # noqa: E402
from section import CARS, LANES, PASS_S, RENDER_CLAIM_MIN, SOURCES, drone  # noqa: E402

PROBE_WINDOWS = ((22.5, 23.5), (24.0, 25.0), (27.6, 28.5))
"""Seconds into the pass: approaching from afar, approaching close, going away (the probe ends at
29 s)."""


def run(c: Check) -> None:
    rate = c.rate
    man = json.loads((c.dir / "bake" / "scene.json").read_text())
    ids = [s["id"] for s in man["sources"]]
    cars = sum(1 for i in ids if i.startswith("city.night."))
    instancers = len({i.split("/")[0] for i in ids if i.startswith("city.night.")})
    c.expect("sources in the bake (cars, sources)", f"{instancers}, {cars}", f"{CARS}, {SOURCES}",
             (instancers, cars) == (CARS, SOURCES))
    dropped = [w for w in man["warnings"] if "instances of tagged object" in w]
    c.expect("bake: no instances dropped (instance_limit=0)", dropped or "none", "none", not dropped)
    # the bake's padding warning counts sound heard from frame 1, the silent title page; the pass starts
    # on its first frame, so the padding has to reach back the farthest car's travel time from there
    first = c.windows["night"][0]
    k = int(np.argmin(np.abs(c.geo.frames - first)))
    travel = float(np.nanmax(np.linalg.norm(c.geo.src[k] - c.geo.lis[k], axis=1))) / C
    need = travel - (first - 1) / story.FPS
    pad = man["settings"]["pad_seconds"]
    c.expect("bake: padding covers the farthest car heard at the pass's first frame",
             f"needs {need:.2f} s (travel {travel:.2f} s, title page 3 s)", f"at most {pad:g} s", need <= pad)

    # one car among 10 000: its Doppler shift as the geometry gives it
    probe = next(i for i in ids if i.startswith("city.probe.night."))
    x = measure.mono(c.probe("night").audio)
    for a, b in PROBE_WINDOWS:
        got = measure.frequency(x[int(a * rate):int(b * rate)], rate, 1000)
        want = 1000 * c.geo.rate(probe, c.frame("night", (a + b) / 2))
        c.near(f"probe car at {a:g}-{b:g} s: frequency", got, want, max(1.0, 0.002 * want), "Hz", 1)

    rep = c.pass_report("night")
    far = rep.get("far_field") or {}
    c.expect("sources in the far field (reported)", f"{far.get('far_sources')} of {len(rep['sources'])}, "
             f"near voices at once up to {far.get('near_voices_max')}", "above zero", (far.get("far_sources") or 0) > 0)
    # the report's rate is the Doppler factor (the pitch is not in it), bounded by the drone's top
    # speed and the fastest car's
    doppler = [r for s in rep["sources"] for r in (s.get("rate") or [])]
    v_cam = max(math.dist(drone(t / 10), drone(t / 10 + 0.1)) / 0.1 for t in range(int(PASS_S * 10)))
    v_car = max(v for *_, (_, v), _ in LANES.values()) / 3.6
    lo, hi = (C - v_cam) / (C + v_car), (C + v_cam) / (C - v_car)
    c.expect(f"playback rates (camera up to {v_cam:.0f} m/s, cars up to {v_car:.0f} m/s)",
             f"{min(doppler):.3f} to {max(doppler):.3f}", f"within {lo:.3f} to {hi:.3f}",
             lo <= min(doppler) and max(doppler) <= hi)
    clamps = [w for w in rep["warnings"] if "clamp" in w]
    c.expect("no playback-rate clamp warning", clamps or "none", "none", not clamps)
    summary = json.loads((c.dir / "city.report.json").read_text())
    row = next(r for r in summary["passes"] if r["pass"] == "night")
    machine = summary.get("machine") or {}
    c.expect(f"render time of the pass ({PASS_S:g} s) on one 16-core CPU: the callout's claim (R7)",
             f"{row['render_seconds']:.0f} s, {machine.get('cpu')}, {machine.get('threads')} threads",
             f"under {RENDER_CLAIM_MIN * 60} s on 16 cores / 32 threads",
             row["render_seconds"] < RENDER_CLAIM_MIN * 60 and machine.get("threads") == 32)
    c.expect("peak memory (reported)", f"{row['peak_rss_mb']} MB", "reported", True)


if __name__ == "__main__":
    Check.main(run, "city")
