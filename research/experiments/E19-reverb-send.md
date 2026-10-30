# E19: the reverb send over distance

**Question.** With thousands of sources, the reverb send's distance law decides how loud the
reverberation is: with the EFX convention (room rolloff 0, the classical diffuse field), every source
sends the same, however far it is. How do the EFX law, the EFX law with room rolloff 1 (the send
follows the direct sound) and the revised law of [ADR 0014](../../docs/adr/0014-reverb-send-falls-with-distance.md)
(Barron and Lee within the listener's space, spherical spreading beyond, [model](../models/reverb.md))
compare, analytically and on dense traffic? And does the far field's send, now split into distance
bands with their air absorption, match the full chain's?

## Setup

`e19_reverb_send.py`:

1. The revised law per preset, from its mid-frequency decay time `T`: the radius
   `R = c T / ln(1000)` and the send level at 10 m to 3 km.
2. Sources spread evenly over a plane around the listener out to a radius D (traffic in a city):
   the reverberant energy (the sum of the squared send gains) and the direct energy (inverse
   distance, reference 8 m) as D grows from 100 m to 10 km.
3. Renders of the E18 traffic scenes ([E18](E18-traffic.md): cars on 24 lanes in a 3 km canyon,
   60 s, one engine hum per car at reference distance 8 m) with the `city_streets` reverb
   (`T` 1.79 s) at `detail_voices` 64, 2000 and 10 000 cars, for the three laws: loudness of the
   cars stem and of the reverb return, the share of the send energy from cars beyond 100 m and
   1 km (from the baked distances, every car's loop playing throughout), render time and memory,
   on a 16-core node.
4. The reverb return per octave band with the far field (`detail_voices` 64) against every car in
   the full chain (null), 1000 cars, EFX law (constant send: the far cars send the most). "Before":
   the far field of c81a028, whose send was one mono signal without air absorption; "after": one
   send bus per distance band, filtered by the band's air absorption.

## Results: the law

| preset | T60 (s) | R (m) | 10 m | 30 m | 100 m | 300 m | 1000 m | 3000 m |
|---|---|---|---|---|---|---|---|---|
| livingroom | 0.50 | 25 | -3.5 | -10.3 | -20.8 | -30.3 | -40.8 | -50.3 |
| concerthall | 3.92 | 195 | -0.4 | -1.3 | -4.5 | -12.4 | -22.9 | -32.4 |
| city_streets | 1.79 | 89 | -1.0 | -2.9 | -9.7 | -19.3 | -29.7 | -39.3 |
| forest | 1.49 | 74 | -1.2 | -3.5 | -11.3 | -20.8 | -31.3 | -40.8 |
| hangar | 10.05 | 499 | -0.2 | -0.5 | -1.7 | -5.2 | -14.7 | -24.3 |
| mountains | 1.49 | 74 | -1.2 | -3.5 | -11.3 | -20.8 | -31.3 | -40.8 |

Send level in dB of the revised law (the EFX law: 0 dB at every distance for these presets).

Sources spread evenly over a plane out to D, energy relative to D = 100 m (dB), `city_streets`:

| D | EFX | EFX, room rolloff 1 | revised | direct |
|---|---|---|---|---|
| 300 m | +9.5 | +1.3 | +2.8 | +1.3 |
| 1000 m | +20.0 | +2.5 | +4.6 | +2.5 |
| 3000 m | +29.5 | +3.3 | +5.8 | +3.3 |
| 10000 m | +40.0 | +4.0 | +6.8 | +4.0 |

With the EFX law the reverberation grows with the area the sources cover (20 dB per decade of
radius), while the direct sound grows by the log of the radius: the farther the traffic reaches,
the more the reverberation takes over. With room rolloff 1 or the revised law the reverberation
grows like the direct sound.

## Results: dense traffic

| cars | law | cars stem (LUFS) | reverb return (LUFS) | cars − reverb (LU) | master (LUFS) | send from > 100 m | > 1 km | time (s) | memory (GB) |
|---|---|---|---|---|---|---|---|---|---|
| 2000 | EFX | -10.0 | +2.8 | -12.9 | +3.1 | 94 % | 38 % | 81 | 19.3 |
| 2000 | EFX, room rolloff 1 | -10.0 | -25.4 | 15.3 | -9.9 | 28 % | 1 % | 81 | 19.4 |
| 2000 | revised | -10.0 | -14.0 | 3.9 | -8.5 | 34 % | 1 % | 81 | 19.5 |
| 10 000 | EFX | -3.9 | +9.8 | -13.7 | +10.0 | 94 % | 38 % | 194 | 17.4 |
| 10 000 | EFX, room rolloff 1 | -3.9 | -18.4 | 14.5 | -3.7 | 28 % | 1 % | 200 | 17.4 |
| 10 000 | revised | -3.9 | -7.0 | 3.1 | -2.2 | 34 % | 1 % | 234 | 17.5 |

(The scene has no limiter or master gain: the absolute levels are those of 2000 and 10 000 engine
hums; compare the laws within one size.)

- With the EFX law the reverb return is 13–14 LU louder than the cars themselves, and 94 % of what
  feeds it comes from cars more than 100 m away (38 % from beyond 1 km): the master is reverb.
- Room rolloff 1 puts the reverb 15 LU below the cars: dry, also for the close passes.
- The revised law puts it 3–4 LU below the cars; a third of the send comes from beyond 100 m and
  1 % from beyond 1 km. The close cars keep most of their reverberation (−1 dB at 10 m, −2.9 dB at
  30 m), the distant ones lose it.
- The law does not change the render time at 2000 cars (81 s each); at 10 000 the three renders took
  194, 200 and 234 s on the same node.

## Results: the far field's send

Reverb return per octave band, far field (`detail_voices` 64) minus every car in the full chain
(dB), 1000 cars, EFX law, and the render time at 64:

| | 63 Hz | 125 Hz | 250 Hz | 500 Hz | 1 kHz | 2 kHz | 4 kHz | 8 kHz | 16 kHz | time (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| level of the full chain's return (dB re loudest) | 0 | -4 | -9 | -24 | -45 | -36 | -38 | -58 | -75 | |
| before (c81a028) | -0.0 | +0.3 | +0.4 | +1.0 | +11.1 | +8.3 | +10.4 | +24.8 | +41.0 | 61 |
| after | -0.1 | +0.2 | +0.0 | -0.2 | +5.2 | +1.2 | -0.0 | +0.0 | +10.2 | 66 |

Without air absorption on the far cars' sends the reverb return was 8–25 dB too bright from 2 to
8 kHz. With the send per band it matches the full chain within 0.2 dB up to 8 kHz in the octaves
that carry energy. The two remaining differences are in octaves 45 and 75 dB below the loudest: the
engine hum has a dip at 1 kHz that the far field's loop reading fills a little (the far field reads
one unpitched loop cycle per sample at each car's pitch, E18), and at 16 kHz there is next to
nothing. The 64 render took 66 s against 61 s before (+8 %), with the new air filters and the
send buses together.

## What to take from it

- For a few sources in one room the EFX law is right; for sources spread over a large or open
  space it is not: the reverberation then grows with the area and swamps the direct sound.
- The revised law keeps the reverberation of the close sources and lets the distant ones fall
  away, at no measurable cost; room rolloff 1 also bounds the reverb but makes the close sources
  dry. Which balance sounds right for a shot is a listening judgement: a 2200-source city shot was
  rendered with both for a listening comparison.
- The far field's reverb send now carries the same air absorption as the full chain's.

## Reproduce

The renders take about 25 minutes on a 16-core node and need the E18 scenes
(`e18_traffic.py run bake`). "Before" needs a checkout of c81a028:

```bash
git worktree add /tmp/c81a028 c81a028
.venv/bin/python research/experiments/scripts/e19_reverb_send.py run --tag before --checkout /tmp/c81a028
.venv/bin/python research/experiments/scripts/e19_reverb_send.py run
.venv/bin/python research/experiments/scripts/e19_reverb_send.py analyse
```
