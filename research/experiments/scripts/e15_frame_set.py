"""E15 diagnostic: cost of ``scene.frame_set`` against the number of static objects. Needs Blender.

The bake steps through every sub-frame with ``frame_set``; E15 found a fixed bake cost that grows
with the number of objects in the scene although none of them moves. This builds the E15 city
(``e15_scene.py``, one source) for several building counts and times ``frame_set`` alone, with
and without a subframe, and the depsgraph lookup the bake does after it.
"""

import json
import os
import subprocess
from pathlib import Path

from common import REPO, table

SCENE = Path(__file__).with_name("e15_scene.py")
BLENDER = r'''
import bpy, json, time, os
s = bpy.context.scene
res = {}
for label, sub in (("frame_set", 0.0), ("frame_set + subframe", 0.25)):
    t0 = time.perf_counter()
    for f in range(1, 201):
        s.frame_set(f, subframe=sub)
    res[label] = (time.perf_counter() - t0) / 200 * 1e3
t0 = time.perf_counter()
for f in range(1, 201):
    s.frame_set(f, subframe=0.25)
    dg = bpy.context.evaluated_depsgraph_get()
    s.camera.evaluated_get(dg).matrix_world.copy()
res["frame_set + depsgraph + camera"] = (time.perf_counter() - t0) / 200 * 1e3
res["objects"] = len(s.objects)
print("E15RESULT " + json.dumps(res), flush=True)
'''


def main() -> None:
    rows = []
    for buildings in (0, 200, 800, 3200):
        env = {**os.environ, "E15_SOURCES": "1", "E15_BUILDINGS": str(buildings), "E15_SECONDS": "10"}
        p = subprocess.run(["blender", "-b", "--factory-startup", "-y", "--python", str(SCENE),
                            "--python-expr", BLENDER], env=env, capture_output=True, text=True, cwd=REPO)
        line = next(x for x in p.stdout.splitlines() if x.startswith("E15RESULT"))
        r = json.loads(line.split(" ", 1)[1])
        rows.append([buildings, r["objects"], f"{r['frame_set']:.2f}", f"{r['frame_set + subframe']:.2f}",
                     f"{r['frame_set + depsgraph + camera']:.2f}"])
        print(rows[-1], flush=True)
    print(table(["buildings", "objects", "frame_set (ms)", "with subframe (ms)", "+ depsgraph, camera (ms)"], rows))


if __name__ == "__main__":
    main()
