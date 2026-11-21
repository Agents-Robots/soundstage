# `around`: Around the listener

Two channels, two ears. A source to the side is louder in the near ear, arrives there earlier and
sounds brighter there; a source behind sounds a little duller. A scooter circles the camera at a
constant distance, so that direction is the only thing that changes.

| | |
|---|---|
| Length | 15 s (450 frames) |
| Set | a roundabout in the town (kit), day |
| Features | panner (`amplitude`, `hybrid`), interaural time difference, head shadow, rear cue |
| Reverb | none |
| Needs | headphones |

## Title page

| Element | Text |
|---|---|
| Title | Around the listener |
| Claim | Two channels, two ears: level, arrival time and timbre tell where a sound comes from. |
| Code chip | `panner = "hybrid"` |
| Listen for | the scooter leaving the picture, passing behind you and coming back. Use headphones. |

The headphones mark is shown on this title page.

## Scene

A roundabout with a planted island. The camera stands in the middle of the island, 1.6 m high,
24 mm, and does not move. A scooter with a rider circles it on a radius of 12 m, clockwise seen
from above, once in 12 s (6.3 m/s, 23 km/h):

| Time in the pass | Direction | In the picture |
|---|---|---|
| 0 s | straight ahead | yes, in the middle |
| 1.2 s | 37° right | leaves the frame |
| 3 s | right | no |
| 6 s | behind | no |
| 9 s | left | no |
| 10.8 s | 37° left | enters the frame |
| 12 s | straight ahead | yes |

The lap closes: the scooter ends where it started. The engine and
the probe ride 1 m above the ground, 0.6 m below the camera.

## Passes

| Pass | Frames | Label | Setting | What is heard |
|---|---|---|---|---|
| `lap` | 91–450 (12 s) | Time difference, head shadow, rear cue | defaults | the scooter leaving the picture to the right, outside the head at the side, duller and slightly quieter while it is behind, coming back on the left |

Only the effect is shown (sections/README.md). The checks also render the lap with level difference
only (`panner=amplitude`) and with time difference and head shadow but no rear cue (`hybrid`,
`rear_gain_db=0`), as references; neither is shown.

## Sounds

| Source | Sample | Tag |
|---|---|---|
| `around.<pass>.engine` | `car_engine.wav` | loop, `pitch=1.6`, `ref_distance=12`, `loop_phase=0`, `loop_crossfade=0` |
| `around.<pass>.tyres` | `tyre_noise.wav` | loop, `ref_distance=12`, `gain_db=-6`, `loop_phase=0`, `loop_crossfade=0` |

Both fade in over 0.2 s and out over 0.4 s, ending where their sound arrives 0.25 s before the
pass ends (S3; C5 asks for 0.2 s of silence at the end of the section). The section gain is
−4.5 dB (S2).

In `hybrid` the far ear is never more than 12 dB down from the pan (`ild_limit_db`); the head
shadow adds up to about 7 dB at high frequencies. Without the limit the scooter was in one ear only
at the sides, 40–55 dB down in the other, which was uncomfortable on headphones (#46). `amplitude`
keeps the plain pan law and is still one-sided there.

The rear cue cannot be switched off completely in `hybrid`: its low-pass has its highest cutoff at
20 kHz (`rear_cutoff_hz`), and at the engine's 96 kHz emission rate that still takes 0.1 dB off
4 kHz, 0.5 dB off 8 kHz and 1.1 dB off 12 kHz straight behind. `rear_gain_db=0` removes its level
step. The known answers count that low-pass in.

## Picture aids

- An inset map at the upper right, seen from above: the camera with its view cone, the circle, the
  scooter as a dot in the accent colour. This is the picture for the 80 % of the lap in which the
  scooter is outside the frame.
- Under the map, the arrival-time difference of the sound heard on that frame in milliseconds
  ("Δt 0.32 ms" at the sides).
- The rear half of the circle is shaded on the map.

## Requirements

- **R1** The distance is constant: no Doppler shift and no level change from distance.
- **R2** The references the checks render are the same lap; only the settings differ.
- **R3** The scooter has content above 6 kHz (engine at `pitch=1.6`, tyre noise), or the rear cue
  has nothing to act on.
- **R4** No occluders: the island's plants and the houses around are set not to occlude (every
  mesh is tagged `sfx_occluder = False`).
- **R5** The section says that it needs headphones (title page). On loudspeakers the time
  difference is the reason for the default of half its physical size.

## Known answers

Probe: pink noise on the scooter, tagged like the engine (`around.probe.<pass>.noise`,
`loop_phase=0`, `loop_crossfade=0`: the sample is seamless, and without the seam crossfade the
noise heard at any time is a known part of the sample). Levels and spectra are compared on the
same noise: against the part of the sample emitted for the window, between windows one noise loop
(4 s, 120°) apart, or between renders at the same time. `rear` below is the lap as shown,
`amplitude` and `hybrid` the lap rendered with those settings (`panner=amplitude` or `hybrid`, rear
cue off).

| What | Expected |
|---|---|
| Playback rate | 1.000 ± 0.001 |
| `amplitude`: summed power of both channels, windows 120° and 240° apart | equal within 0.1 dB |
| `amplitude`, source on the right (3 s): left channel | at least 40 dB below the right |
| `amplitude`: lag between the channels | 0 ± 0.5 samples, every 30° |
| `hybrid`, right (3 s) and left (9 s): lag | 15.4 samples (0.321 ms; the scooter is 0.6 m below the camera), ± 1; right channel first at 3 s, left first at 9 s |
| `hybrid`, right (3 s) and left (9 s): far ear against near ear, 125 Hz octave | 12.1 dB down (`ild_limit_db` = 12, the head shadow adds 0.1 dB there), ± 0.5 dB |
| `hybrid`: far ear against near ear at 2 s (60°), 4 kHz octave minus 250 Hz octave | negative (head shadow), absent in `amplitude` (0 ± 0.2 dB) |
| `amplitude` and `hybrid`: behind (165°) against in front (15°), the same pan | equal third-octave spectra within 0.2 dB, in `hybrid` after the 20 kHz rear low-pass |
| `rear` minus `hybrid`, behind (6 s) | −2.1 dB at 1 kHz, −4.7 dB at 6 kHz, −8.1 dB at 12 kHz (third octaves), ± 0.7 dB |
| `rear` minus `hybrid`, in front and at the sides | 0 ± 0.1 dB |

The head shadow is measured at 60° rather than 90°: at 90° the far channel of `amplitude` is
46 dB down and no longer a clean copy of the near one, so its spectrum says nothing. The rear-cue
values follow from the one-pole low-pass at 6 kHz and the −2 dB step, run at 96 kHz, weighted over
each third octave, less the `hybrid` render's own 20 kHz low-pass.

## Limits

Stereo cannot place a sound behind: the rear cue marks it, it does not move it there. No height.

## Needs ears

All of it: whether `hybrid` is heard outside the head, and whether the rear cue is noticeable with
this sound. This section is the one where numbers say least.
