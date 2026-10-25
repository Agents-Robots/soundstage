"""E10: render time (NFR-3) for synthetic shots of growing size, single-threaded and parallel.

Uses tools/benchmark.py's scene (moving camera, sources on repeated straight passes, one-shots),
default settings (standard quality, hybrid panner); the last case adds the Phase 3 processing
(varying occlusion on every source, the hangar reverb, stems). Prints the timing table.
"""

import os
import sys
import tempfile
import time
from pathlib import Path

from common import REPO, table

sys.path.insert(0, str(REPO / "tools"))
import benchmark  # noqa: E402

from soundstage.engine import render  # noqa: E402
from soundstage.engine.scene import load_scene  # noqa: E402


def main() -> None:
    rows = []
    cores = os.cpu_count()
    cases = ((10, 1, 1, False), (10, 1, cores, False), (50, 1, 1, False), (50, 1, cores, False),
             (50, 5, cores, False), (50, 5, cores, True))
    for sources, minutes, workers, phase3 in cases:
        with tempfile.TemporaryDirectory() as tmp:
            scene = load_scene(benchmark.build(Path(tmp), sources, minutes, occlusion=phase3),
                               {"reverb": "hangar"} if phase3 else None)
            t0 = time.perf_counter()
            result = render.render(scene, workers=workers, stems=phase3)
            seconds = time.perf_counter() - t0
        audio = len(result.audio) / result.rate
        rows.append([sources, f"{minutes} min" + (" + occlusion, reverb, stems" if phase3 else ""),
                     result.timing_s["workers"], f"{seconds:.1f} s",
                     f"{result.timing_s['load']:.1f} s", f"{result.timing_s['dsp']:.1f} s", f"{audio / seconds:.1f}×"])
        print(rows[-1], flush=True)
    print(f"\n{cores} logical cores\n")
    print(table(["sources", "length", "workers", "render", "of which setup", "of which audio", "real time"], rows))


if __name__ == "__main__":
    main()
