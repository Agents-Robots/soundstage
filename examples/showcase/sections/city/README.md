# `city`: Ten thousand cars

A city at blue hour with ten thousand cars on its streets, each with an engine and tyres: 20 000
sources. A drone comes down from 320 m above the city into the boulevard and stops on its median;
the sound turns from the roar of a whole city into single cars passing on both sides. The near
cars get the full processing chain, the thousands far away one physical far field
([ADR 0013](../../../../docs/adr/0013-two-render-tiers.md)), and the sound of the 30 s pass renders
in about three minutes on one 16-core CPU.

| | |
|---|---|
| Length | 33 s (990 frames) |
| Set | a grid city 2.4 km across: avenues along X every 120 m, streets along Y every 120 m, the boulevard along X at y = 0; 2433 buildings (taller in the middle and along the boulevard), lit windows, lamps along every road; lanes run on to ±1.8 km into the dark land around it |
| Features | far field (`detail_voices`), culling (`cull_db`), instances at scale (`instance_limit = 0`), Doppler from the listener's motion, occlusion by the buildings |
| Reverb | none |

## Title page

| Element | Text |
|---|---|
| Title | Ten thousand cars |
| Claim | Every car has its own engine and tyres: the near ones in full detail, the rest in one physical far field. |
| Code chip | `detail_voices = 64   cull_db = -40` |
| Listen for | a whole city from above, turning into single cars passing by. |

## Scene

**Traffic.** 10 000 vehicles, each an instance of one of 24 collections (six variants, four
distance bands): four car colours and two trucks (8 %). Right-hand traffic on 110 lanes: the
boulevard has three lanes each way at 60 to 80 km/h, the avenues two each way at 45 to 60 km/h,
the streets one each way at 30 to 45 km/h. The streets within ±480 m of the camera's end position
carry no traffic: vehicles do not stop at junctions, and the camera would see them cross the
boulevard's traffic. In each lane every vehicle is at least as fast as the one behind it; the
closest two of a lane are 14.7 m apart (front to front). Speeds are constant, from before the
timeline into the padding (linear extrapolation), so the sound heard at the start left the far
cars at their speed.

**Drone.** A cubic Bezier from (−420, −160, 320) to (−40, 0, 2.2) over 26 s, eased at both ends,
then standing on the median. It lines up over the boulevard while still above the roofs (160 m at
12 s) and comes down between the boulevard's buildings; `build.py` stops if it comes within 3 m of
a building. Top speed 29 m/s (105 km/h): the first version flew 160 m/s and raised the pitch of the
whole city by up to half an octave. It looks at the middle of the city, then along the boulevard.
24 mm.

**Light.** Lit windows are a procedural pattern on the walls (3.2 m bays, 3.6 m storeys, about 40 %
lit, per building); street lamps are glowing dots every 30 m along every road; each car carries its
lights, a faint pool of light on the road ahead and a red glow behind (what shows a car from
300 m). On the median, real lamps every 30 m near the camera.

## Passes

| Pass | Frames | Label | Setting | What is heard |
|---|---|---|---|---|
| `night` | 91–990 (30 s) | Each car an engine and tyres: 20 000 sources | default settings | from above, the city's traffic as one wide roar, duller and darker with distance; coming down, single streets and then single cars; on the median, cars passing close on both sides, approaching ones higher, receding ones lower |

Read-out at the upper right: "10 000 cars". Callout from 20 to 28.5 s: "Sound rendered in under 6
minutes on one 16-core CPU".

## Sounds

| Source | Sample | Tag |
|---|---|---|
| `city.night.vNNNNN/…:0` (10 000 engines) | `car_engine.wav` | loop at the front (trucks: the cab), `pitch` 0.9, 1.0, 1.1, 1.2 (cars) or 0.55, 0.65 (trucks, +3 dB), `ref_distance=8`, `loop_phase="random"`, group `traffic` |
| `city.night.vNNNNN/…:1` (10 000 tyres) | `tyre_noise.wav` | loop at the rear axle, `ref_distance=8`, group `traffic` |

The loops play from before the timeline (no `frame`) and end by distance band, as in `scale`: the
farther a vehicle's band from the camera's end position (300, 800, 1600 m and beyond), the earlier
its loops end and the longer they fade (0.5 to 3 s), so that every vehicle's faded end has reached
the camera 0.3 s before the pass ends. The bake pads 6 s: sound from the farthest car (2.6 km,
7.6 s) heard at the pass's first frame left it 4.6 s before the timeline starts. Section gain
−7 dB: on the median the cars are 15 dB louder than the city from above.

## Requirements

- **R1** One tag per collection: the 10 000 vehicles are instances (one empty each), and
  `instance_limit = 0` keeps every one.
- **R2** The vehicles do not occlude (`sfx_occluder = False` on their collections); every building
  is its own box and does.
- **R3** The camera never enters a building (checked at build time).
- **R4** The numbers on screen are the bake's: 10 000 cars, 20 000 sources.
- **R5** One car's sound is measured among all the others: a 1 kHz probe rides on the westbound
  boulevard car that passes the camera's end position at about 26.5 s.
- **R6** No two vehicles of a lane come closer than 12 m.
- **R7** The callout's render time is measured: the pass's render time in the section's report,
  on a 16-core CPU (32 threads), under 6 minutes.

## Known answers

| What | Expected | Measured |
|---|---|---|
| Sources in the bake | 10 000 instancers, 20 000 sources; no instances dropped | 10 000, 20 000; none dropped |
| Padding for the pass's first frame | at most 6 s | needs 4.62 s (travel 7.62 s, title page 3 s) |
| Probe car, approaching from afar / close / going away | 1000 Hz × the Doppler factor from the baked positions, ± 0.2 % | 1073.3 / 1063.9 / 947.8 Hz, each within 0.4 Hz of expected |
| Far field | sources in the far field (reported) | 20000 of 20000, near voices at once up to 110; 83 % of source samples baked with the direct path only |
| Playback rate / pitch | within the Doppler bound of the camera's and the cars' top speeds | 0.872 to 1.155 (bound 0.859 to 1.160) |
| Render time of the pass | under 360 s on 16 cores | 167 s (AMD Ryzen 9 3950X), peak memory 14165 MB |
| Level | −18 LUFS ± 2; true peak at most −1 dBTP | −16.7 LUFS; −1.23 dBTP |

## Limits

Vehicles drive at constant speeds and pass through each other at junctions far from the camera
(none near it). The far field has no ITD, head shadow or rear cue; with 64 near voices per group
that is below what other random loop phases change ([E18](../../../../research/experiments/E18-traffic.md)).

## Needs ears

Whether the city from above sounds like traffic or like noise, and whether the swell to the
median is too much.
