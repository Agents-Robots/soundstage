# `cuts`: Camera cuts

The camera is the microphone. When the picture cuts to another camera, the sound cuts with it:
level, direction, delay and pitch belong to the new position from the first frame. A race covered
by five cameras, one of them on board, shows it; the same edit heard from one fixed microphone
shows what is missing without it.

| | |
|---|---|
| Length | 33 s (990 frames) |
| Set | an oval race track with a grandstand, day |
| Features | listener cuts (camera markers), moving listener, the bake's `listener` setting |
| Reverb | none |

## Title page

| Element | Text |
|---|---|
| Title | Camera cuts |
| Claim | The camera is the microphone. When the picture cuts, level, direction, delay and pitch cut with it. |
| Code chip | `marker.camera = camera_2` |
| Listen for | each shot having its own sound, most of all on board. |

## Scene

An oval: two straights of 250 m and two turns of 80 m radius, 1003 m around. `s` is the distance
along the track from the start line. Three race cars drive at 180 km/h (50 m/s), 60 m (1.2 s)
apart, the lead car at `s = 25 m + 50 m/s · t`; in 15 s they cover the start straight, turn 1 and
the back straight.

| Camera | Where | Lens |
|---|---|---|
| A | beside the start straight at s = 70 m, 12 m from the cars' line, 1.5 m high | 28 mm, static, aimed 6 m back along the straight |
| B | on board the lead car, above the driver's helmet, looking ahead | 20 mm |
| C | outside turn 1 at s = 320 m, 20 m from the line, 3 m high | 35 mm, pans with the cars |
| D | on the roof of the grandstand outside the back straight, where turn 1 ends, 110 m from the track, 30 m high | 24 mm, static, aimed at turn 1 |
| E | beside the back straight at s = 675 m, 6 m from the line, 0.5 m high | 24 mm, static |

Six shots of 2.5 s, cut by timeline markers bound to the cameras:

| Shot | Time | Camera | What the lead car does | Level of its engine | Late by |
|---|---|---|---|---|---|
| 1 | 0 to 2.5 s | A | passes at 0.9 s (the second car at 2.1 s) | up to −6 dB | 35 ms at the pass |
| 2 | 2.5 to 5 s | B | on the straight, into turn 1 | 0 dB, steady | 6 ms |
| 3 | 5 to 7.5 s | C | passes at 5.9 s (the second at 7.1 s) | up to −10.5 dB | 58 ms at the pass |
| 4 | 7.5 to 10 s | D | leaves turn 1, 185 to 115 m away | −30 to −26 dB | 0.54 to 0.33 s |
| 5 | 10 to 12.5 s | B | on the back straight | 0 dB, steady | 6 ms |
| 6 | 12.5 to 15 s | E | passes at 13.0 s (the second at 14.2 s) | up to 0 dB | 17 ms at the pass |

## Passes

| Pass | Frames | Chip | Label | Setting | What is heard |
|---|---|---|---|---|---|
| `one_mic` | 91–540 (15 s) | WITHOUT | Five cameras, one microphone | bake with `listener` = camera A | the cars pass camera A and stay far away, 30 dB down, while the picture goes on board, to the turn and to the grandstand |
| `per_camera` | 541–990 (15 s) | WITH | Five cameras, the sound cuts with the picture | default (the active camera) | a pass-by, the steady roar on board, a pass-by in the turn, the far and late sound from the grandstand, on board again, a close pass-by |

The picture is the same in both passes: the same six shots.

## Sounds

| Source | Sample | Tag |
|---|---|---|
| `cuts.<pass>.engine_1` … `engine_3` | `race_engine.wav` | loop on each car, `pitch=1.8`, `ref_distance=6`, `loop_phase="random"`, `loop_crossfade=0`, `fade_in=0.2`, `end_frame` 13.6 s into the pass, `fade_out=0.5` after it, group `cars` |
| `cuts.<pass>.tyres_1` … `tyres_3` | `tyre_noise.wav` | loop, `ref_distance=6`, `gain_db=-8`, same fades, group `cars` |
| `cuts.<pass>.crowd` | `crowd_bed.wav` | `spatial=False`, `gain_db=-24`, same fades, group `ambience` |

Both passes are rendered with `quality=high`: at the start of a pass-by the engine is read 17 % faster.
The loops end at 13.6 s: from camera A, up to 190 m from the cars, the faded end arrives 0.55 s
later, 0.35 s before the pass ends. The section gain is +1 dB: `per_camera` has −17.9 LUFS, the
section's true peak is −3.3 dBTP.

## Picture aids

- A camera chip at the upper right: the letter of the active camera and its place in words
  ("A · trackside", "B · on board", "C · turn 1", "D · grandstand", "E · back straight").
- A small map of the oval beside it: the cars as dots, the five cameras, the active one in the
  accent colour. In `one_mic` a microphone mark stays at camera A.
- Shot 4: the distance to the lead car and its delay, counting ("150 m · 0.44 s late").

## Requirements

- **R1** Cuts are markers bound to cameras, on frames 75 apart: the path the bake supports. No
  camera is animated across a cut.
- **R2** Camera B is parented to the lead car. The car travels with the listener and does not
  occlude its own or the other engines for that camera.
- **R3** `ref_distance=6`, so the shots differ in level as they would on site: about 30 dB between
  on board and the grandstand. The crowd bed carries the quiet shot.
- **R4** The grandstand, barriers and fences are set not to occlude: the section shows cuts, not
  occlusion.
- **R5** `one_mic` is a second bake of the same .blend with `listener` set to camera A
  (`bakes` in `section.py`, `bake_one_mic/`); picture and sources are identical. Five more bakes,
  each with one camera as the fixed listener over `per_camera`'s frames, are the checks' reference
  for what that camera alone hears.
- **R6** The cars drive at one speed on one line, linear in `s`; the engine sample is steady
  (sound requirement A2), so every change of pitch in a shot is Doppler.
- **R7** The loops end 1.4 s before the pass does, while the cars still move.

## Known answers

Probes on the lead car: a 1 kHz sine and a click every 0.5 s (`cuts.probe.<pass>.sine`, `.click`).
Each camera's own sound is the probe rendered from the bake with that camera as the fixed listener.

| What | Expected | Measured |
|---|---|---|
| `per_camera`: cuts in the report | five, on frames 616, 691, 766, 841 and 916 | as expected |
| `one_mic`: cuts in the report | none | none |
| `per_camera`, shots 2 and 5 (on board): sine | 1000.0 Hz ± 0.5 Hz, level constant within 0.1 dB | 1000.00 Hz, 0.000 dB |
| `per_camera`: sine frequency in the 50 ms after each cut's 10 ms crossfade | the new camera's within 0.5 %: no glide from the old one | equal to 0.1 Hz (874 → 1000, 1000 → 1170, 874 → 1148, 995 → 1000, 1000 → 1166 Hz) |
| `per_camera`: sine level in the same 50 ms | the new camera's within 0.5 dB | 0.00 dB |
| `per_camera`: every shot from 60 ms after its cut | the new camera's own render, sample for sample | max difference 1e-7 |
| `per_camera`: click onsets | emission + distance to the shot's camera / 343 m/s, ± 1 ms (shot 4: 0.33 to 0.54 s); clicks heard within the shot they were emitted in | 27 clicks, within 0.19 ms |
| `per_camera`, shot 1, and `one_mic`, first 2.5 s | equal within 0.1 dB | 0.000 dB |
| `one_mic`: sine frequency | camera A's Doppler within 0.5 % from 0.3 to 13 s; its change per 20 ms within 1 Hz of the Doppler's (no steps): 874 Hz at 2.5 s (leaving), 1098 Hz at 10 s (coming back along the far straight) | within 0.12 %, 0.45 Hz; 874.4 Hz, 1097.9 Hz |
| Crossfade at a cut | no sample step from 2 ms before to 12 ms after the cut larger than 1.05 × the largest on either side | at most 1.02 × |
| Report | no playback-rate clamp warning | none |

## Limits

A cut is hard: 10 ms of crossfade from the cut on, no sound bridge, no J- or L-cut; an editor adds
those from the stems. Over the last baked sample before a cut (8.3 ms at 4 substeps) the listener is
held where it was, so on board the sound's delay and level stop following the car for that long.
Engines keep one speed, so the cars do not lift for the turn. The crowd is a hall full of people
chatting, not a grandstand: no CC0 cheering recording was steady enough for a bed.

## Needs ears

Whether the jump of 30 dB to the grandstand shot is right for a showcase or too much to follow,
and whether `one_mic` reads as "wrong" without the label.
