# `finale`: All together

One evening in a town, in seven shots. Every sound comes from the scene: one bake, one render, no
gain rides and nothing placed by hand. This section is also the trailer.

| | |
|---|---|
| Length | 78 s (2340 frames) |
| Set | the town (kit) with its square, church and main street, the side street (`town.build(side_street=True)`), and north of the town the railway with two level crossings and a hill; dusk turning to night |
| Features | all, at their defaults |
| Reverb | `city_streets`, set in the scene |

## Title page

| Element | Text |
|---|---|
| Title | All together |
| Claim | One evening in a town. Every sound comes from the scene: one bake, one render, nothing mixed by hand. |
| Code chip | `soundstage render bake/scene.json -o town.wav` |
| Listen for | where each sound is, how far away, and what stands in between. |

The trailer cut drops this title page and starts on the first shot.

## Scene

The town runs on one clock; the shots only move the camera. Times are seconds from the start of
the pass (frame 91), positions in the town's coordinates (`kit/blender/town.py`: the main street
along X at y = 0, the square north of it for |x| ≤ 30, the church south of it). The sky and the sun
dim over the first 55 s, and the glow of the sunset fades into the night blue; a cool moonlight
rises as the sun sets, and 70 % of the windows are lit (the kit's town has 45 %), so that the night
stays readable.

**What happens in the town**

| Time | Event | Where |
|---|---|---|
| 0.2 to 74.5 s | evening ambience | bed |
| 0.2 to 59 s | a busker plays the accordion | on the square at (24, 40), beside the mouth of the side street, under a street lamp |
| 2.0, 4.5, 7.0, 9.5 s | the church bell strikes | in the tower, 23.6 m up |
| 8 to 20 s | an ambulance drives along the main street towards −X at 72 km/h, siren on | behind the houses on the north side of the street, except where the street camera sees its lane through the square's open south side (72 m of it, emitted 12.7 to 16.3 s) |
| 21.5 to 29 s | a passer-by walks up the side street (16 steps) | passes the walking camera 2.5 m to its left at 25 s |
| 24 to 54 s | a train runs at 108 km/h towards +X; horn at 33.5 s; its front passes the first crossing at 37.0 s and the second, 250 m on, at 45.3 s | railway 140 m north of the main street; outside these times the train is more than 300 m from every camera |
| 29 to 44 s | the bell of the first level crossing rings | 300 m east of the square |
| 39 to 49 s | the bell of the second level crossing rings | 550 m east |
| 50.5 to 57.5 s | a scooter crosses the square at 25 km/h, 5 m behind the square camera, straight behind it at 54 s | from the main street to the north-west |
| 60.4 to 70.0 s | thirteen firework bursts, 270 to 380 m away, 107 to 138 m up, the last five as a closing salvo from 68.2 s | north of the town, above its roofs |

**Shots**

| Shot | Time | Frames | Camera | What is heard | Callout on screen |
|---|---|---|---|---|---|
| `overview` | 0 to 9 s | 91–360 | drone 400 m south of the church, 80 m up, sinking to 64 m and closing in by 20 m (eased), 85 mm, aimed at the church | the ambience; the bell, 1.16 s after each swing of the clapper (397 m); at the end the siren, faint | "400 m away: 1.2 s late" |
| `street` | 9 to 20 s | 361–690 | on the square at (6, 44), 1.6 m high, 28 mm, looking south across the main street (42 m away) to the church | the bell, now close (95 m, 0.28 s late); the busker off to the left; the siren muffled behind the houses, clear and dropping in pitch while the ambulance is in the open (heard 12.8 to 16.4 s), muffled again | "behind houses" · "Doppler" |
| `corner` | 20 to 31 s | 691–1020 | walking down the middle of the side street towards the square at 1.5 m/s (x 57 to 40.5), 24 mm | steps passing close; the busker around the corner, dull at first, clear from about 26 s, in the street's reverberation | "around the corner" |
| `crossing` | 31 to 41 s | 1021–1320 | beside the first crossing's road, 8 m from the track, 24 mm, looking west along the track | the crossing bell; the horn, high (111 m away); the train passing; the pitch of horn and wheels falling | "Doppler" |
| `onboard` | 41 to 49 s | 1321–1560 | in the locomotive's cab, 1.6 m behind its front, looking ahead, 20 mm | the steady roll of the train; the second crossing's bell rising in level and dropping three semitones as the camera passes it (45.5 s) | "the camera moves: the bell drops" |
| `square` | 49 to 60 s | 1561–1890 | on the square at (5.6, 32.2), 20 m from the busker, who stands 3 m left of the middle; zoom from 24 to 70 mm between 51 and 57 s | the accordion moving to the left as the busker moves to the left of the frame; the scooter passing behind, duller | "behind you" · "sound follows the lens" |
| `fireworks` | 60 to 75 s | 1891–2340 | on the square at (0, 12), tilted up 14° over the roofs, 24 mm | each burst 0.8 to 1.1 s after its flash, the closing salvo bang on bang; the town's echo | "340 m: 1.0 s late"; at the end the card of what the evening took |

The busker stops at 59 s, as the first rocket rises, and lowers the accordion. The picture fades
to black over the last 1.5 s. Inside the cab, the locomotive's front wall, windscreen and lamps
are hidden for the `onboard` shot and a cab interior (`models.train_cab`) is shown instead.

## Passes

| Pass | Frames | Label | Setting | What is heard |
|---|---|---|---|---|
| `town` | 91–2340 (75 s) | (none; callouts only) | defaults; `reverb=city_streets` from the scene settings; section gain +3.9 dB | see the shots |

No lower third: the frame stays clean. A callout is a small chip in the upper right
(`overlay.callout`), in plain words, shown for 2.3 to 3 s while the effect it names is audible.

## Sounds

| Source | Sample | Tag |
|---|---|---|
| `finale.town.bed` | `town_bed.wav` | `spatial=False`, `gain_db=-16`, from 0.2 s with `fade_in=2`, ends at 73 s with `fade_out=1.5`, group `ambience` |
| `finale.town.busker` | `accordion_loop.wav` | loop on the accordion, `ref_distance=4`, 0.2 to 59 s, `fade_in=0.3`, `fade_out=0.6`, group `music` |
| `finale.town.bell` | `church_bell.wav` | once on the four strike frames, `ref_distance=80`, group `bells` |
| `finale.town.siren`, `.amb_engine`, `.amb_tyres` | `siren_two_tone.wav`, `car_engine.wav` (`pitch=0.9`, at the front axle), `tyre_noise.wav` (`gain_db=-6`, at the rear axle) | loops on the ambulance from 8 s, `fade_in=1`, ending at 19 s with `fade_out=1`; siren on the light bar, `ref_distance=8`; engine and tyres `ref_distance=4`; group `vehicles` |
| `finale.town.step_1` … `step_4` | `footstep_1.wav` … `_4.wav` | once, on the passer-by's step frames, `ref_distance=2`, `gain_db=-4`, group `people` |
| `finale.town.xing_bell_1`, `_2` | `crossing_bell.wav` | loops at the two crossings over their times, `ref_distance=6`, `gain_db=-8`, `fade_in=0.05`, `fade_out=0.3`, group `railway` |
| `finale.town.train_horn` | `train_horn.wav` | once at 33.5 s, on the roof at the front of the train, `ref_distance=60`, group `railway` |
| `finale.town.train_roll_1` … `_3` | `train_roll.wav` | loops under the locomotive and the two coaches, 24 to 54 s with 2 s fades, `ref_distance=8`, `gain_db=-3`, group `railway` |
| `finale.town.scooter`, `.scooter_tyres` | `car_engine.wav` (`pitch=1.6`), `tyre_noise.wav` (`gain_db=-8`) | loops, 50.5 to 57.5 s with 0.5 s fades, `ref_distance=5`, group `vehicles` |
| `finale.town.burst_1` … `burst_13` | `firework_bang_1.wav` … `_3.wav` in turn | once on the flash frame, at the burst, `ref_distance=600`, `gain_db=6`, group `fireworks` |

No source has `sync_to_picture`, and no per-source setting differs from its default except
`ref_distance`, `gain_db`, `pitch`, `offset`, the fades and the groups, and `loop_crossfade=0`,
`loop_phase=0` on the loops (the kit's loops are seamless). The levels were set so that the pass
reaches −18 LUFS ± 2 with one static gain and the true peak stays below −1 dBTP: the crossing bells
at 4 m would otherwise cover the passing train, and the steps at 2.5 m and the train at 6.5 m set
the peaks. The bangs are 6 dB louder than their samples, and soundstage's true-peak limiter at
−1 dBTP (`limit_dbtp`, the exception to S1) takes up to 5.6 dB off them. Moving the fireworks
closer alone made them no louder: within `ref_distance` a source plays at its sample's level
(`inverse_clamped`). A bang is short, so the fireworks still measure −23.9 LUFS over their 12 s,
against −16.0 for the train crossing; their peaks are the evening's.

## Requirements

- **R1** One timeline, one bake, one render at default settings; the reverb is set in the scene
  (`tag.set_scene_settings`), so the command on the title page is the whole render.
- **R2** One clock: every event happens once, at its place in the town; a shot never restarts an
  action. What is far from a shot's camera is quiet or inaudible because it is far.
- **R3** The pass starts and ends with 0.2 s of silence and ends in black, so that it stands alone
  as the trailer after its title page is cut off (the assembly fades the trailer's first 8 frames
  in from black).
- **R4** Each feature has one moment where it is plainly heard, with its callout: distance and
  delay (`overview`, `fireworks`), occlusion (`street`, `corner`), Doppler (`street`, `crossing`),
  reverb (`corner`), cuts (every change of shot, most clearly into and out of `onboard`), moving
  listener (`onboard`), screen panning (`square`), rear cue (`square`).
- **R5** A bell strike or burst is received before the next cut or rings across it: no one-shot
  arrives within 0.3 s before a cut.
- **R6** The bursts stand above the roofs in the line of sight of the last camera, clear of the
  Fresnel zone (20 to 25° up, the roofs at 8 to 13°); the longest path is 380 m (1.1 s), inside the
  default bake padding of 3 s.
- **R7** Callouts name what is heard in plain words; they do not refer to other sections (C6).
- **R8** Stems per group (`ambience`, `music`, `bells`, `vehicles`, `people`, `railway`,
  `fireworks`, `reverb`) are written with the mix: they are the material for a re-edit.
- **R9** Level: integrated loudness −18 LUFS ± 2 with one static gain, true peak at most −1 dBTP.
- **R10** The numbers on screen are measured: the sources in the bake, the tag calls and their lines
  in `build.py`, and the render time under the card's claim.

## Known answers

Probes (`finale.probe.town.<name>`, group `probe`), tagged like the source they sit on; expected
values are computed from the baked positions and visibility. Measured values from `check.py`.

| What | Probe | Expected | Measured |
|---|---|---|---|
| Cuts in the report | | six, on frames 361, 691, 1021, 1321, 1561 and 1891 | the same |
| One-shots and cuts (R5) | | none arrives within 0.3 s before a cut | shortest 0.89 s |
| Bell onsets | click on the strike frames | strikes 1 to 3 from the drone 1.158 s late (397 m), the fourth from the square 0.276 s (95 m), ± 1 ms | within 0.08 ms |
| Bell level | the same, both channels' power | the fourth strike above the third, 250 Hz to 1 kHz: distance law and the engine's air absorption, 12.6 dB ± 1 | 12.0 dB |
| Ambulance pitch | 1 kHz sine on the light bar | from the geometry: 1057 Hz at 9.3 s, 950 Hz at 18.8 s, ± 0.5 %; through 1000 Hz at 14.22 s ± 0.03 | 1056.9, 950.3 Hz; 14.20 s |
| Ambulance behind the houses | pink noise, with and without `occlusion` (direct sound) | every steady 0.3 s window of the street shot against the baked visibility, ± 1.5 dB; hidden −12.1 / −13.6 / −21.1 dB at 250 Hz / 1 kHz / 4 kHz | max error 0.44 dB; hidden −12.2 / −13.7 / −20.9 dB |
| Ambulance's line of sight | baked visibility | in the open from 12.69 to 16.31 s (emission), the lane seen through the square's south side, ± 0.25 s | 12.90 to 16.30 s |
| Busker in `corner` | pink noise, with and without `occlusion` | against the baked visibility at 21 s (−8.4 / −12.0 / −22.1 dB: the 250 Hz band bends round the corner) and 30.5 s (−1.5 dB in all bands), ± 1.5 dB | −8.4 / −11.9 / −21.6; −1.5 dB |
| Busker in sight | baked visibility, 4 kHz band | half visible when the line from the camera passes the corner: 26.0 s ± 0.5 | 26.2 s |
| Busker's reverb | the same, `reverb` stem | unchanged by the occlusion (`obstruction`), ± 0.5 dB | 0.00 dB |
| Train horn in `crossing` | 1 kHz sine at the train's front | from the geometry: 1095.7 Hz at 31.3 s, 919.9 Hz at 40.7 s, ± 0.5 % | 1095.8, 919.8 Hz |
| Bell in `onboard` | 1 kHz sine at the second crossing's bell | 1087.4 Hz at 41.3 s, 912.6 Hz at 48.6 s, ± 0.5 %; through 1000 Hz at 45.51 s ± 0.03; 2.8 to 3.1 semitones | 1087.4, 912.6 Hz; 45.51 s; 3.04 |
| A sine on the train | 1 kHz sine under the locomotive | 1000.0 Hz ± 0.5 in the cab | 999.99 to 1000.02 Hz |
| Zoom in `square` | pink noise on the accordion (direct sound), 200 to 400 Hz | left over right from the screen pan law and the head shadow (`kit/hearing.py`): 1.84 dB at 24 mm, 5.52 dB at 70 mm, ± 0.7 dB | 1.86, 5.58 dB |
| Scooter behind the camera | pink noise, against a render with the rear cue off | at 54.01 s (rho 0.98), third octaves: −2.07 dB at 1 kHz, −8.08 dB at 12 kHz (the rear low-pass at the engine's oversampled rate), ± 0.7 dB | −2.07, −8.08 dB |
| Firework bursts | click on the flash frames | onsets at distance / c: 0.79 s (270 m) to 1.11 s (380 m), ± 1 ms; baked visibility at least 0.99 | all within 1 ms; 1.000 |
| Stems | | the eight groups of R8 | all eight |
| Loudness and peak | | −18 LUFS ± 2, at most −1 dBTP; first and last 0.2 s of the pass below −60 dBFS | −19.4 LUFS, −1.0 dBTP; silent |
| What the scene took (R10) | | 31 sources in the bake; render time under 15 s | 31; 13 calls in 21 lines; 5.2 s |

## Limits

One reverb for the whole pass: the drone, the square and the train's cab share `city_streets`.
Engines keep one speed: the ambulance and the train neither brake nor accelerate. The cab does
not muffle the outside (an object travelling with the camera does not occlude). Occlusion is graded
by the Fresnel zone: the busker around the corner is never fully hidden at 250 Hz, and he clears
gradually over the last 5 s of the walk.

## Needs ears

The whole section, as the last check of the showcase: whether a viewer who has seen nothing else
understands from picture and sound alone that the sound belongs to the scene. In particular the
balance: the overview opens quietly (about −27 LUFS: the town from 400 m), the crossing is
the loudest shot by loudness, and the fireworks, 270 to 380 m away, hit the peak ceiling with
each bang.

## What the scene took (R10)

Beside the drone's view (0.8 to 8.6 s) a panel lists the scene's `tag` calls as `build.py` has
them (each with its first two arguments; `section.tag_calls` reads them from the script's syntax
tree, probes left out): 13 calls. Over the fireworks' last echoes (71 to 74.5 s) a card gives the
numbers: 31 sources, 21 lines of Python to tag them, 75 s of sound rendered in under 15 s. The check
asserts the source count against the bake and the render time against the claim (5.2 s on an AMD
Ryzen 9 3950X, 24 threads).
