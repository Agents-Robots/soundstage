# `occlusion`: Occlusion

What stands between a source and the camera muffles it: quieter, and duller, because high
frequencies bend around an obstacle less than low ones. The bake finds out from the scene's
geometry which sources are hidden, per frequency band and over time; nothing is keyed.

| | |
|---|---|
| Length | 39 s (1170 frames) |
| Sets | a row of houses along a road; a street corner built from the kit's houses; day |
| Features | visibility bake, occlusion filter, `occlusion`, `occlusion_mode` (reverb stays) |
| Reverb | none (motorbike), `city_streets` (busker) |

## Title page

| Element | Text |
|---|---|
| Title | Occlusion |
| Claim | What stands between a source and the camera muffles it. The bake reads it from the scene's geometry. |
| Code chip | `occlusion = True` |
| Listen for | the motorbike dimming behind each house; the busker heard around the corner before he is seen. |

## Scene

**Motorbike.** Four detached houses in a row, each 12 m wide, 6 m deep and 7 m high, with gaps of
12 m between them (84 m in all). The camera stands 45 m in front of the row, 1.6 m high, 70 mm,
and pans with the motorbike, which drives along a road 4 m behind the houses (55 m from the
camera) at 40 km/h (11.1 m/s), 100 m from left to right in 9 s; its engine is 0.7 m above the
road. The line from camera to motorbike crosses the row like this (`bike_edges` in `section.py`):

| Time in the pass | Line of sight | Middle at |
|---|---|---|
| 0 to 1.59 s | through the first house | 0.8 s |
| 1.59 to 2.52 s | open (first gap) | 2.06 s |
| 2.52 to 3.92 s | second house | 3.22 s |
| 3.92 to 5.08 s | open (middle gap) | 4.50 s |
| 5.08 to 6.48 s | third house | 5.78 s |
| 6.48 to 7.41 s | open (third gap) | 6.94 s |
| 7.41 to 9 s | fourth house | 8.2 s |

The sound follows the picture by its travel time, 0.16 to 0.17 s.

**Busker.** A street corner: a side street, 6 m wide, leaves the main street at a right angle to
the north. The house on the near corner is 12 m wide and 14 m deep. A busker with an accordion
stands in the middle of the side street, 8 m from the corner. The camera walks along the main
street's pavement towards the corner (1.5 m/s, 13.5 m in 9 s), 3 m from the house fronts, from
7.4 m before the corner to 6.1 m past it. It looks ahead along the street and turns towards the
side street from 2.5 s to 5 s. The corner house hides the busker until 4.2 s, when the camera
is 1.1 m before the corner; he is in the frame from then on. He ends his tune 7 s into the pass
and lowers the accordion, so the reverberation has ended before the pass does.

## Passes

| Pass | Frames | Chip | Label | Setting | What is heard |
|---|---|---|---|---|---|
| `bike_off` | 91–360 (9 s) | WITHOUT | Motorbike behind houses: no occlusion | `occlusion=False` | the engine passes at an even level, as if the houses were not there |
| `bike` | 361–630 (9 s) | WITH | Motorbike behind houses | default | quiet and dull behind each house, clear in each of the three gaps |
| `busker_off` | 631–900 (9 s) | WITHOUT | Busker around the corner: no occlusion | `occlusion=False` | the accordion is clear from the first step, from where a wall is seen |
| `busker` | 901–1170 (9 s) | WITH | Busker around the corner | default | muffled but present in the street's reverberation, then clear as the corner opens |

Each pass has its own camera, so that the restart of a pass is a cut: a camera that jumps back to
its start is heard as moving at 400 m/s for a frame.

## Sounds

| Source | Sample | Tag |
|---|---|---|
| `occlusion.<pass>.bike_engine` | `car_engine.wav` | loop, `pitch=1.4`, `gain_db=3`, `ref_distance=10`, `fade_in=0.2`, `fade_out=0.5`, arriving 0.25 s before the pass ends |
| `occlusion.<pass>.bike_tyres` | `tyre_noise.wav` | loop at the road, `gain_db=-5`, same settings |
| `occlusion.<pass>.busker` | `accordion_loop.wav` | loop at the accordion, `ref_distance=4`, `loop_phase=0`, `loop_crossfade=0`, `end_frame` 7 s into the pass, `fade_out=0.3` |
| `occlusion.<pass>.bed` | `town_bed.wav` | busker passes only: `spatial=False`, `gain_db=-24`, ends with the busker |

The `_off` passes carry the same entries with `occlusion=False`. The section gain is +9 dB: the
reference pass `busker` has −18.5 LUFS, the section's true peak is −3.5 dBTP (`busker_off`).

## Picture aids

- An inset map at the upper right, seen from above: the houses, the camera and the source as dots,
  and the line between them, amber while it is open and grey while a house is in the way. The line
  is computed from the houses' footprints, the boxes the bake reads (`open_line` in `section.py`);
  it shows the line of sight in the picture, which the sound follows by its travel time.
- The motorbike's headlight is on; in the gaps it is plainly in view.
- `busker`: the busker plays (the bellows open and close) from the first frame, which is seen
  once the corner opens.

## Requirements

- **R1** A house and a gap are each wider than the first Fresnel zone at 250 Hz (6.7 m across at
  the house fronts, 1.7 m at 4 kHz): the fully hidden and the fully open state are reached in all
  three bands.
- **R2** The houses (walls and roofs) are the only occluders: every other mesh has
  `sfx_occluder = False`; nothing stands on the line of sight.
- **R3** The camera pans with the motorbike, so the direction of the sound stays in the middle and
  the passes differ in level and timbre only.
- **R4** The busker passes use the default `occlusion_mode="obstruction"`: the direct sound is
  muffled, the reverberation is not, which is why he is heard around the corner.
- **R5** `_off` and default passes are the same frames; only `occlusion` differs.
- **R6** The busker stands clear of the walls (3 m), so that no box contains him.

## Known answers

Probes: pink noise on the motorbike's engine and at the accordion, tagged like the sources
(`occlusion.probe.<pass>.noise`, `loop_phase=0`). Levels of the default pass relative to the `_off`
pass at the same time, in octave bands, which removes distance, air and direction. For the busker,
the direct sound is the probe's own group stem; the reverberation is the `reverb` stem.

| What | Expected | Measured |
|---|---|---|
| `bike`: behind each house (heard at 0.99, 3.39, 5.95 s; the fourth at 7.90 s, during the fade-out, which both passes share) | −12.1 dB at 250 Hz, −13.6 dB at 1 kHz, −21.1 dB at 4 kHz, ± 1.5 dB | −11.9 to −12.2, −13.2 to −13.7, −19.7 to −20.8 dB (the fourth house the least) |
| `bike`: highest level in each opening | 0 dB ± 1 dB at 1 kHz and 4 kHz in all three; at 250 Hz 0 dB ± 1 dB in the middle gap and at least −3 dB in the outer two | −0.07 to −0.01 dB in all bands |
| `bike`: baked visibility | 0 behind the houses' middles and 1 in the gaps' middles, all bands; three openings; 1 kHz passes 0.5 within 0.3 s of the line of sight heard | as expected; within 0.03 s |
| `bike`: an edge at 4 kHz, −3 to −15 dB | faster falling than rising (followers of 60 ms and 150 ms) | 135 ms falling, 165 ms rising |
| `bike_off`: probe level | the distance law (−14.8 dB at the closest point relative to 10 m), 200 Hz to 1 kHz, within ± 0.5 dB, no step above 0.3 dB | ± 0.12 dB, steps 0.19 dB |
| `busker`: first 2 s | fully hidden: the values above, ± 1.5 dB | −12.3, −13.8, −21.3 dB |
| `busker`: from 6.5 s to the end of the tune | 0 dB ± 0.5 dB | 0.00 dB |
| `busker`: visibility at 1 kHz passes 0.5 | 4.2 s into the pass, ± 0.4 s | 4.15 s |
| `busker` and `busker_off`: the `reverb` stem (probe and accordion) | equal within 0.5 dB throughout | 0.00 dB |

## Limits

Occluders are boxes: a house occludes by its bounding box, roof included. Sound does not pass
through open windows or reflect off the houses opposite; the reverb preset stands for that.
Visibility is sampled 10 times a second.

## Needs ears

Whether the three openings sound like a motorbike passing gaps, and whether the hidden busker
sounds around a corner (and not merely turned down). Whether the accordion (a Balkan
improvisation, not a musette tune) reads as a busker; its recording carries a quiet room tail
about 23 dB below the playing.
