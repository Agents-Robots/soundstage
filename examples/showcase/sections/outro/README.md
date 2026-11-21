# `outro`: End card

The end card of the full video and of the trailer: what the project is, how it is used, where to
get it. It stands over a row of houses at night while fireworks burst to its right; their bangs
arrive one and a half seconds after the flashes, as in the speed-of-sound section.

| | |
|---|---|
| Length | 14 s (420 frames) |
| Set | a row of houses 90 m ahead with lit windows, trees and street lamps; night sky |
| Features | propagation delay, distance, the street's reverb, a bed |
| Reverb | `city_streets` |

## Card

No title page and no passes. The picture fades from black in frames 1 to 8 and to black in frames
413 to 420. A dark panel (88 % opaque) covers the left 74 % of the frame; the column is
left-aligned at 7 % from the left edge and ends at 70 %:

| Element | Content |
|---|---|
| Wordmark | `soundstage`, with the line "Offline spatial sound for Blender animations" |
| Three steps | "tag · bake · render", each with one line of code in monospace: `tag.add_sound(car, "engine.wav")`, `soundstage bake scene.blend --out bake/`, `soundstage render bake/scene.json -o mix.wav` |
| Statement | "Every sound in this video was rendered by soundstage from the Blender scenes shown." |
| Get it | "Get it" in amber, the repository's address (`github.com/Agents-Robots/soundstage`), and below it the install line `pip install git+https://github.com/Agents-Robots/soundstage` |
| Also | "Stems per group · loudness normalization · true-peak limiter · solo and mute · reverb presets and impulse responses" |
| Credits | "Recorded sounds:" and the authors from `sounds/sources.toml` and `sounds/animations.toml`; "all other sounds synthesized" |

## Scene and sound

| Time | Event |
|---|---|
| 0.3 to 13.3 s | the town's night bed (`town_bed.wav`, non-spatial, −22 dB), fading in and out over 1.5 s |
| 1.6, 4.0, 6.4, 8.6 s | a firework bursts 480 to 600 m away, 20 to 27° right of the view, 125 to 215 m up (the rocket rises for 1.2 s before) |
| 1.4 to 1.9 s after each burst | its bang arrives (`firework_bang_1..3.wav`, `ref_distance` 500 m) |

Section gain +4.5 dB. The loudness is reported, not checked (S2): single bangs over a quiet bed.

## Requirements

- **R1** The fireworks burst right of the panel, and the houses stand right of it too: the text has
  a dark, even background.
- **R2** The URL is one constant in the kit (`kit/story.py`, `REPO_URL`); the address and the install
  line are made from it. `pip install git+<URL>` installs a working `soundstage` command (scan,
  bake, render, preview; checked with a fresh venv, #49).
- **R3** The credits are read from `sounds/sources.toml` and `sounds/animations.toml` at build time; with
  no recorded sounds the line reads "All sounds synthesized".
- **R4** The code lines are valid: they are the commands of [docs/usage.md](../../../../docs/usage.md)
  and are compared with the CLI's argument parser at build time.
- **R5** The statement is true of the cut it closes: `assemble.py` refuses to append `outro` to a
  cut that contains a section whose sound was not rendered from its manifest.
- **R6** No reference to a section and no "thanks for watching": the card closes the trailer and
  the full video alike (C6).

## Known answers

| What | Expected | Measured |
|---|---|---|
| Each bang after its flash | the travel time from the bake's positions, ± 10 ms | 1.467 s (expected 1.465), 1.730 s (expected 1.727), 1.561 s (expected 1.558), 1.859 s (expected 1.857) |
| First and last frame | black | at most 1 of 255 |
| Text | inside the 5 % margin (the ink on the panel of the rendered middle frame); smallest cap height 2 % of the frame height (install line, also, credits) | the panel's ink from x 0.067 to 0.735 (the panel's edge), y 0.059 to 0.937 |
| Level | true peak at most −1 dBTP; first and last 0.2 s silent | −1.4 dBTP, −30.9 LUFS |

The kit checks every text's width at build time; the "Also" line breaks between items, never
before a separator. The manifest's title is "End card", the chapter name in a joined cut.
