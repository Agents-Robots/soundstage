# `slates`: text cards for the trailer

Three cards of white and amber text on black, silent. They are not a chapter of the full video:
the trailer (`cuts.py`) takes them between its clips.

| | |
|---|---|
| Length | 6.9 s (207 frames) |
| Set | none: black |
| Sound | digital silence (the trailer lets the clip before a card run on under it) |

## Passes

| Pass | Frames | Text |
|---|---|---|
| `not_recorded` | 1–66 (2.2 s) | "This sound was not recorded." |
| `title` | 67–141 (2.5 s) | "soundstage", the accent rule, "Spatial sound, computed from your Blender scenes" |
| `thousands` | 142–207 (2.2 s) | "Ten thousand cars." and, in amber, "Twenty thousand sources." |

Each card fades in from black over 6 frames and out to black over its last 6, centred, bold Inter.

## Requirements

- **R1** Every card's first and last frames are black, so a cut can take any card alone (C5).
- **R2** What a card states is shown in the clip that follows it: `thousands` comes before `city`,
  whose bake has 10 000 cars and 20 000 sources (its check).

## Known answers

| What | Expected |
|---|---|
| WAV | digital silence |
| first and last frame of every card | black (at most 2 of 255) |
