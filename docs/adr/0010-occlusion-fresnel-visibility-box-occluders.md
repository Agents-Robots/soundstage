# 0010. Occlusion from Fresnel-zone visibility against bounding boxes, baked in Blender

- Status: Accepted
- Date: 2026-10-25
- Ticket: #20

## Context

Sources behind buildings, walls and vehicles must sound quieter and duller (FR-25, FR-47). The
question has three parts: what to measure, against which geometry, and where. The scenes are large
(a test city has 24 000 objects and, through instancing, 4 billion triangles), shots are minutes
long, and sources move fast enough that their sound arrives noticeably after the picture.

## Decision

- **Measure** per source, at 10 Hz in the bake, the open share of the first Fresnel zone of the
  sound's path in three bands (250 Hz, 1 kHz, 4 kHz): the direct path and four points per band on
  the zone's equal-area ring at the midpoint, each open if listener → point → source is
  unobstructed (after Tsingos and Gascuel). The path is that of the sound heard at the sample: the
  source at its retarded position, moving occluders where they were when the sound passed them.
- **Geometry**: oriented bounding boxes of rendered meshes and mesh instances (of their connected
  parts when the largest part fills less than half of the box) with a diagonal of at least
  `occluder_min_size` (2 m), in a `mathutils.bvhtree.BVHTree`; moving ones in a small tree
  rebuilt per sample. Light-only materials and objects that travel with the listener are left out.
  A custom property `sfx_occluder` (`False`, `"mesh"`) on an object or an instanced collection
  excludes it or uses its real triangles. For a source, a box that contains the listener or the
  source does not block, and a box beyond both endpoints (the ground under both) reflects instead.
- **Engine**: per band `g = v + (1 − v) · T(f)` with a transmission `T` (−12 dB, low-pass 1.5 kHz),
  realized as a broadband gain and a one-pole low-pass fitted in dB, smoothed 60/150 ms, on the
  direct sound; on the reverb send only in `occlusion` mode.
- Visibility goes into the scene file (`vis_frames`, `src_visibility` per band), so renders with
  other transmission settings need no new bake.

## Alternatives considered

- **Single ray, binary visibility** (game-engine raycast occlusion): switches abruptly and has no
  frequency dependence; small obstacles block as much as buildings.
- **Volumetric rays to a sphere around the source** (Steam Audio): smooth but frequency-independent,
  and the sphere radius is arbitrary.
- **Barrier formulas** (Maekawa, Kurze–Anderson) or **edge diffraction** (UTD, BTM): need the
  diffraction edges; not available for arbitrary scene geometry without far more computation.
- **`scene.ray_cast`**: 44 ms per ray on the test city after a first call of 0.55 s, so 2 minutes per
  visibility sample of a 111-source shot ([E11](../../research/experiments/E11-blender-raycast.md)).
- **BVH over the real triangles**: billions of instanced triangles; gathering them exhausted memory
  on the test city (the synthetic city of E11 extrapolates to 7.9 GB for 31 million triangles).
- **Visibility in the engine**: the engine has no geometry; the scene file stays the contract
  (ADR 0004).

## Consequences

- Bake time grows with sources × samples × 25 rays plus the moving occluders: on the test city
  (111 sources, 7080 moving boxes, a 120 s shot) visibility adds 6 minutes to a 10-minute bake (E11).
- Boxes are coarse: arches and L-shaped buildings need `sfx_occluder = "mesh"`;
  foliage, fences and other open objects need `sfx_occluder = False`. Light-only materials (fog,
  light beams) and the camera's vehicle are excluded automatically.
- The model has three free choices that hearing should confirm: the transmission (−12 dB, 1.5 kHz),
  the smoothing, and the 2 m size threshold.
- A per-region reverb (occlusion into another room's reverb) is not covered; `occlusion` mode only
  lowers the send.
