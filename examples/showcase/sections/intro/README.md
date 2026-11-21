# `intro`: SoundStage

The opening: one street shot twice, first as Blender renders it (silent), then with the sound
SoundStage renders for it. No explanation; the difference is the message. The full cut starts at
`sound` (sections/README.md, "Cuts").

| | |
|---|---|
| Length | 18 s (540 frames) |
| Set | the town (kit), main street, dusk |
| Features | everything at default settings |
| Reverb | `city_streets` |

## Title page

None at the start (the section opens on the picture, fading from black in frames 1 to 8). The
wordmark page comes at the end, over the running shot:

| Element | Text |
|---|---|
| Wordmark | `SoundStage`, centred, cap height 9 % |
| Tagline | Sound for Blender animations, computed from the scene. |
| Note | Headphones recommended. |

## Scene

A street in the town at dusk, street lamps on, a few parked cars, a pedestrian on the far pavement.
The camera stands at the kerb in a gap between parked cars, 1.6 m high, 24 mm, looking up the
street at 25° to its axis.

An ambulance with its light bar turning comes down the street at 72 km/h (20 m/s), passes the
camera at 6 m and leaves behind it. Its position along the street is `x = −90 m + 20 m/s · t`
(`t` from the start of the pass), so it passes the camera at 4.5 s. A car comes the other way at
40 km/h and passes at 2 s.

## Passes

| Pass | Frames | Label | Setting | What is heard |
|---|---|---|---|---|
| `silent` | 1–195 (6.5 s) | Blender renders the picture. | no sources | nothing: digital silence |
| `sound` | 196–540 (11.5 s) | SoundStage renders the sound. | defaults, `reverb=city_streets` | the same action from its start: the town, the car, the siren approaching, dropping in pitch as it passes, moving behind the camera and into the distance |

The action restarts at frame 196. From frame 421 (7.5 s into `sound`, the ambulance 60 m past the
camera) the wordmark card fades in over the running shot within 12 frames; the label goes with
it. The siren keeps receding under the wordmark; all sources have faded by frame 495, which leaves the
reverberation 1.5 s to end, and the picture fades to black in frames 533 to 540.

## Sounds

| Source | Sample | Tag |
|---|---|---|
| `intro.sound.siren` | `siren_two_tone.wav` | loop, on the light bar, `ref_distance=8`, cone to the front (`cone_inner_deg=120`, `cone_outer_deg=300`, `cone_outer_gain_db=-8`), `end_frame=480`, `fade_out=0.5` |
| `intro.sound.amb_engine` | `car_engine.wav` | loop, `pitch=0.9`, `ref_distance=4`, group `vehicles` |
| `intro.sound.amb_tyres` | `tyre_noise.wav` | loop, `ref_distance=4`, `gain_db=-6`, `offset` at the rear axle, group `vehicles` |
| `intro.sound.car_engine`, `.car_tyres` | `car_engine.wav`, `tyre_noise.wav` | loops on the oncoming car, `ref_distance=4`, engine `gain_db=-4`, tyres `gain_db=-6`, group `vehicles` |
| `intro.sound.step_1` … `step_4` | `footstep_1.wav` … `_4.wav` | one-shots on the pedestrian, on the frames a heel lands (the samples in turn), `ref_distance=2`, group `people` |

The vehicles' sounds ride on followers: empties on the path of the `sound` pass from 1 s before it
begins, which is where the loops start. What is still on its way when the pass begins (the siren,
90 m away, 0.26 s) is so heard on its first frame. The visible vehicles cannot carry it: in those
frames they are elsewhere, in the `silent` pass.
| `intro.sound.bed` | `town_bed.wav` | `spatial=False`, `gain_db=-18`, `fade_in=0.5`, `end_frame=465`, `fade_out=1.0`, group `ambience` |

## Picture aids

Only the two labels, set larger than a pass label (cap height 4 %), centred in the lower third.
No instruments, no state chip, no section tag.

## Requirements

- **R1** Both passes show the same frames of the same action (same camera, same motion), so that
  the sound is the only difference.
- **R2** `silent` is digital silence, not a quiet bed.
- **R3** The ambulance, the car and the pedestrian use the town's models and sound tags unchanged
  (the kit's town module), as in `finale`.
- **R4** The siren is audible from the first frame of `sound` (it is 90 m away then) and still
  audible, receding, when the wordmark appears.
- **R5** No text names a feature: this section makes one point.

## Known answers

Probe `intro.probe.sound.siren`: a 1 kHz sine on the light bar, tagged like the siren.

| What | Expected |
|---|---|
| Frames 1–195 | every sample 0 |
| Probe frequencies | also computed from the baked positions; the two below agree with them |
| Probe frequency in the first 0.25 s of `sound` | 1061.8 Hz ± 0.3 % (rate 1.0618) |
| Probe frequency 9 s after the pass starts | 945.0 Hz ± 0.3 % |
| Probe passes 1000 Hz | when the geometry says (4.47 s after the pass starts: the light bar is 2.65 m high and 0.9 m ahead of the van's centre), ± 20 ms |
| Probe level | highest where distance and cone predict (4.22 s: the cone points forwards, so the siren is loudest shortly before it passes), ± 0.1 s |
| Last 0.2 s of the section | below −60 dBFS |

## Needs ears

Whether the first second of `sound` is convincing as "the picture got its sound", and whether the
siren reads as an ambulance.
