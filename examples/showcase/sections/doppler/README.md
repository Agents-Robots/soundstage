# `doppler`: Doppler effect

A source that approaches sounds higher, one that leaves sounds lower. Everyone knows the drop in
pitch of a passing ambulance; a pass-by without it sounds like a recording slid across the stereo
image. The shift follows from the motion in the scene, of the source or of the camera; nothing is
keyed.

| | |
|---|---|
| Length | 46 s (1380 frames) |
| Sets | a country road, a race track straight, an airfield, a railway line; day |
| Features | Doppler from source motion and from listener motion, `doppler_factor` |
| Reverb | none |

## Title page

| Element | Text |
|---|---|
| Title | Doppler effect |
| Claim | An approaching source sounds higher, a leaving one lower. The shift follows from the motion in the scene. |
| Code chip | `doppler_factor = 1.0` |
| Listen for | the drop in pitch at the moment of passing. |

## Scene

Four pass-bys on straight lines at constant speed. `x` is the position along the line, 0 at the
point closest to the camera.

| Pass-by | Speed | Closest | Travel | Rate at the start and the end | Drop |
|---|---|---|---|---|---|
| Ambulance on a country road | 72 km/h (20 m/s) | 8 m | −90 m to +90 m in 9 s | 1.0617 → 0.9451 | 2.0 semitones |
| Race car on a straight | 252 km/h (70 m/s) | 15 m | −245 m to +245 m in 7 s | 1.2558 → 0.8308 | 7.2 semitones (a fifth) |
| Propeller plane, low pass over the airfield | 216 km/h (60 m/s) | 80 m: 75 m up, 28 m to the side | −300 m to +300 m in 10 s | 1.2034 → 0.8554 | 5.9 semitones |
| The camera, in the cab of a train, passes a level-crossing bell | 108 km/h (30 m/s) | 10 m | −120 m to +120 m in 8 s | 1.0872 → 0.9128 | 3.0 semitones |

The siren's two tones, 440 Hz and 585 Hz, are heard at 467 and 621 Hz approaching and at 416 and
553 Hz leaving.

The rates in the table are those at the ends of the travel. A source stops early enough that its
sound has arrived and faded before the pass ends (R5), so the last sound heard left the ambulance
at +80 m, the race car at +189 m and the plane at +241 m, and the bell is heard until the camera is
103 m past it: the end rates heard are 0.9452, 0.8310, 0.8576 and 0.9129 (the known answers below).

Cameras: at the roadside for the ambulance and the race car (1.6 m high, 24 mm, static), turned
50° towards the approaching vehicle, so that the far end of the road is in the frame and the
vehicle leaves it just before it passes. On the airfield for the plane (35 mm), following it on
every frame; the flight path is 28 m to the side, so that the camera tilts up to 70° and does not
turn over. In the cab for the train, looking ahead along the track; the crossing with its lights and
barriers comes up on the right, the bell on a mast beside the road, 10 m from the track. (On the
crossing's post, 4 m from the track, it glided down 2.5 times as fast, within about a tenth of a
second, and passed 3 dB louder: a metallic ring at the moment of passing.)

## Passes

| Pass | Frames | Chip | Label | Setting | What is heard |
|---|---|---|---|---|---|
| `siren_off` | 91–360 (9 s) | WITHOUT | Ambulance, 72 km/h: no Doppler | `doppler_factor=0` | the siren gets louder and quieter and moves across, at one pitch |
| `siren` | 361–630 (9 s) | WITH | Ambulance, 72 km/h | default | the siren drops a whole tone as it passes |
| `race` | 631–840 (7 s) | | Race car, 252 km/h | default, `quality=high` | the engine falls by a fifth within half a second |
| `plane` | 841–1140 (10 s) | | Propeller plane, 216 km/h, 80 m away | default, `quality=high` | a slower glide, because the plane is further away |
| `train` | 1141–1380 (8 s) | | From a moving train, 108 km/h | default | the standing bell drops by three semitones as the camera passes; the train's own noise does not change |

## Sounds

| Source | Sample | Tag |
|---|---|---|
| `doppler.<pass>.siren` | `siren_two_tone.wav` | loop on the light bar, `ref_distance=8`, `loop_phase=0` |
| `doppler.<pass>.amb_engine`, `.amb_tyres` | `car_engine.wav` (`pitch=0.9`), `tyre_noise.wav` | loops, `ref_distance=4`, `gain_db=-6` |
| `doppler.race.engine`, `.tyres` | `race_engine.wav` (`pitch=1.8`, `gain_db=3`), `tyre_noise.wav` (`gain_db=-4`) | loops, `ref_distance=15` |
| `doppler.plane.engine` | `prop_plane.wav` | loop, `ref_distance=80`, `gain_db=5` |
| `doppler.train.bell` | `crossing_bell.wav` | loop on the bell on its mast at the crossing, `ref_distance=6`, from 1.5 s before the pass |
| `doppler.train.roll` | `train_roll.wav` | loop on the train (moves with the camera), 4.5 m behind and below the camera, `ref_distance=3` |

Every loop is tagged `loop_crossfade=0`: the samples are seamless, and the default 50 ms seam
crossfade made the plane's engine (90 Hz firing) stutter once per loop. Moving loops fade in over
0.2 s from the first frame of their pass and out over 0.5 s, ending where their sound still arrives
0.25 s before the pass ends. `race_engine.wav` is a large car's engine at
constant revs (no CC0 recording of a racing engine holds steady revs), raised by `pitch=1.8`. The
gains even the passes out: without them the race car, the plane and the train's own noise were 5
to 10 dB under the ambulance. The section gain is −2 dB (S2: the ambulance passes at −1.3 dBTP).

## Picture aids

- A pitch gauge at the upper right: a needle over a scale in semitones (−4 to +4), with marks at
  the values first and last heard in the pass (ambulance +1.04 and −0.98; race car +3.94 and
  −3.21; plane +3.21 and −2.66; train +1.45 and −1.58). The needle is keyed on every frame from the
  pass-by's geometry and the speed of sound, shifted by the travel time, and held at the first value
  until the sound arrives. In `siren_off` it stays at 0.
- The speed in km/h is part of the label.
- The ambulance's light bar turns.

## Requirements

- **R1** Linear keys and constant speed in every pass-by, checked at build time from the object's
  position per frame (within 0.5 % of the stated speed).
- **R2** `siren_off` and `siren` are the same frames of the same motion; only `doppler_factor`
  differs.
- **R3** The sources carry no shift of their own: the samples are steady (sound requirement A2).
- **R4** `race` and `plane` play faster than 1.09 times and are rendered with `quality=high`.
- **R5** Every source sounds from the first to the last frame of its travel and has faded before
  the pass ends, while the vehicle still moves.
- **R6** The train's own noise is tagged on the train, so the camera's vehicle and the camera move
  together: the section shows a moving listener beside a source at rest and one that travels along.
- **R7** No occluders and no reverb: pitch, level and direction only (every mesh is tagged
  `sfx_occluder = False`).

## Known answers

Probes: a 1 kHz sine on each moving source's emitter and on the bell, tagged like the source
(`doppler.probe.<pass>.sine`), and one on the train itself (`doppler.probe.train.cab`). "First" and
"last 0.25 s" are the first and last quarter second of the probe at full level (after its fade-in,
before its fade-out); the expected frequency is 1 kHz times the playback rate from the baked
positions at the middle of the window, and the README values (rates at the ends of the travel) are
met within the same tolerance widened by their distance from it.

| What | Expected |
|---|---|
| `siren_off`: probe frequency (mono sum, 0.25 s windows) | 1000.0 Hz ± 0.5 Hz throughout |
| `siren`: first and last 0.25 s | 1061.6 Hz and 945.3 Hz, ± 0.3 % |
| `siren`: passes 1000 Hz | 4.5 s + 8 m / 343 m/s = 4.523 s after the pass starts, ± 20 ms |
| `race`: first and last 0.25 s | 1255.7 Hz and 831.2 Hz, ± 0.5 % |
| `plane`: first and last 0.25 s | 1202.1 Hz and 859.9 Hz, ± 0.5 % |
| `train`: first and last 0.25 s | 1087.2 Hz and 912.8 Hz, ± 0.3 % |
| `train`: probe on the train itself | 1000.0 Hz ± 0.5 Hz |
| Frequency track of each probe (50 ms windows) against the rate from the geometry | within 0.5 % over the whole pass: one smooth S-curve, no steps (`probe_tracks.png`) |
| Report | no playback-rate clamp warning; `race` and `plane` faster than 1.09 at `quality=high` |

With `doppler_factor=0` the delay is frozen, but each ear's delay still follows the time difference
between the ears, which swings by 0.3 ms as the ambulance passes: each ear is shifted by up to
0.5 Hz, the two in opposite directions. The mono sum stays within 0.4 Hz.

## Limits

Engines keep one speed (no animated pitch), so the vehicles neither accelerate nor shift gears.
The plane has no ground reflection.

## Needs ears

Whether the recorded engines stay believable when played 25 % faster and 17 % slower, and whether
`siren_off` sounds wrong to someone who is not told why.
