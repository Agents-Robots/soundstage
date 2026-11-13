# `outro`: End card

The end card of the full video and of the trailer: what the project is, how it is used, where it
is. Silent.

| | |
|---|---|
| Length | 8 s (240 frames) |
| Set | none (the kit's background colour) |
| Features | none shown; names the ones that have nothing to see or hear |
| Reverb | none |

## Card

No title page and no passes. One still card; the picture fades from black in frames 1 to 8 and to
black in frames 233 to 240. Left-aligned column as on the title pages:

| Element | Content |
|---|---|
| Wordmark | `soundstage`, with the line "Offline spatial sound for Blender animations" |
| Three steps | "tag · bake · render", each with one line of code in monospace: `tag.add_sound(car, "engine.wav")`, `soundstage bake scene.blend --out bake/`, `soundstage render bake/scene.json -o mix.wav` |
| Statement | "Every sound in this video was rendered by soundstage from the Blender scenes shown." |
| Also | "Stems per group · loudness normalization · true-peak limiter · solo and mute · reverb presets and impulse responses" |
| Where | the repository's URL |
| Credits | "Recorded sounds:" and the authors from `sounds/sources.toml`; "all other sounds synthesized" |

## Requirements

- **R1** The sound is digital silence for all 240 frames.
- **R2** The URL is one constant in the kit (`kit/story.py`, `REPO_URL`). While it is empty (the
  repository is not public), the "Where" line is left out and the column closes up.
- **R3** The credits are read from `sounds/sources.toml` at build time; with no recorded sounds
  the line reads "All sounds synthesized".
- **R4** The code lines are valid: they are the commands of [docs/usage.md](../../../../docs/usage.md)
  and are compared with the CLI's argument parser at build time.
- **R5** The statement is true of the cut it closes: `assemble.py` refuses to append `outro` to a
  cut that contains a section whose sound was not rendered from its manifest.
- **R6** No reference to a section and no "thanks for watching": the card closes the trailer and
  the full video alike (C6).

## Known answers

| What | Expected | Measured |
|---|---|---|
| WAV | 384 000 samples per channel, all zero | the same |
| First and last frame | black | at most 1 of 255 |
| Text | inside the 5 % margin (the ink on the rendered middle frame); smallest cap height 2 % of the frame height (the credits) | x 0.098 to 0.892, y 0.130 to 0.904 |

The kit checks every text's width at build time; the "Also" line breaks between items, never
before a separator. The manifest's title is "End card", the chapter name in a joined cut.
