# examples

Script-built example scenes and tagging scripts.

| File | What it is |
|---|---|
| `flyby.py` | Builds the flyby scene from scratch: a camera dollies forward, a ship passes left to right at 30 m/s, a beacon on the left, a crate falls and lands at frame 180. 30 fps, frames 1-240. |
| `flyby_sounds.py` | Tags for the flyby scene, applied at bake time with `--run` (the pattern for existing animations). |
| `sounds_template.py` | Template tagging script to copy next to your own animation ([agent guide](../docs/agent-guide.md)). |

```bash
blender -b --factory-startup --python examples/flyby.py -- --save out/flyby.blend
.venv/bin/soundstage bake out/flyby.blend --run examples/flyby_sounds.py --out out/flyby
.venv/bin/soundstage render out/flyby/scene.json -o out/flyby/mix.wav --report
```

Planned:

- `station_interior.py`: ambience bed, machinery loops with cones, doors as one-shots, occlusion
  by walls.
- `fleet.py`: many engines at distance, Doppler and air absorption, camera cuts.
