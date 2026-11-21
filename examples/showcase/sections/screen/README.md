# `screen`: Sound follows the lens

A source in the picture is heard where it is seen. When the lens zooms in and two players move
from the middle of the frame to its edges, their sounds move apart with them, although neither the
players nor the camera have moved.

| | |
|---|---|
| Length | 27 s (810 frames) |
| Set | a tennis court, day |
| Features | screen-relative panning (`pan_reference`), `screen_edge_deg`, `sync_to_picture` |
| Reverb | none |

## Title page

| Element | Text |
|---|---|
| Title | Sound follows the lens |
| Claim | A source in the picture is heard where it is seen, also when the lens zooms. |
| Code chip | `pan_reference = "screen"` |
| Listen for | the hits moving apart as the players reach the frame's edges. |

## Scene

A tennis court seen from the side. The camera stands on the line of the net, 40 m from the middle
of the court and 6 m high, and looks along the net at the middle of the court, 1 m above it. The
players hit on the baselines, 11.9 m to the left and to the right of the net and 1 m above the
ground: 16.4° off the camera's axis, on the picture's horizontal midline.

A rally: one hit every 1.2 s, alternating between the players, 10 hits per pass, the first 0.6 s
after the pass starts (a drop-hit by the left player). The ball crosses in 1.2 s (20 m/s) on an arc
1.8 m high; it is drawn 18 cm wide, nearly three times its real size, so that it is seen at 24 mm.

The lens: 24 mm for 3 s, then a zoom to 55 mm over 5 s, then 55 mm for 4 s.

| Lens | Players in the frame | Seen from a seat at 3 picture heights | Level difference, `screen` | Level difference, `camera` |
|---|---|---|---|---|
| 24 mm | at 39 % of the half width | 6.6° off the middle | 3.7 dB | 4.1 dB |
| 55 mm | at 90 % of the half width | 15.0° off the middle | 8.9 dB | 4.1 dB |

The level differences are those between 200 and 400 Hz: the sine pan law, plus 0.1 to 0.3 dB from
the head shadow (`section.py` computes both). The players are well inside the 12 dB limit of the
`hybrid` panner, which only acts beyond the frame's edges.

## Passes

| Pass | Frames | Chip | Label | Setting | What is heard |
|---|---|---|---|---|---|
| `camera` | 91–450 (12 s) | WITHOUT | Direction from the camera | `pan_reference=camera` | the hits stay where they were while the players move to the edges |
| `screen` | 451–810 (12 s) | WITH | Direction on the screen | default (`pan_reference=screen`, `screen_edge_deg=16.5`) | the hits move outwards with the players |

## Sounds

| Source | Sample | Tag |
|---|---|---|
| `screen.<pass>.hit_left` | `tennis_hit_1.wav` | once, 5 frames, at the left player's racket, `ref_distance=40`, `sync_to_picture=True` |
| `screen.<pass>.hit_right` | `tennis_hit_2.wav` | once, 5 frames, at the right player's racket, same settings |

Both samples are two hits of one recording (`../../sounds/README.md`). The section gain is +8 dB,
with SoundStage's true-peak limiter at −1 dBTP on each pass (`limit_dbtp`, the exception to S1):
it takes up to 5.5 dB off the hits. S2 still cannot hold both ways: the hits are nearly all of the
section's sound, so the limiter holds its loudness too (+4 dB more gain gave 0.2 LU), and the
reference pass has −25.9 LUFS at −1.0 dBTP (`loudness_reported_only` in `section.py`). Before the
limiter it had −27.6 LUFS at +2 dB.

## Picture aids

- A stereo bar along the bottom of the picture, as wide as the frame: for each hit a mark in the
  accent colour at the place between left and right where the hit is heard, from the same formula
  as the engine's. In `screen` the mark is under the player; in `camera` the players move away from
  their marks during the zoom.
- The focal length ("24 mm" … "55 mm") at the upper right.
- A ring flashes at the racket on each hit.

## Requirements

- **R1** Camera and players stay in place; only the focal length is keyed.
- **R2** The hits are synced to the picture: at 40 m they would be 117 ms (3.5 frames) late, which
  would draw attention away from the direction.
- **R3** Both players are inside the frame at 55 mm (91 % of the half width), so the screen mapping
  applies throughout.
- **R4** Default `screen_edge_deg`. The label of `screen` states the value. A wider setting (25 for
  a large screen) is a render option and needs no new picture.
- **R5** The hits have content below 1 kHz (the 600 Hz body), where the level difference carries
  the direction.
- **R6** Nothing occludes: the net, the umpire's chair and the fence are set not to occlude.

## Known answers

Probes: a white-noise burst (`noise_burst.wav`, 0.1 s) on every hit, at the same emitters and
frames (`screen.probe.<pass>.left`, `.right`). The level difference between the channels is measured
between 200 and 400 Hz, below the head shadow.

| What | Expected |
|---|---|
| Side | left player's hits louder on the left, right player's on the right |
| `camera`: level difference, every hit | 4.1 dB ± 0.5 dB; change over the zoom below 0.5 dB |
| `screen`: level difference at 24 mm (hits 1 and 2) | 3.7 dB ± 0.7 dB |
| `screen`: level difference at 55 mm (hits 8 to 10) | 8.9 dB ± 0.7 dB |
| `screen`: change over the zoom | at least 4.5 dB |
| Onsets | on the hit's frame, ± 1 ms |
| Summed level of both channels, 200 to 400 Hz | the same in both passes within 0.2 dB, every hit |

## Limits

The mapping is made for loudspeakers at ±30° and a viewer at 3 picture heights; on headphones the
positions are wider than the picture.

## Needs ears

Whether a change of 5 dB between the channels is enough to be noticed without the stereo bar, or
whether the section should be rendered with a wider `screen_edge_deg`.
