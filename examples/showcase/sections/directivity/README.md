# `directivity`: Directivity

Most sources are louder in one direction. A jet engine whines to the front and roars to the back;
walking around a running jet, the sound changes with every step. A cone per sound sets where it
radiates, and an object can carry several sounds at different places.

| | |
|---|---|
| Length | 29 s (870 frames) |
| Set | an airfield apron, day |
| Features | cones (`cone_inner_deg`, `cone_outer_deg`, `cone_outer_gain_db`, `forward_axis`), several sounds per object, `offset`, groups |
| Reverb | none |

## Title page

| Element | Text |
|---|---|
| Title | Directivity |
| Claim | Most sources are louder in one direction. A cone per sound sets where it radiates. |
| Code chip | `cone_inner_deg = 60   cone_outer_deg = 240` |
| Listen for | the whine in front of the jet, the roar behind it. |

## Scene

A business jet with two engines at the tail stands on the apron, engines running (the fans turn,
heat shimmer is not needed). The camera circles it on a radius of 30 m, 3 m high, 28 mm, always
aimed at the jet (4 m ahead of the engines, 2.4 m up), once in 13 s (14.5 m/s, a drone),
counter-clockwise seen from above. The circle is centred on the middle between the engines, so
the distance to the intakes and nozzles stays between 27.6 and 32.4 m. The lap starts in front of
the nose and closes, so the picture runs on from the first pass into the second.

Each engine carries two sounds:

| Sound | Where | Cone axis | Cone | In front | At 90° to the axis | Behind |
|---|---|---|---|---|---|---|
| Whine (fan) | intake, 1.5 m ahead of the engine's middle | to the nose | 60° / 240°, −18 dB outside | 0 dB | −7.6 dB | −18 dB |
| Roar (jet) | nozzle, 1.5 m behind it | to the tail | 90° / 270°, −12 dB outside | −12 dB | −4.1 dB | 0 dB |

## Passes

| Pass | Frames | Chip | Label | Setting | What is heard |
|---|---|---|---|---|---|
| `omni` | 91–480 (13 s) | WITHOUT | Equally loud in all directions | no cones (360° / 360°) | the same mix of whine and roar from every side |
| `cones` | 481–870 (13 s) | WITH | A cone per sound | whine 60° / 240° / −18 dB · roar 90° / 270° / −12 dB | whine in front, both at the side, roar behind |

## Sounds

| Source | Sample | Tag |
|---|---|---|
| `directivity.<pass>.whine_l`, `.whine_r` | `jet_whine.wav` | loops on the jet, `offset` at each intake, `forward_axis` to the nose, `ref_distance=30`, `loop_phase="random"`, group `intake` |
| `directivity.<pass>.roar_l`, `.roar_r` | `jet_roar.wav` | loops on the jet, `offset` at each nozzle, `forward_axis` to the tail, `ref_distance=30`, `loop_phase="random"`, group `exhaust` |

All four are entries of one object, the jet, with `loop_crossfade=0` (the loops are seamless).
They fade in over 0.2 s and out over 0.4 s, ending where their sound still arrives 0.25 s before
the pass ends. Both samples are recordings (`../../sounds/README.md`): the whine is a fighter
idling before take-off (half its energy between 2 and 5 kHz), the roar a jet engine on a test
stand (99 % below 1 kHz). The section gain is −7 dB (S2); `omni` is 3.7 dB louder than `cones`,
since nothing in it is attenuated.

## Picture aids

- An inset map at the upper right, seen from above with the nose up: the jet's outline, the cones
  drawn as lobes around it (the gain as a polar curve, 0 dB at the lobe's full size, −24 dB at the
  centre; whine in the accent colour towards the nose, roar in white towards the tail; in `omni` one
  circle), the camera as a dot on its circle.
- Two level bars below it, "intake" and "exhaust", keyed from the cone formula at the camera's
  position (the mean power of the two engines). In `omni` both stay full.

## Requirements

- **R1** The camera moves, the jet stands: the distance to the engines is nearly constant and the
  motion is across the line of sight, so level changes come from the cones (playback rate within
  1 ± 0.005).
- **R2** The whine and the roar are different sounds in different frequency ranges, so the change
  is heard as a change of timbre and not only of level.
- **R3** The two engines play the same samples at random loop phases (their ids differ), so that
  they do not cancel each other.
- **R4** The jet does not occlude (`sfx_occluder=False`): the fuselage would shadow the far engine,
  which belongs to the `occlusion` section.
- **R5** The emitters lie inside the jet's bounding box and are entries of one object with
  different `offset` and `forward_axis`.
- **R6** `omni` and `cones` are the same lap.

## Known answers

Probes: pink noise at the left intake with the whine's cone and at the left nozzle with the roar's
cone (`directivity.probe.<pass>.intake`, `.exhaust`), `loop_phase=0`. Levels of `cones` relative to
`omni` at the same frame, which removes distance and direction; the expected value is the cone
formula at the angle taken from the baked positions.

| What | Expected |
|---|---|
| Intake probe: camera in front of the nose, abeam (90° from the cone's axis), behind the tail | 0, −7.6, −18.0 dB, ± 0.7 dB |
| Exhaust probe: the same three places | −12.0, −4.1, 0 dB, ± 0.7 dB |
| Whole lap, both probes, 0.2 s windows every 0.1 s | within 0.5 dB of the cone formula |
| `omni`: probe level over the lap, less the distance law, measured against the noise emitted for each window | constant within ± 0.3 dB |
| Probe spectrum, `cones` against `omni`, where the cone's gain is steady over the 0.5 s window | one gain at all third octaves from 125 Hz to 8 kHz, within 0.2 dB (a cone is broadband) |
| Stems | `intake` and `exhaust`; their sum equals the mix within 10⁻⁶ |

## Limits

A cone lowers all frequencies alike: real sources are more directional at high frequencies. The
change of timbre here comes from two sounds with two cones.

## Needs ears

Whether the two recordings read as one jet: the whine is a fighter's, the roar comes from another
engine and has almost nothing above 1 kHz.
