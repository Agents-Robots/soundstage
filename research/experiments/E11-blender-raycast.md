# E11: ray casting in Blender for the visibility bake (Phase 3)

**Question.** Which ray-casting method can the bake afford for visibility (25 rays per source and
sample, at 10 Hz, over shots of minutes, in scenes with tens of thousands of objects)?

## Setup

`e11_blender_raycast.py` builds a synthetic city in headless Blender: a grid of buildings (four
box meshes subdivided to 3072 triangles each, 30 m apart), placed either as geometry-nodes instances
of an asset collection or as separate objects sharing the meshes, plus one moving car per street.
It measures:

- `scene.ray_cast` per ray (50 random street-level rays across the city);
- the bake's occluders (`occlusion.Occluders`): building the box BVH from three frames, and the cost
  per ray (20 000 rays);
- a BVH over the real triangles, built for 200 instances and extrapolated (time and memory);
- one visibility sample of the bake for 50 sources (25 paths each).

Synthetic city on an unloaded compute node (AMD Ryzen 9 3950X, 16 cores, as in [E10](E10-performance.md)); Blender 5.2.2.

## Results

**Synthetic city** (per ray; the triangle BVH extrapolated from 200 instances; visibility = one
bake sample for 50 sources):

| scene | triangles | `scene.ray_cast` | blocked: ray_cast / boxes | boxes (static + moving) | box BVH | triangle BVH (extrapolated) | visibility |
|---|---|---|---|---|---|---|---|
| 1600 buildings (GN instances) + 40 cars | 5 M | 0.3 ms | 98 / 98 % | 1600 + 40 in 0.23 s | 4.9 µs | 7 s, 1.3 GB | 20 ms |
| 10000 buildings (GN instances) + 100 cars | 31 M | 1.6 ms | 100 / 100 % | 10000 + 100 in 1.48 s | 5.5 µs | 45 s, 7.4 GB | 23 ms |
| 1600 buildings (objects) + 40 cars | 5 M | 0.4 ms | 98 / 98 % | 1600 + 40 in 0.24 s | 5.0 µs | 7 s, 1.3 GB | 21 ms |
| 10000 buildings (objects) + 100 cars | 31 M | 6.0 ms | 100 / 100 % | 10000 + 100 in 1.47 s | 5.3 µs | 49 s, 8.0 GB | 23 ms |

- `scene.ray_cast` sees geometry-nodes instances (its blocked share equals the boxes' on these box
  buildings) and costs about 0.6 µs per object per ray: 6 ms with 10 000 objects. A bake sample
  with 50 sources (1250 rays) would take 7.5 s.
- The box BVH costs about 5 µs per ray regardless of the scene size, 60× to 1200× less.
- A BVH over the real triangles needs about 250 bytes per triangle in Blender's Python API; at
  31 million triangles that is 8 GB, and real scenes with detailed instanced assets reach billions
  of triangles.

**Real scene**: a user's 120 s drone shot over a procedurally built city (23 782 objects, 43 349 mesh
instances, 4.0 billion instanced triangles, 178 sources of which 174 spatial), baked with one
sub-frame per frame and 7 s padding (4020 samples, visibility at 10 Hz: 1340 samples) on a compute
node:

| | bake | peak memory |
|---|---|---|
| without visibility (`occlusion_rate = 0`) | 585 s | 7.2 GB |
| with visibility | 961 s | 7.4 GB |

With visibility: 111 180 static and 7002 moving boxes (9 objects that travel with the listener left
out), set up in 47 s; 244 ms per visibility sample for 174 sources, 327 s in all. `scene.ray_cast` (probe on the workstation): 0.55 s for the first ray, which builds every
object's BVH, then 44 ms per ray, so one visibility sample of this shot would take 2 minutes.
Of the 174 spatial sources, 64 are occluded for more than half of the shot (the median source for
42 % of it), mostly cars and lights 1–2 km away behind the city's towers; 15 are occluded
throughout, mostly sound points on a river at the bottom of a canal between old-town buildings.
Whether these are right needs the picture and the user's ears; the bake lists the objects that
block each source (`soundstage inspect`). On this shot the list points at the old town's buildings
(one merged mesh) for the market and searchlight sources, at the bridge decks for the walkers on
them, and at the city's ground-floor slab for the river points: a box has no hole, so if the canal is
cut into that slab, `sfx_occluder = "mesh"` on it opens the canal.

**What the real scene showed.** The synthetic tests passed from the start; the first bakes of the
real shot did not hold up, and each finding below was fixed with a test:

| Finding | Effect | Fix |
|---|---|---|
| Objects created by the shot's tagging script were missing from `view_layer.objects` (synced lazily) | 67 of 178 sources not baked | view-layer membership from the layer collections |
| Each read of `DepsgraphObjectInstance.object` leaks about 125 bytes | the per-sample walk over 52 000 instances grew the bake from 7 to 14.5 GB | per-sample walks key instances by instancer and persistent id |
| Per-sample Python loops over 7000 moving boxes, containment tests against all boxes | 836 ms per visibility sample, 30 min bake | vectorized updates, cached containment: 250 ms |
| Haze banks 200–500 m across with volume-only materials | every source behind them occluded | light-only materials do not occlude |
| The car the camera rides on, 1.2 m below it | the city below the camera occluded | objects that travel with the listener do not occlude |
| Merged meshes: the corbels around a tower, a bridge railing, a terrace's lamps, the old town's buildings in one object | most sources occluded for the whole shot | a mesh whose largest part fills less than half of its box occludes by its parts (splitting every mesh: 2.6 million boxes, 27 GB, 5 min setup) |
| Boxes around the camera (merged meshes) closed the Fresnel points of sources outside | sources at 0.2 visibility with nothing in between | a box that contains the listener or the source does not occlude that source |
| A hologram sign's text object | the sign occluded by its own lettering | text objects do not occlude |


## Reproduce

```bash
.venv/bin/python research/experiments/scripts/e11_blender_raycast.py    # about 2.5 minutes, needs Blender
```
