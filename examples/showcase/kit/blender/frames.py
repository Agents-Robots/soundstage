"""Render frames of a section's .blend for checking and previews (run inside Blender).

    blender -b <key>.blend -y --python examples/showcase/kit/blender/frames.py -- \
        --out DIR [--frames 1,60,331 | --step 1] [--first N] [--last N] [--percent 33] [--samples 16]

With ``--step`` the range's last frame is rendered too.

Cycles on the CPU; the farm renders the final frames from the same .blend at 100 %.
"""

import argparse
import sys
from pathlib import Path

import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
p = argparse.ArgumentParser()
p.add_argument("--out", required=True)
p.add_argument("--frames", default="", help="comma-separated frames (default: every --step-th frame)")
p.add_argument("--step", type=int, default=1)
p.add_argument("--first", type=int, default=0)
p.add_argument("--last", type=int, default=0)
p.add_argument("--percent", type=int, default=33)
p.add_argument("--samples", type=int, default=16)
a = p.parse_args(argv)

scene = bpy.context.scene
scene.render.resolution_percentage = a.percent
scene.cycles.samples = a.samples
scene.cycles.device = "CPU"
scene.render.use_persistent_data = True
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)
if a.frames:
    frames = [int(f) for f in a.frames.split(",")]
else:
    last = a.last or scene.frame_end
    frames = list(range(a.first or scene.frame_start, last + 1, a.step))
    if frames[-1] != last:  # the last frame always, so that a stepped preview ends where the section does
        frames.append(last)
for f in frames:
    scene.frame_set(f)
    scene.render.filepath = str(out / f"{f:05d}.png")
    bpy.ops.render.render(write_still=True)
    print(f"frame {f}", flush=True)
