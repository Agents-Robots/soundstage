# `sources`: One line per sound

A sound is one line in the script that builds the scene: a sample, on an object. The section adds
the lines one at a time and shows each on screen as it becomes audible.

| | |
|---|---|
| Length | 42 s (1260 frames) |
| Set | the town square (kit), day |
| Features | loops, one-shots with trigger frames, `offset`, beds (`spatial=False`), `pitch`, groups |
| Reverb | none |

## Title page

| Element | Text |
|---|---|
| Title | One line per sound |
| Claim | A sound is one line in the script that builds the scene: a sample, on an object. |
| Code chip | `tag.add_sound(car, "car_engine.wav")` |
| Listen for | each line adding one sound, at the place of its object. |

## Scene

The town square: the main street along one side, the church opposite, beyond the street, with
its bell tower 62 m from the camera and right of the middle of the view; trees, a bench. The
camera stands on the square, 1.6 m high, 28 mm, looking across the street.

A car drives along the street at 30 km/h (8.3 m/s), from left to right, 12 m from the camera, and
passes the middle of the frame 3 s into the pass. The same drive is repeated in the passes that
have it. In `pitch` a second camera (24 mm) looks at a scooter, the car and a truck standing side
by side on the square, 12 m away.

## Passes

Each pass shows its code in a panel at the upper left (monospace): the calls of the sounds heard
in the pass, the new ones in the accent colour, the others in grey. A call longer than 54
characters wraps after a comma, as Python is written.

| Pass | Frames | Label | New line on screen | What is heard |
|---|---|---|---|---|
| `loop` | 91–270 (6 s) | A loop on an object | `tag.add_sound(car, "car_engine.wav", ref_distance=4, group="vehicles")` | the engine, moving with the car |
| `layers` | 271–450 (6 s) | More sounds on the same object | `tag.add_sound(car, "tyre_noise.wav", offset=(0, 1.3, -0.4), group="vehicles")` and `tag.add_sound(car, "car_horn.wav", mode="once", frame=331)` | engine and tyres; the horn once, 2 s into the pass |
| `events` | 451–720 (9 s) | One-shots on frames | `tag.add_sound(bell, "church_bell.wav", mode="once", frame=[466, 526, 586])` | three strikes of the bell, each as the bell reaches the end of its swing; the car stands and idles; the last strike rings out |
| `bed` | 721–870 (5 s) | A bed that does not move | `tag.add_sound(root, "town_bed.wav", spatial=False, group="ambience")` | the town ambience; the camera pans 90° to the right: the idling car moves to the left of the stereo image, the bed stays |
| `pitch` | 871–1080 (7 s) | One sample, three vehicles | `tag.add_sound(scooter, "car_engine.wav", pitch=1.6)`, the same for `car` (`pitch=1`) and `truck` (`pitch=0.6`) | scooter, car and truck alone in turn (0.1 to 1.9 s, 1.9 to 3.7 s, 3.7 to 5.5 s), then together (5.5 to 6.6 s) |
| `stems` | 1081–1260 (6 s) | Groups become stems | `soundstage render bake/scene.json -o mix.wav --stems`, and a comment naming the groups | the drive, one bell strike and the bed together |

## Sounds

Every pass has its own tag entries (`sources.<pass>.<name>`).

| Source | Sample | Tag |
|---|---|---|
| `…car_engine` | `car_engine.wav` | loop, `ref_distance=4`, group `vehicles`; fades out 0.3 s before the pass ends |
| `…car_tyres` | `tyre_noise.wav` | loop, `offset` at the rear axle, `gain_db=-6`, group `vehicles` |
| `…car_horn` | `car_horn.wav` | once, 60 frames into `layers`, `ref_distance=6` |
| `…car_idle` | `car_idle.wav` | loop in `events` and `bed`, `ref_distance=4` |
| `…bell` | `church_bell.wav` | once, on the bell in the tower (62 m away, 23 m up: 65 m), `ref_distance=40`, group `bells` |
| `…bed` | `town_bed.wav` | `spatial=False`, `gain_db=-18`, `loop_phase=0` (for the check), group `ambience` |
| `…scooter`, `…car`, `…truck` | `car_engine.wav` | loops with `pitch` 1.6, 1.0, 0.6, `ref_distance=4`, `loop_phase=0`; one entry for the vehicle alone and one (`…_together`) for the end |

## Picture aids

- The code panel (above). The texts are the real arguments of the calls in `build.py`: the build
  script formats the panel from the same values it passes to `tag.add_sound`; only the arguments
  that tie an entry to its pass (id, frame window, fades) are left out.
- `events` and `stems`: the bell swings in the open belfry; a ring flashes in front of it on each
  trigger frame.
- `pitch`: each vehicle's `pitch` value stands above it on a dark plate, in the accent colour and
  with a ring on the ground while the vehicle runs.
- `stems`: three level bars named after the groups, above the lower third, keyed from the distance
  law and the bell's arrival and decay.

## Requirements

- **R1** A pass adds only what its new line adds: `loop` has one source, `layers` three.
- **R2** The code on screen is the code that ran (generated from the call's arguments, not typed
  twice).
- **R3** The horn and the bell are heard later than their frames by their distance (12 m: 35 ms;
  the bell at 65 m: 190 ms); the section does not hide this, the `delay` section explains it.
- **R4** In `bed` nothing but the camera moves.
- **R5** In `pitch` the three vehicles stand, so that pitch is the only difference: the truck's
  sample is the car's, played 0.6 times as fast.
- **R6** No reverb and no occluders between sources and camera: what is heard is the sample, the
  distance and the direction.

## Known answers

Probes: a click on the horn's and the bell's trigger frames (`sources.probe.layers.horn`,
`sources.probe.events.bell`), a 1 kHz sine on each vehicle in `pitch` while it runs alone, pink
noise on the idling car in `bed`. Arrival times are computed from the baked positions.

| What | Expected |
|---|---|
| Audible sources per pass (report) | `loop` 1, `layers` 3, `events` 2, `bed` 2, `pitch` 6 (two entries per vehicle), `stems` 4 |
| Horn probe onset | trigger frame + distance / 343 m/s, ± 1 ms |
| Bell probe onsets | three, each trigger frame + distance / 343 m/s (about 190 ms), ± 1 ms |
| `bed`: the `ambience` stem | equal to the sample times its gain, sample for sample, in both channels, from the end of its fade-in to 1.2 s before the pass ends, whatever the camera does |
| `bed`: probe on the car | level difference between the channels changes by more than 10 dB during the pan |
| `pitch`: probe frequencies | 1600, 1000 and 600 Hz, ± 0.1 % |
| `stems` | three group stems; their sum equals the mix within 10⁻⁶ |

## Needs ears

Whether the car engine pitched to 1.6 and 0.6 is believable as a scooter and a truck, or whether
those two need their own recordings.
