# `delay`: Speed of sound

Sound travels at 343 m/s: three seconds per kilometre. Every source is delayed by its distance, so
a hammer across a lake is seen before it is heard, and thunder follows the lightning. Where the
edit needs a sound on its frame, one setting puts it there.

| | |
|---|---|
| Length | 35 s (1050 frames) |
| Set | a lake shore, dusk turning to night |
| Features | propagation delay, `sync_to_picture`, air absorption over long distances |
| Reverb | none |

## Title page

| Element | Text |
|---|---|
| Title | Speed of sound |
| Claim | Sound travels at 343 m/s: three seconds per kilometre. Every source is delayed by its distance. |
| Code chip | `sync_to_picture = False` |
| Listen for | the gap between seeing and hearing: the farther away, the later. |

## Scene

The camera stands on the shore of a lake and looks across the water. On the far side:

| Event | Distance | Delay | Seen as |
|---|---|---|---|
| A carpenter on a jetty hammers a post, three hits | 171.5 m | 0.5 s (15 frames) | the hammer coming down; a ring flashes at the hit |
| Fireworks from a raft, three bursts | 514.5 m, 686 m, 514.5 m | 1.5 s, 2.0 s, 1.5 s (45, 60, 45 frames) | the burst opening |
| Lightning over the hills | 1029 m | 3.0 s (90 frames) | the flash, lighting the scene for 3 frames |

Two cameras stand at the same place, 1.6 m high: a 300 mm lens on the carpenter, and a 28 mm lens
for the fireworks and the lightning. The cut between them changes the picture only.

Every event is placed at its distance from the camera exactly (`section.place`): the hammer's post
8.5° left of straight ahead, 1.35 m up; the bursts 20°, 9° and 29° right at 110, 150 and 95 m up,
each above a raft; the thunder's source halfway along the bolt, 3° left and 250 m up. A work light
on the jetty lights the carpenter at dusk.

Times from the start of a pass:

| Time | Event | Arrives (physical) |
|---|---|---|
| 0.4, 1.2, 2.0 s | hammer hits (300 mm) | 0.9, 1.7, 2.5 s |
| 2.9 s | cut to 28 mm | |
| 3.2, 4.4, 5.6 s | bursts at 514.5, 686, 514.5 m | 4.7, 6.4, 7.1 s |
| 8.0 s | lightning | 11.0 s, thunder until 15.5 s |

## Passes

| Pass | Frames | Label | Setting | What is heard |
|---|---|---|---|---|
| `physical` | 91–570 (16 s) | Sound travels at 343 m/s | default | every event late by its distance: half a second for the hammer, three for the thunder |
| `synced` | 571–1050 (16 s) | Synced to the picture | `sync_to_picture=True` on every event | every event on its frame, with the level and timbre of its distance |

No state chip: both are choices. `physical` is the default.

## Sounds

| Source | Sample | Tag |
|---|---|---|
| `delay.<pass>.hammer` | `hammer_hit.wav` | once, 3 frames, `ref_distance=100` (its peak within 5 dB of the bursts' and the thunder's) |
| `delay.<pass>.burst_1` … `_3` | `firework_bang_1.wav` … `_3.wav` | once, `ref_distance=250` |
| `delay.<pass>.thunder` | `thunder.wav` | once, `ref_distance=400` |

Scene setting for the bake: `pad_seconds=4` (the default 3 s covers 1 km, without margin).

Section gain +10.5 dB: −17.9 LUFS in both passes, true peak −2.9 dBTP.

## Picture aids

- A ruler above the lower third (kit `travel_ruler`): the camera at the left end, marks at 343 m
  ("1 s"), 686 m ("2 s") and 1029 m ("3 s"), a tick at each event's distance. In `physical`, a dot
  leaves the event's tick on its frame, moves at 343 m/s and reaches the camera on the frame the
  sound arrives; a counter above it shows the seconds on the way in 0.1 s steps, and the exact
  time for 0.6 s after it arrives.
- In `synced` the dot is at the camera on the event's frame.
- Every event has a mark in the picture on its frame (P1).

## Requirements

- **R1** The distances are whole frames of travel (15, 45, 60, 90), so that picture, ruler and
  sound agree to the frame.
- **R2** Each event is visible when it happens: the carpenter fills a sixth of the frame height
  through the 300 mm lens; bursts are 60 m across; the flash lights the whole scene.
- **R3** In both passes every event has arrived, and its sound has ended, before the pass ends;
  the hammer hits arrive before the cut at 2.9 s (a synced one-shot must be received before the
  next cut).
- **R4** The reference distances make the three kinds of event similar in level at the camera:
  what differs is the delay.
- **R5** The two passes differ in `sync_to_picture` only.

## Known answers

Probes: a click on every event's frame and emitter, tagged like the event
(`delay.probe.<pass>.<event>`).

| What | Expected |
|---|---|
| `physical`: click onset after its frame | 0.500 s (hammer), 1.500, 2.000, 1.500 s (bursts), 3.000 s (lightning), ± 1 ms |
| `synced`: click onset after its frame | 0, ± 1 ms |
| Click level and spectrum, `synced` against `physical` | equal within 0.1 dB |
| Thunder: loss in the 4 kHz octave from the air (click with and without `air_absorption`) | ISO 9613-1 over the octave, −23.9 dB, ± 2 dB (a pure 4 kHz tone loses 30.5 dB: 29.67 dB/km over 1029 m) |
| Bake | no warning about the padding |

## Limits

One arrival per event: no echo from the hills and no reflection from the water.

## Needs ears

Whether the synthesized bursts and the thunder are convincing, and whether the half second of the
hammer reads as distance and not as a sync error.
