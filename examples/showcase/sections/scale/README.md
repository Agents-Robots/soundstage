# `scale`: Many sources

A tagged object that is instanced carries its sound to every instance. Forty identical cars
become forty engines that do not sound like one engine copied forty times, and a motorway with
300 vehicles renders with 600 sources: in full where they matter, cheaply where they do not.

| | |
|---|---|
| Length | 37 s (1110 frames) |
| Sets | a queue of cars on a country road; a motorway with a bridge; day |
| Features | tags inside instances, `instance_limit`, `loop_phase`, far field (`detail_voices`), culling (`cull_db`, on; it finds nothing to skip on 4 km) |
| Reverb | none |

## Title page

| Element | Text |
|---|---|
| Title | Many sources |
| Claim | Instanced objects carry their sounds along. Hundreds of sources render in full where they matter. |
| Code chip | `instance_limit = 0   detail_voices = 64   cull_db = -40` |
| Listen for | forty engines, not one; and a motorway that sounds like one. |

## Scene

**Queue.** Forty identical cars stand in a queue, 6 m from one to the next (234 m), engines
idling. They are 40 instances of one collection; their engines are 40 instances of another, which
holds one empty with one tag (one per pass: `scale.queue_same`, `scale.queue_random`). The camera moves along the
queue at walking pace (1.5 m/s, 10.5 m in 7 s), 2.5 m beside the cars, 1.6 m high, 24 mm, looking
along the queue.

**Motorway.** Two carriageways of two lanes, 4 km long, with a bridge across the middle. 300
vehicles, instances of six collections: 240 cars in four variants at 110 to 130 km/h, 60 trucks
in two variants at 80 to 90 km/h, 53 m apart on average in a lane, each instance with its own
speed (seeded); in each lane every vehicle is at least as fast as the one behind it, so nobody
catches up. Every vehicle has an engine and a tyre sound: 600 sources. The camera is a drone: it
starts 200 m to the side of the motorway and 60 m above it and flies in 20 s to a point 12 m above
the outer eastbound lane, 60 m before the bridge, looking along the traffic towards the bridge
(10 m/s, eased at both ends).

Sound from a vehicle 2.7 km away takes 8 s to reach the drone, so the loops cannot all end at once
before the pass does. The vehicles are put into four bands by their distance from the drone's last
position (up to 250 m, 700 m, 1400 m, farther), each variant with one collection per band (24 in
all): the farther the band, the earlier its loops end and the longer they fade (0.5 to 3 s), so
that every vehicle's faded end has reached the drone 0.3 s before the pass ends. The distant wash
thins out from 9 s on while the drone comes down to the near traffic.

## Passes

| Pass | Frames | Chip | Label | Setting | What is heard |
|---|---|---|---|---|---|
| `same` | 91–300 (7 s) | WITHOUT | 40 cars, the same loop from the same point | `loop_phase=0` | one engine with a hollow, shifting colour: 40 copies that differ only in their delay |
| `random` | 301–510 (7 s) | WITH | 40 cars, each at its own point of the loop | default (`loop_phase="random"`) | a queue: single engines near the camera, a murmur further on |
| `motorway` | 511–1110 (20 s) | | 300 vehicles, 600 sources | `instance_limit=0`, otherwise defaults | a wash of traffic from afar that turns into single vehicles passing below, each with its own pitch drop |

## Sounds

| Source | Sample | Tag |
|---|---|---|
| `scale.same.qNN/…` (40) | `car_idle.wav` | loop on the engine empty of the collection `scale.queue_same`, `ref_distance=3`, `gain_db=-6`, `loop_phase=0` |
| `scale.random.qNN/…` (40) | `car_idle.wav` | the same in `scale.queue_random`, `loop_phase="random"` |
| `scale.motorway.vNNN/…` (240 car engines) | `car_engine.wav` | loop, `pitch` 0.9, 1.0, 1.1 or 1.2 by variant, `ref_distance=8`, `loop_phase="random"`, group `traffic` |
| `scale.motorway.vNNN/…` (60 truck engines) | `car_engine.wav` | loop, `pitch` 0.55 or 0.65 by variant, `ref_distance=8`, `gain_db=3`, group `traffic` |
| `scale.motorway.vNNN/…` (300 tyres) | `tyre_noise.wav` | loop, `offset` at the rear axle, `ref_distance=8`, group `traffic` |

A source inside an instance gets the id `<instancer>/<object>:<index>`; the instancers are named
`scale.<pass>.<…>`, so each pass is rendered with `--solo scale.<pass>.*` like everywhere else.
All loops fade in over 0.3 s and use `loop_crossfade=0`. The queue's loops end 5.75 s into their
pass and fade out over 0.3 s (the farthest car, 228 m away, is heard 0.66 s later); the motorway's
end by distance band (above). The queue is 6 dB down: forty idling engines, the nearest 2.5 m away,
are otherwise 7 dB louder than the motorway. The section gain is +1.5 dB: `motorway` has
−17.8 LUFS, the section's true peak is −2.3 dBTP.

## Picture aids

- The number of sources on the label, and in `motorway` a counter at the upper right ("600
  sources").
- `same` and `random`: a row of 40 small marks at the upper right, one per car, each pulsing at
  its loop's position: in step in `same`, scattered in `random`.

## Requirements

- **R1** The cars of the queue are instances (one empty per car instancing the collection), not
  copies with a tag each: the section shows that one tag is enough. The engines' collections hold
  only an empty, so the two passes' queues need no hiding: only the cars are seen.
- **R2** `same` and `random` are the same frames and the same camera path (a camera each, so the
  restart is a cut); only `loop_phase` differs.
- **R3** The section is baked with `instance_limit=0`. With the default (32) the bake keeps the 32
  instances of each tagged object that come closest to the camera and warns about the rest: of the
  queue's 40, it keeps 32 (a check bake with the default, `bake_default_limit/`). The motorway's 24
  collections have fewer than 32 instances each, so the default would keep them all.
- **R4** The vehicles of the motorway do not occlude (`sfx_occluder=False` on their collections):
  seen from above they do not hide each other, and 300 moving boxes would be tracked for nothing.
  The bridge occludes as it stands.
- **R5** Speeds are constant per vehicle and seeded; no two vehicles of a lane come closer than 12 m
  during the pass (checked at build time; the closest are 24 m apart).
- **R6** `motorway` is rendered with `quality=high` (vehicles approach at up to 36 m/s plus the
  drone's 10 m/s).
- **R7** The render time and peak memory of `motorway` are written to the section's report.

## Known answers

Probes: pink noise at the queue's engines in both passes, in collections of their own instanced at
the same places (`scale.probe.<pass>.qNN/…`, `loop_phase` as the pass has it).

| What | Expected | Measured |
|---|---|---|
| Sources in the bake | 40 (`same`), 40 (`random`), 600 (`motorway`); no warning about dropped instances | as expected |
| With the default `instance_limit` | 32 of the queue's 40 kept, with a warning | 32, warned |
| `same`: two neighbouring cars' probes, rendered alone, correlation at the best lag in 0.4 s windows (their delay drifts by 0.2 ms over the pass as the camera walks) | at least 0.9 | 0.938 |
| `random`: the same | at most 0.2 | 0.084 |
| `random`: power of all 40 probes together | the sum of the single powers within 1 dB in every octave band | −0.2 dB at most |
| `same`: the same | reported: the comb's notches are 57 Hz apart and closer, so an octave averages them out; the correlation above is the known answer | ± 0.2 dB |
| `motorway`: default render against a reference with `detail_voices=null`, `cull_db=null` | integrated loudness within 0.3 LU, short-term loudness (3 s) within 1.0 LU at every 0.5 s | −0.02 LU, 0.14 LU |
| `motorway`: report | sources in the far field above zero; culled seconds reported | 580 of 600 in the far field; nothing culled: every vehicle stays within about 33 dB of its group, inside the −40 dB budget |
| `motorway`: playback rates | within 0.85 to 1.15, no clamp warning | 0.893 to 1.128 |
| `motorway`: render time, peak memory | reported, not asserted | 36 s, 3.7 GB (the process's peak) |

## Limits

All instances of a collection share its tag: variety between vehicles comes from several
collections, not from a setting per instance. One-shot variations per instance are not
implemented.

## Needs ears

Whether `same` is heard as wrong without the label, and whether the motorway from afar sounds like
traffic or like noise.
