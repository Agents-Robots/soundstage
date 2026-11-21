# Feature showcase

A video of about five minutes that shows one feature of SoundStage at a time, with simple shapes and
synthetic sounds (sine, white and pink noise, clicks, bursts). Each chapter is a title card followed
by passes: the same action again with one thing changed (feature off, on, and sometimes
exaggerated), with a label naming the pass. Objects light up while they sound. Listen on
headphones.

This is the first version. The second one is specified in [`sections/README.md`](sections/README.md):
one folder per section, scenes from everyday life (an ambulance, a race, a busker around a corner)
with recorded and synthesized sounds ([`sounds/README.md`](sounds/README.md)), each section built
and rendered on its own and joined afterwards. The scripts below stay until that replaces them.
The second version runs through `showcase.py`:

```bash
.venv/bin/python examples/showcase/showcase.py sounds                 # make.py and fetch.py -> out/showcase/sounds
.venv/bin/python examples/showcase/sounds/audition.py                 # audition clip of the sounds
.venv/bin/python examples/showcase/showcase.py all intro sources      # build, bake, audio, check per section
.venv/bin/python examples/showcase/showcase.py frames intro --percent 50 --samples 16
.venv/bin/python examples/showcase/showcase.py preview intro          # out/showcase/intro/intro_preview.mp4
.venv/bin/python examples/showcase/assemble.py trailer                # out/showcase/cuts/trailer.mp4 (cuts.py)
```

`production` shows scenes from two animations whose projects live outside this repository: name their
folders in `sections/production/sources.local.toml` (gitignored, see its README) before its audio
and frames steps. `city` has 10 000 cars: its bake takes about 40 min, its sound about 3 min and 14 GB on a
16-core CPU.

| File | What it is |
|---|---|
| `storyboard.py` | Chapters, passes, labels, durations and per-pass render settings: the one description both scripts read |
| `build.py` | Builds the .blend in Blender: one stage per chapter, cameras switched by markers, titles and labels, radar, sound tags |
| `audio.py` | Renders every pass on its own (its frames, its sounds, its settings) and places them in one mix |
| `check.py` | Known-answer checks on the pass renders |

## Commands

```bash
.venv/bin/python tools/make_test_samples.py                     # samples/, incl. the white-noise ones
blender -b --factory-startup --python examples/showcase/build.py -- --save out/showcase/showcase.blend
.venv/bin/soundstage bake out/showcase/showcase.blend --out out/showcase/bake        # about 3 min
.venv/bin/python examples/showcase/audio.py                     # out/showcase/showcase.wav, about 1 min
.venv/bin/python examples/showcase/check.py                     # known answers per pass
```

`build.py` sets up Cycles (64 samples, denoised) at 1920×1080, 30 fps; `--engine BLENDER_EEVEE`,
`--resolution`, `--percent` and `--samples` change that. The tags are set by the build script and
saved in the .blend, so the bake needs no `--run`. Render the frames (frames 1 to the end, see
`python examples/showcase/storyboard.py`) on the farm, then mux:

```bash
.venv/bin/soundstage preview out/showcase/showcase.wav --video <rendered video> --width 0 -o out/showcase/showcase.mp4
.venv/bin/soundstage preview out/showcase/showcase.wav --frames <frames dir>    # from an image sequence
```

`showcase.report.json` next to the mix carries the first frame and the fps that `preview` reads,
plus loudness and peaks of the mix and of every pass. `out/showcase/passes/` holds each pass as
its own WAV with report and debug plot (and its reverb return): useful to compare two passes
directly.

## Why one render per pass

Settings such as the panner, the rear cue, the reverb or the screen reference apply to a whole
render, not to one source. `audio.py` therefore renders each pass alone (`--frames` of the pass,
`--solo <chapter>.<pass>.*`, `--set` from the storyboard) and adds the renders at their frames.
Per-source keys (Doppler, air absorption, distance model, cones, occlusion, sync to picture, loop
phase, pitch) need no override: the object carries one tag entry per pass, limited to the pass with
`frame` / `end_frame` or trigger frames. Every pass starts and ends in silence, so the renders do
not overlap. There is no normalization or limiter: it would even out the level differences the
passes show.

## Chapters and what to listen for

| # | Chapter | Picture | Passes: listen for |
|---|---|---|---|
| 1 | Sound sources | A humming cube; a bouncing ball; three cubes; a ticking sphere while the camera pans | the loop fades in and out; one beep per contact; the same 1 kHz loop at 500, 1000, 2000 Hz; the stereo bed stays put while the ticks move to the right |
| 2 | Distance attenuation | A sphere steps from 2 to 64 m, past labelled posts (Doppler off) | none: same level throughout; inverse: 6 dB quieter at each post |
| 3 | Stereo panning | A sphere swings left and right in front of the camera | the level difference follows the sphere (amplitude panner) |
| 4 | Screen-relative panning | Two shapes at ±8.5°; the camera zooms from 24 to 105 mm | camera reference: the pips stay where they were; screen reference: they move outwards with the image |
| 5 | Propagation delay | Blocks drop on pads 34, 172 and 343 m away; the radar shows the wavefront | physical: the impact comes 0.1, 0.5 and 1.0 s after the flash; synced: on the flash |
| 6 | Doppler | A sphere passes 10 m away at 34.3 m/s with a 1 kHz tone | 0: no pitch change; 1: 1111 Hz to 909 Hz; 2: about 1220 to 820 Hz |
| 7 | Air absorption | Noise bursts from pillars at 10, 100, 300 and 600 m (distance attenuation off) | off: four identical bursts; on: each duller than the last |
| 8 | Ear model | A sphere circles the camera at 5 m; the radar shows where it is | amplitude only; with time difference and head shadow, the sound is placed more clearly, also behind; full strength exaggerates it |
| 9 | Rear cue | Same orbit, pink noise | off; default: slightly quieter and duller behind; strong: clearly so |
| 10 | Directivity | A horn turns once on a turntable | omni: steady; cone: loud while it faces the camera, 24 dB down while it faces away |
| 11 | Occlusion | A sphere passes behind a glass wall | off: steady; on: muffled while behind the wall |
| 12 | Reverb | A ball bounces; then it hops away from 3 to 60 m | dry, room, alley, concert hall: longer tails; hopping away: the direct sound fades, the reverb stays |
| 13 | Camera cuts | Two cameras on a moving cube, a cut every 2 s | level and side switch at the cut, no pitch glide or click |
| 14 | Loop phase | Eight cubes play the same loop | in step: one loud, phasey source; random: a broader, even sound |
| 15 | All together | A ship passes behind a wall, a beacon, a ball, a bed, in an alley | everything at default settings |

## Left out

- Loudness normalization, true-peak limiter, stems, solo and mute: mix tools; nothing to see.
- Quality modes and sample rate: built to make no audible difference.
- Culling and far field: built to be inaudible (they make large scenes fast).
- Speaker objects and instances: other ways to create sources, not other sounds.
- Variations, animated parameters, binaural and ambisonic output: not implemented yet.
