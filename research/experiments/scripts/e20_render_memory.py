"""E20: memory a near voice holds, by attribute, and a render's peak (issue #32).

The E18 scene with 1000 cars (baked by e18_traffic.py), the first 30 s, ``detail_voices`` 128,
16 workers. While it renders, every ``SpatialRenderer`` built is recorded; the bytes of the numpy
arrays it holds are summed per attribute (views of other arrays not counted twice). tracemalloc
gives the traced peak and the traced memory at the far field's busiest call (the most near voices
alive), the process its peak RSS.

    python e20_render_memory.py [--checkout DIR]     # prints a JSON line; DIR: render with that checkout
"""

from __future__ import annotations

import argparse
import collections
import json
import resource
import subprocess
import sys
import tracemalloc
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
SCENE = REPO / "out" / "e18" / "scenes" / "cars_1000" / "scene.json"


def nbytes(x, seen: set) -> int:
    if id(x) in seen:
        return 0
    seen.add(id(x))
    if isinstance(x, np.ndarray):
        return x.nbytes if x.base is None else 0
    if isinstance(x, (list, tuple)):
        return sum(nbytes(v, seen) for v in x)
    if isinstance(x, dict):
        return sum(nbytes(v, seen) for v in x.values())
    if hasattr(x, "__dict__") and type(x).__module__.startswith("soundstage"):
        return sum(nbytes(v, seen) for v in vars(x).values())
    return 0


def measure() -> dict:
    from soundstage.engine import farfield, render, source
    from soundstage.engine.scene import load_scene

    made, busiest = [], {"traced": 0}
    init = source.SpatialRenderer.__init__

    def record(self, *a, **k):
        init(self, *a, **k)
        made.append(self)

    source.SpatialRenderer.__init__ = record
    far_render = farfield.FarField.render

    def watch(self, *a, **k):
        out = far_render(self, *a, **k)
        busiest["traced"] = max(busiest["traced"], tracemalloc.get_traced_memory()[0])
        return out

    farfield.FarField.render = watch
    tracemalloc.start()
    sc = load_scene(SCENE)
    sc.settings["detail_voices"] = 128
    res = render.render(sc, frames=(1, 900), workers=16)
    peak = tracemalloc.get_traced_memory()[1]
    per = collections.Counter()
    for r in made:
        seen: set = set()
        for k, v in vars(r).items():
            per[k] += nbytes(v, seen)
    n = max(len(made), 1)
    return {"renderers": len(made), "near_voices_max": res.lod["near_voices_max"],
            "held_mb": round(sum(per.values()) / n / 1e6, 2),
            "by_attribute_mb": {k: round(v / n / 1e6, 2) for k, v in per.most_common(6)},
            "traced_peak_gb": round(peak / 1e9, 2), "traced_busiest_gb": round(busiest["traced"] / 1e9, 2),
            "maxrss_gb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6, 2)}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--checkout", help="render with this checkout instead of the repository's")
    p.add_argument("--inner", action="store_true", help=argparse.SUPPRESS)
    a = p.parse_args()
    if a.inner:
        print(json.dumps(measure()))
        return
    root = Path(a.checkout).resolve() if a.checkout else REPO
    me = str(Path(__file__).resolve())
    code = (f"import sys; sys.path.insert(0, {str(root)!r}); sys.argv = ['e20', '--inner']; "
            f"__file__ = {me!r}; exec(open(__file__).read())")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    print(json.dumps({"checkout": str(root), **json.loads(out.strip().splitlines()[-1])}))


if __name__ == "__main__":
    main()
