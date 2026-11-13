# `distance`: Distance

Sound gets quieter with distance, and duller: the level falls 6 dB with every doubling, and the
air absorbs the high frequencies first. An open-air stage is heard from five places, each half as
far away as the one before.

| | |
|---|---|
| Length | 40.5 s (1215 frames) |
| Set | a field with a stage, day |
| Features | distance model, air absorption (ISO 9613-1), propagation delay |
| Reverb | none |

## Title page

| Element | Text |
|---|---|
| Title | Distance |
| Claim | Sound gets quieter with distance, and duller: air absorbs the high frequencies first. |
| Code chip | `distance_model = "inverse_clamped"   air_absorption = 1.0` |
| Listen for | the level at each camera position, and the hi-hats that only arrive close up. |

## Scene

A flat field with an open-air stage: roof, two loudspeaker towers, lights that flash on the beat,
a crowd of figures in front (picture only). The music is one source at the middle of the stage
front, 4 m high.

Five cameras stand on a straight line in front of the stage, 3 m high, all with a 50 mm lens,
aimed at the stage:

| Camera | Distance | Delay | Level (inverse law) | Air loss at 4 kHz | at 8 kHz |
|---|---|---|---|---|---|
| 1 | 686 m | 2.000 s | −24.1 dB | 20.4 dB | 72 dB |
| 2 | 343 m | 1.000 s | −18.1 dB | 10.2 dB | 36.1 dB |
| 3 | 171.5 m | 0.500 s | −12.0 dB | 5.1 dB | 18.1 dB |
| 4 | 85.75 m | 0.250 s | −6.0 dB | 2.5 dB | 9.0 dB |
| 5 | 42.875 m | 0.125 s | 0 dB | 1.3 dB | 4.5 dB |

A pass shows the five cameras in this order, 2.5 s (75 frames) each, with hard cuts. The stage
grows in the frame from a speck to a full view.

## Passes

| Pass | Frames | Chip | Label | Setting | What is heard |
|---|---|---|---|---|---|
| `none` | 91–465 (12.5 s) | WITHOUT | No distance model | `distance_model="none"`, `air_absorption=0` | the same level and timbre at every camera: wrong, most of all at 686 m |
| `inverse` | 466–840 (12.5 s) | | Inverse distance law: −6 dB per doubling | `distance_model="inverse_clamped"`, `air_absorption=0` | 6 dB louder at every cut, the timbre unchanged |
| `air` | 841–1215 (12.5 s) | WITH | Plus air absorption | defaults | as before, and at 686 m only kick and bass arrive; the snare gains its crack and the hi-hats come in as the camera gets closer |

## Sounds

| Source | Sample | Tag |
|---|---|---|
| `distance.<pass>.music` | `drum_loop.wav` | loop, `ref_distance=42.875`, `loop_phase=0`, `loop_crossfade=0`, group `music`, and the pass's `distance_model` and `air_absorption`; starts 75 frames before its pass; its 0.4 s fade-out has ended 0.35 s before the pass ends, so the nearest camera hears silence in the last 0.225 s |

Section gain +4 dB: the reference pass `air` is at −19.4 LUFS. The peak limit sets the gain: `none`
plays the music at full level at every camera and peaks at −1.1 dBTP (S2).

## Picture aids

- A distance read-out per camera ("686 m", upper right), and from `inverse` on a level gauge at
  the right with marks at 0, −6, −12, −18 and −24 dB; each camera's needle stands at its level, so
  it jumps at each cut.
- `air`: a band strip at the upper left (eight bands from 125 Hz to 16 kHz) showing the expected
  loss per band at the camera's distance, ISO 9613-1 at the band's centre, down to 60 dB. The
  build computes it with the same formula as the engine (`section.air_alpha_db_per_m`); the check
  compares the two.
- The stage lights flash on the kick drum (at emission time).

## Requirements

- **R1** One source for the music. Two loudspeaker towers playing the same loop would cancel and
  reinforce each other differently at each camera.
- **R2** Cuts, not a flight: a camera flying 643 m in 12.5 s would raise the music by 2.6
  semitones.
- **R3** The loop is one bar of exactly 2 s and the distances are 2 s, 1 s, 1/2 s, 1/4 s and 1/8 s
  of travel, so the music stays in time across every cut although each camera hears it later.
- **R4** The music starts 75 frames before each pass, so that it has reached the farthest camera
  (2 s) when the pass begins.
- **R5** The reference distance is the nearest camera's distance: the last view plays at the
  sample's level, the first 24 dB below it. No gain rides in between.
- **R6** The loop has clear content at both ends of the spectrum: kick and bass below 150 Hz,
  hi-hats between 8 and 12 kHz.
- **R7** Air at 20 °C and 50 % humidity (defaults).

## Known answers

Probes on the music's emitter, tagged like the music: pink noise (`distance.probe.<pass>.noise`,
`loop_phase=0`) and a click every 2 s from the music's start (`distance.probe.<pass>.click`).
Levels are measured from 0.4 to 1.9 s into each shot (away from the cuts and the fade-out), each
relative to the part of the noise sample that camera hears (emitted d / c earlier), so that the
noise's own fluctuation does not count. The air's loss in an octave band is compared with ISO
9613-1 over the band, weighted by the probe's spectrum: in an octave the loss is not the
pure-tone value at its centre (at 686 m, 8 kHz: −72 dB as a tone, −48.8 dB over the octave).

| What | Expected |
|---|---|
| Camera distances (baked) | 686, 343, 171.5, 85.75, 42.875 m, ± 1 cm |
| `none`: probe level at the five cameras | equal within 0.1 dB |
| `inverse`: probe level relative to camera 5 | −24.08, −18.06, −12.04, −6.02, 0 dB, ± 0.3 dB |
| `air` minus `inverse`, octave band at 1 kHz | −3.2, −1.6, −0.8, −0.4, −0.2 dB, ± 0.5 dB |
| `air` minus `inverse`, octave band at 4 kHz | −17.5, −9.5, −5.1, −2.6, −1.3 dB, ± 1.5 dB |
| `air` minus `inverse`, octave band at 8 kHz | −48.8, −27.1, −15.2, −8.4, −4.5 dB, ± 2 dB |
| Click arrival after emission | 2.000, 1.000, 0.500, 0.250, 0.125 s, ± 1 ms |
| Playback rate | 1.000 in every shot (no Doppler across the cuts) |
| Band strip | ISO 9613-1 coefficients equal to the engine's |

The cut from camera 5 to camera 1 at the start of each pass goes back 1.875 s in emission time:
what camera 1 hears first was emitted while camera 5 was the listener. It is filtered for camera 1
because each segment between cuts has its own emission-side filters (issue #43, found here).

## Limits

The ground does not reflect and the air does not refract: real open-air sound over 700 m also
depends on wind and temperature layers.

## Needs ears

Whether the first view of `air` (24 dB down, no highs) is still audible enough on small speakers,
or whether the section gain has to favour it.
