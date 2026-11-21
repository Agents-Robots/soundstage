# `production`: In production

Two scenes from Blender animations that were not made for this showcase, with the sound soundstage
rendered for them: the race across the swamp, six racers at 612 km/h, whole as the animation cuts
it (it starts calm and builds to its end); and a drone flight around a party terrace in a city of
over two thousand flying cars, with the terrace's music and the neon signs on the towers.

| | |
|---|---|
| Length | 71.1 s (2133 frames) |
| Picture | the animations' own rendered frames (2.39:1, scaled to the width and centred on black), with the kit's overlays laid over them |
| Features | all, at the animations' settings |
| Reverb | as in the animations (`outdoors_valley` for the race, `city_streets` for the city) |

## Title page

| Element | Text |
|---|---|
| Title | In production |
| Claim | Scenes from two Blender animations, with the sound soundstage rendered for them. |
| Code chip | `soundstage render bake/scene.json -o mix.wav` |
| Listen for | six racers crossing a swamp at 612 km/h; music and neon signs around a tower in a city of flying cars. |

The title page lies over the race's first frame.

## Passes

| Pass | Frames | Label | Setting line | Animation frames | What is heard |
|---|---|---|---|---|---|
| `race` | 91–1323 (41.1 s) | Six racers at 612 km/h, half the speed of sound | from an animation: the swamp, 11 shots | the race, its swamp scene: 11 shots, race frames 3480–4707 (`RACE_SHOTS`, the animation's `data/cut_swamp.json`) | calm long shots of the pack over the water, two flybys (the second one, `flyby_omega` at 20.6 s, with the whine falling from about 2030 Hz to 680 Hz), then fast cuts close to the racers to the end |
| `metropolis` | 1324–2133 (27 s) | Over 2000 flying cars, music on the terraces | from an animation: 2200 sources | the city, drone shot, frames 361–1170 (12 to 39 s of the 120 s shot) | the drone heads for a party terrace and its music, circles the tower with the 未来へ neon sign, passes the king's statue and comes out over the canyon of flying traffic |

Every text of a scene shows in its first 9 s only and fades out: the scenes build to their ends.
Callouts at the upper right, from 1.5 to 9 s of each scene: "Passing at 612 km/h, a racer's whine
falls to a third" (race) and "27 s of sound, rendered in under a minute on 16 cores" (metropolis).

## Sound

| Pass | Source | Gain |
|---|---|---|
| `race` | the stems soundstage rendered in the animation's own mix of the scene (`out/audio/mix/film_full_stem_{engines,bed}.wav`, from 164.571 s of its time line): the racers (engines, whine, sub) and the air and water, at the levels the mix gives each shot. Left out: the score, the radio voices, the cheering recordings and the whooshes | +4 dB, then soundstage's true-peak limiter at −1 dBTP |
| `metropolis` | the animation's own render of frames 361–1170 from its bake (`--set master_gain_db=-5 --limit -1`, as its mix), music included | +2.5 dB |

The animation's mix steps the engines and the air back by 4 dB while the radio speaks; without the
voices those steps would be dips with no cause. Its gain curves (`film_full_curves.npz`) undo them:
where a stem's curve dips under the scene's median, the stem is lifted by the dip, at most 4 dB. The
two flybys then stand 10 dB over the rest of the scene; the animation holds them with its master
limiter, the excerpt with soundstage's (`mix.true_peak_limiter`, at most 2.9 dB for 1.1 s).

`steps.py` assembles the section: the race runs at 29.97 fps, so its 1233 frames are shown at 30 fps
and its sound is resampled by 1000/1001 (41.143 s to 41.102 s, 1.7 cents higher); the metropolis
render runs in the animation's project folder (`soundstage render`, skipped while the result is newer
than the bake); fixed gains per pass; 0.25 s fades where a scene is cut, and at the end a 1 s fade
followed by 0.25 s of silence (C5). The animations' project folders are machine-specific and named
in `sources.local.toml` next to this file (gitignored):

```toml
[projects]
race = "/path/to/the/race/animation/project"
metropolis = "/path/to/the/city/animation/project"
```

Recordings in the race's engines (credited on the end card, `sounds/animations.toml`): "F-16
startup idle" by ikbenraar (Freesound 322178) and "F-15 flyover" by klangfabrik (Freesound 324370),
both CC0, pitched and processed by the animation. The city's sounds, its music too, are all
synthesized.

## Picture

The race's frames come from its render folders (`RACE_RENDERS`: one folder per render of each pass of
its cut, named by date); each shot is taken from the newest render that has all of its frames, so a
new render replaces the old one shot by shot as it lands, never in the middle of a shot. `pan_swamp`
stands in the cut's second render pass. The shots (`RACE_SHOTS`) follow the animation's cut
(`data/cut_swamp.json` of 2026-11-14, `flyby_swamp` 10 beats from race frame 3719); after a recut, a
render holds other cameras at some frames, so the check compares the two.

## Requirements

- **R1** Only soundstage renders are heard: no score, no voices, no sound added in an animation's
  own mix (accents, whooshes, crowd recordings). The city's music is a source in its scene, rendered
  by soundstage.
- **R2** Picture and sound of a scene start on the same animation frame; the race's 29.97 fps is
  matched by resampling the sound, not by dropping frames.
- **R3** The callouts' numbers are measured: the whine's pitch before and after the pass, and the
  render time of the metropolis scene (load, culling and DSP from the render's report).
- **R4** The race is shown in the animation's current cut, from its newest render.
- **R5** No machine-specific path in a tracked file.

## Known answers

| What | Expected | Measured |
|---|---|---|
| race: whine coming / going in `flyby_omega` | (c + v) / (c − v) = 2.97 at 170 m/s, ± 0.15 (the animation's camera moves too) | 2030 / 679 Hz = 2.99 |
| race: whine coming | 1050 Hz × c / (c − v) × 1001/1000 = 2084 Hz ± 5 % | 2030 Hz |
| race: stems | engines and bed only | engines, bed; lifted by up to 4.0 dB under the voices |
| race: shots as the animation cuts them | camera, beats and first race frame of each of the 11 shots | 11 as cut |
| race: shots from the newest render | every shot | 11 of 11 (renders of 2026-11-15) |
| metropolis: groups in the render | `music` among them | ambience, cars, crowds, drone, foreground, lights, music, oldtown, reverb, signs |
| metropolis: sources | 2200 | 2200; 2066 in the far field |
| metropolis: render time of the 27 s | under 60 s on 16 cores (32 threads) | 51.6 s (AMD Ryzen 9 3950X) |
| level | metropolis −18 LUFS ± 2; true peak at most −1 dBTP | −18.3 LUFS (race −20.6 LUFS); −1.0 dBTP |

## Limits

The metropolis scene is rendered with the engine of this repository, which has changed since the
animation's mix was approved (#42, #43, #46): it differs from that mix in the level difference at
the sides (`ild_limit_db`) and slightly elsewhere. The race's stems are the animation's mix of
2026-11-21.

## Needs ears

Whether the race holds without its score, whether the undone steps under the radio sound natural,
and whether the scenes hold up next to the low-poly sections.
