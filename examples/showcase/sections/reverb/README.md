# `reverb`: Reverb

The same sound in four spaces: outdoors, a living room, a gym and a church. Then a walk away from
the camera in the church: the direct sound falls with the distance, the reverberation stays, and
the steps sink into the room.

| | |
|---|---|
| Length | 44 s (1320 frames) |
| Sets | an outdoor court, a living room, a gym, a church nave (kit interiors) |
| Features | reverb presets, reverb send law, the `reverb` stem |
| Reverb | none, `livingroom`, `sport_gymnasium`, `chapel` |

## Title page

| Element | Text |
|---|---|
| Title | Reverb |
| Claim | The same sound in four spaces. The reverberation stays as a source walks away, the direct sound does not. |
| Code chip | `reverb = "chapel"` |
| Listen for | the tail after each clap, and how the steps sink into the room. |

## Scene

A figure with a basketball stands 4 m from the camera (1.6 m high, 20 mm, static, aimed 1.1 m
above the floor at the figure), in the same place in the frame in all four sets. At 20 mm the
frame shows the room around the figure. The action of the first four passes is the same to the
frame:

| Time in the pass | Event |
|---|---|
| 0.5, 1.1, 1.7 s | the ball hits the floor, 0.4 m in front of the figure, at its right hand |
| 2.5, 3.0 s | the figure tucks the ball under its left arm and claps twice, the hands 0.5 m in front of it, 1.3 m high |
| after 3.0 s | the figure stands still; the room is heard |

In `walk` (the church again) the figure claps once 0.3 s into the pass, turns, and walks down the
aisle away from the camera, from 4 m to 16.6 m at 1.4 m/s. It walks 18 steps of 0.7 m from 0.8 s
to 9.8 s, its feet landing every 0.5 s from 1.3 s. It turns back and claps again at 10.5 s. The
last 5.5 s are the tail.

| Preset | Decay time | Reverberation excited 12.6 m farther away, relative to the start |
|---|---|---|
| `livingroom` | 0.50 s | −4.4 dB |
| `sport_gymnasium` | 3.14 s | −0.7 dB |
| `chapel` | 4.62 s | −0.5 dB |

The direct sound of the second clap (hands 16.1 m from the camera) is 13.3 dB below that of the
first (3.5 m) in every space.

## Passes

| Pass | Frames | Label | Setting | What is heard |
|---|---|---|---|---|
| `outdoors` | 91–240 (5 s) | Outdoors | no reverb | ball and claps, dry |
| `livingroom` | 241–390 (5 s) | Living room, 0.5 s | `reverb=livingroom` | a short, close room |
| `gym` | 391–600 (7 s) | Gym, 3.1 s | `reverb=sport_gymnasium` | the hard ring of a sports hall |
| `church` | 601–840 (8 s) | Church, 4.6 s | `reverb=chapel` | a long, soft tail |
| `walk` | 841–1320 (16 s) | Walking away: the room stays | `reverb=chapel` | each step quieter but the room as loud; the second clap is mostly room |

No state chips: the four spaces are equals, not a "without" and a "with". Each room has its own
camera; `church` and `walk` share one.

## Sounds

| Source | Sample | Tag |
|---|---|---|
| `reverb.<pass>.ball_1` … `_3` | `basketball_1.wav` … `_3.wav` | once, one per contact frame, emitted at the floor under the ball, `ref_distance=3` |
| `reverb.<pass>.clap_1`, `_2` | `handclap_1.wav`, `handclap_2.wav` | once each, at the hands, `ref_distance=3` |
| `reverb.walk.step_1` … `step_4` | `footstep_1.wav` … `footstep_4.wav` | once, each on its frames (steps 1, 5, 9 … use the first sample, and so on), emitted at the foot that lands, `ref_distance=3` |

Every emitter is farther than `ref_distance` from the camera (hands 3.5 m, floor 4 m), so the
distance law is never clamped. The section gain is +6 dB.

## Picture aids

- The preset's decay time is part of the label.
- `walk`: two level bars at the upper right, "direct" and "room", keyed from the distance law and
  the send law relative to the start (floor −24 dB), and the distance in metres below them. The
  first falls by 12.4 dB from 4 m to 16.6 m, the second by 0.5 dB.
- A ring flashes at each impact: flat on the floor for the ball, upright at the hands for a clap.

## Requirements

- **R1** The same events on the same frames, at the same distance and place in the frame, in the
  first four passes: only the space differs.
- **R2** Every pass leaves its tail time to end: 2 s after the last clap in `outdoors` and
  `livingroom`, 4 s in `gym`, 5 s in `church`, 5.5 s in `walk`.
- **R3** The figure walks: a foot lands on every step's frame, 0.7 m apart, no sliding.
- **R4** The rooms contain camera and source and therefore do not occlude; no mesh occludes, and
  furniture and pillars stand off the line between them.
- **R5** The sets look their size: the living room 5 m long, the gym 40 m, the nave 30 m long and
  12 m high, so that the picture explains the tail.
- **R6** Level: single impacts cannot reach −18 LUFS. The true-peak limit holds; the loudness is
  reported, not asserted (sound rule S2): −22.1 to −23.4 LUFS in the rooms, −27.4 LUFS in `walk`,
  true peak −1.8 dBTP.

## Known answers

Probes: a click on every ball and clap frame, at the floor point and at the hands
(`reverb.probe.<pass>.click_ball`, `.click_clap`); in `walk` a white-noise burst of 0.1 s
(`noise_burst.wav`) on the two clap frames, at the hands. The direct sound is the probes' own
group stem, the reverberation the `reverb` stem.

| What | Expected | Measured |
|---|---|---|
| `outdoors`: the `reverb` stem | silent (below −120 dBFS) | digital silence |
| Decay time of the `reverb` stem after the last click (T30, 500 Hz to 2 kHz) | 0.50 s, 3.14 s and 4.62 s, ± 10 % | 0.47, 3.13, 4.64 s |
| Direct sound of the first four passes | equal within 0.1 dB | 0.000 dB |
| Click onsets | frame + distance / 343 m/s, from the baked positions, ± 1 ms | within 0.02 ms |
| `walk`: direct sound of the second burst against the first | −13.3 dB ± 0.3 dB (500 Hz to 2 kHz) | −13.32 dB |
| `walk`: `reverb` stem of the second burst against the first | −0.5 dB ± 0.5 dB | −0.52 dB |
| `walk`: direct-to-reverberant ratio | falls by 12.8 dB ± 0.6 dB | 12.80 dB |
| End of every pass | below −60 dBFS | ok (S3) |

## Limits

One reverb per render: a space is a pass, and a door between two spaces cannot be shown. The
presets are generic rooms, not the rooms in the picture; the early reflections do not follow the
walls of the set.

## Needs ears

Whether each preset fits its picture (the gym most of all), and whether the footsteps recorded on
a hard floor fit a church. Whether the recorded bounces sound like a basketball and not a drum
(body at 110 Hz, ring at 2 to 6 kHz), and whether the claps' short room tail in the recording
(−60 dB after 0.11 s) passes as dry.
