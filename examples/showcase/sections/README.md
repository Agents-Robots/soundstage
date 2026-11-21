# Showcase sections

The showcase as independent sections: one folder per section, each with a `README.md` that
specifies its scene. A section is built, baked, rendered (picture and sound) and checked on its
own, gives a clip that can be shown alone, and is joined with the others into the full video
afterwards. This file holds what all sections share: the order, the rules that make them
joinable, the title pages, the labels, the sound rules and the assembly.

This is the specification of the showcase's second version. The scripts one folder up
([`../README.md`](../README.md)) are the first version: one .blend, simple shapes, test tones.

The scenes show things a viewer knows from life (an ambulance passing, fireworks across a lake,
music behind a house), so that a correct result is recognised without explanation.

## Sections

In the order of the full video. The order follows the path of the sound: what a source is, what
distance does to it, what motion does, how it reaches two ears and a screen, what the
surroundings add, and how this holds up across cuts and many sources.

| Key | Title | Real-world case | Features | Length |
|---|---|---|---|---|
| [`intro`](intro/README.md) | soundstage | A street shot, first silent, then with sound | (all, at defaults) | 18 s |
| [`sources`](sources/README.md) | One line per sound | A car, its horn, a church bell and birds, added one tag at a time | loops, one-shots, pitch, beds, groups, offsets | 42 s |
| [`distance`](distance/README.md) | Distance | An open-air stage heard from 686 m down to 43 m | distance model, air absorption | 40.5 s |
| [`delay`](delay/README.md) | Speed of sound | A carpenter, fireworks and lightning across a lake | propagation delay, `sync_to_picture` | 35 s |
| [`doppler`](doppler/README.md) | Doppler effect | An ambulance, a race car and a plane passing; a train passing a crossing bell | Doppler from source and listener motion | 37 s |
| [`around`](around/README.md) | Around the listener | A scooter circling the camera in a roundabout | panner, time difference, head shadow, rear cue | 15 s |
| [`screen`](screen/README.md) | Sound follows the lens | A tennis rally filmed with a zoom | screen-relative panning | 27 s |
| [`directivity`](directivity/README.md) | Directivity | A camera circling a jet with running engines: whine in front, roar behind | cones, several sounds per object, offsets | 29 s |
| [`occlusion`](occlusion/README.md) | Occlusion | A motorbike behind a row of houses; a busker around a corner | visibility bake, occlusion filter | 39 s |
| [`reverb`](reverb/README.md) | Reverb | A basketball outdoors, in a living room, a gym and a church | reverb presets, send law | 44 s |
| [`cuts`](cuts/README.md) | Camera cuts | A race covered by five cameras, one of them on board | listener cuts, moving listener | 33 s |
| [`scale`](scale/README.md) | Many sources | A queue of 40 identical cars; a motorway with 300 vehicles | instances, loop phase, culling, far field | 37 s |
| [`city`](city/README.md) | Ten thousand cars | A city at blue hour with 10 000 cars, from 600 m up down to the boulevard's median | far field, culling, instances at scale | 33 s |
| [`finale`](finale/README.md) | All together | One evening in the town, everything at once, closing with fireworks and the numbers of what it took | all, at defaults | 78 s |
| [`production`](production/README.md) | In production | Two scenes from Blender animations: six racers across a swamp at 612 km/h; music and neon signs around a tower in a city of flying cars | all, at the animations' settings | 71.1 s |
| [`outro`](outro/README.md) | (end card) | | | 14 s |

[`slates`](slates/README.md) holds text cards for the trailer; it is not a chapter. All sections in
full: 9 min 53 s. Not shown, because there is nothing to see or hear: loudness normalization,
limiter, stems, solo and mute (named on the end card), quality modes and sample rate, Speaker
objects (another way to create a source). Not implemented yet: variations, animated parameters,
binaural and ambisonic output.

## Cuts

| Cut | Sections | Length |
|---|---|---|
| `full` | the features first, each with its title page and only passes where it is on: `intro` from its sound, `doppler`, `delay`, `occlusion`, `around`, `directivity`, `reverb`, `screen`, `distance`, `sources` (three of its six passes), `cuts`; then `city`, `production`, `finale` and `outro` whole. `scale` is left out: `city` shows the scale | 6 min 35 s |
| `trailer` | clips: the race's flyby, two slates, the ambulance passing, lightning and thunder, the busker around the corner, the church, the race's camera cuts, a slate, the city, the party terrace in the city of flying cars, the finale's closing salvo; then `outro` | 1 min 18 s |
| clips | every section alone | as above |

The order of a cut is a list of keys in one file (`cuts.py`); nothing else depends on it. A
`Clip` there takes part of one pass (seconds from its first frame), or a section's title page
(`TITLE_PAGE`), with a fixed gain where a section is quiet by design, and a tail of its sound that
may run on under the next part. `chapter(key, *passes)` is a title page and some passes whole.

## What a section is

A section folder holds:

| File | What it is |
|---|---|
| `README.md` | The scene: claim, set, action, cameras, passes, sounds, picture aids, requirements, known answers |
| `section.py` | The storyboard (stdlib only): title page texts, passes with label, length and render settings, section gain |
| `build.py` | Builds the section's .blend in Blender from the kit: set, animation, cameras, overlays, tags, probes |
| `check.py` | The known answers of the README, asserted on the rendered passes |
| `steps.py` | Optional: steps of `showcase.py` the section does its own way (`production` takes sound and picture from finished animations) |

Rules that keep sections independent and joinable:

- **C1 Own files.** A section has its own .blend with frames from 1, its own bake, its own WAV.
  Building or changing one section never changes another.
- **C2 Own imports.** A section imports the kit and the sounds, never another section. Sets used
  by several sections (the town of `intro` and `finale`) are kit modules.
- **C3 Same format.** 1920 × 1080 (other sizes by option, same aspect), 30 fps, the kit's colour
  management; sound 48 kHz stereo, so one frame is 1600 samples and frame ranges cut the sound
  exactly.
- **C4 Same timeline shape.** Title page, then the passes, in the order of `section.py`. Picture
  and sound both read the frame ranges from `section.py`.
- **C5 Black and silent ends.** The picture fades from black over the first 8 frames and to black
  over the last 8; the sound is below −60 dBFS in the first and last 0.2 s. Sections are joined
  with hard cuts and no processing, so any order works.
- **C6 Nothing that depends on the order.** No section number, no "next", no progress bar, no
  reference to another section in picture or sound.
- **C7 Self-contained .blend.** Text is converted to meshes at build time, images are packed, no
  drivers on Python expressions and no frame handlers: the file renders on the farm without the
  repo.
- **C8 A manifest.** The build writes `section.json` next to the .blend: key, title, fps, size,
  frame range, title frames, passes with frame ranges and settings, section gain. The audio
  script, the checks and the assembly read it.
- **C9 Picture and sound split.** A change to render settings, gains or samples needs a new WAV
  only. A change to timing, motion, sets or overlays needs new frames. The manifest's frame count
  is checked against the picture at assembly.

Outputs, all gitignored: `out/showcase/<key>/` with `<key>.blend`, `section.json`, `bake/`,
`passes/`, `<key>.wav`, `<key>.report.json`, and after the frames are rendered `<key>.mp4`.

## Picture

- **Kit.** Low-poly models built by script from primitives, in real dimensions (the physics
  depends on metres): car, van and ambulance, truck, scooter and motorbike with rider, race car,
  train, propeller plane, jet, figure, house (three variants), church with a bell tower, stage with
  loudspeaker towers, grandstand, tennis court, tree, street lamp, bridge, level crossing, and the
  interiors (living room, gym, church nave). Flat-shaded, one palette, one sun-and-sky setup per
  time of day (day, dusk, night). Each model has named empties
  where its sounds are emitted (engine, exhaust, horn, bell).
- **P1 Every sound has a visible cause on its frame**: a hit, a flash, a turning light bar, a
  swinging bell, a foot on the ground. Sources outside the frame are shown on the inset map.
- **P2 Motion is plausible**: speeds a viewer expects (given in km/h on the label where they
  matter), linear keys where a speed is meant, wheels on the ground, no sliding figures.
- **P3 Text is large**: the smallest text has a cap height of 2 % of the frame height; all text
  stays inside a 5 % margin. Fonts are the ones Blender ships (Inter, its interface font, for
  text, made bold by thickening the outline; DejaVu Sans Mono for code); no font file is in the
  repo.
- **P4 Three overlay colours**: text (near white), accent (amber: sounding, arriving), muted
  (grey: scales, axes, the dots of other passes). Overlays are objects parented to the camera,
  rendered with the scene,
  so the farm output is the final picture.

## Title page

Every section starts with a title page of 3.0 s (90 frames), silent. It is laid over the
section's own opening view, which makes each title page look different without extra work:

- Background: the first camera of the first pass, with everything at rest, behind a card in the
  kit's background colour at 78 % opacity (97 % over the lit city of `city`). The picture fades
  from black in frames 1 to 8.
- Left-aligned column at 10 % from the left edge (heights in % of the frame height, baselines
  measured from the top). Two things to read in 3 s, no more: the title and what to listen for.

  | Element | Content | Cap height | Baseline |
  |---|---|---|---|
  | Kicker | `SOUNDSTAGE`, accent colour, letter-spaced | 2.2 % | 40 % |
  | Title | the section title, bold, one line | 8.5 % | 54 % |
  | Rule | accent line, 6 % of the width | | 58 % |
  | Listen for | "Listen for" in the accent colour, then one sentence naming the audible change; at most two lines | 3.4 % | 66 % (a second line at 72 %) |

  The claim (what is true and will be heard) and the code chip (the one call or setting that
  controls the feature) stay in the storyboard and the section's README: on screen they could not
  be read in 3 s.
- Bottom right, at 90 %: a headphones mark where the section needs headphones (`around`), and
  one dot per pass.
- In frames 79 to 90 the card and the text dissolve and reveal the scene; pass 1 starts on
  frame 91.
- No section numbers (C6). The kicker carries the project name, so a clip shown alone is
  attributed.
- The kit measures every text when it builds a title page or a lower third and stops the build
  if one is wider than its place: text is never scaled down or cut off to fit.

Exceptions: `intro` has a centred wordmark page of 4 s, `outro` is an end card only, and the
`finale` title page is cut off in the trailer (its frames are in the manifest).

## Passes, labels and instruments

A pass is one run of the action with one setting. A change of pass is a hard cut: the action
restarts, the label changes on the same frame, and the sound of a pass has ended before its last
frame.

**Only the effect is shown.** The videos show each feature on, never the scene without it: a
feature switched off sounds wrong, not instructive. Some sections still hold a pass with the feature
off (`occlusion`'s `bike_off`, `screen`'s `camera` ...) as a reference for their checks and their
own previews; the cuts (`cuts.py`) leave those passes out. A check that needs the scene without a
scene setting renders it for itself (`Check.probe(..., extra=...)`).

- **Section tag**, top left: the section title on a small chip.
- **Lower third**, 84 % to 96 % of the height: the pass label in plain words (cap height 3.2 %),
  below it the setting in monospace (2.2 %), and on the right one dot per pass with the current one
  filled.
- **Instruments**, top right or above the lower third, only where the picture alone cannot show
  what happens: an inset map seen from above (camera, view cone, sources, occluders), a wavefront
  travelling at 343 m/s, a gauge with marks at the expected values (pitch in semitones, level in
  dB), a stopwatch bar. They are keyed at build time from the scene's geometry with the same
  formulas the checks use, so an instrument shows the expected value and `check.py` confirms that
  the sound has it.

## Sound

- **Sounds** are listed with their requirements in [`../sounds/README.md`](../sounds/README.md):
  synthesized by a seeded script where that is convincing, CC0 recordings fetched by script where
  it is not (engines, footsteps). No sound file is in git.
- **One render per pass**: scene settings apply to a whole render, so each pass is rendered alone
  (its frames, its sources, its settings from `section.py`) and placed at its frames; the title
  page is silent by construction. A pass may name a bake variant where a bake setting differs
  (`cuts`: another listener).
- **Sources belong to a pass.** Every tag entry has an id `<section>.<pass>.<name>` and is limited
  to its pass with `frame` and `end_frame`; the pass is rendered with `--solo <section>.<pass>.*`.
  Per-source settings (cones, `occlusion`, `sync_to_picture`, `loop_phase`) therefore differ
  between passes without a render option. Sources inside instances take their id from the
  instancer's name, which starts the same way. A source may start before its pass (sound that is
  still on its way when the pass begins); the render takes the pass's frames only.
- **S1 No normalization and no limiter**, in a pass, a section or the assembly: they would level
  out what the passes show. One static gain per section (`gain_db` in `section.py`). The one
  exception: a section of sharp impacts that stand about 15 dB over everything else (tennis hits,
  claps and bounces) names a ceiling (`limit_dbtp`), and each of its passes goes through
  soundstage's true-peak limiter there, so that the section can be lifted toward the others'
  level. The report gives the limiter's largest reduction per pass.
- **S2 Level.** The section's reference pass (the last pass at default settings) has an integrated
  loudness of −18 LUFS ± 2; the section's true peak is at most −1 dBTP. Where both cannot hold
  (single loud impacts), the peak limit wins and the README says so.
- **S3 No cut tails**: every pass ends below −60 dBFS (the audio script warns otherwise). It
  measures from 55 to 5 ms before the end: when a camera cut follows the pass, the engine's 10 ms
  crossfade into the next shot starts 5 ms before it.
- **S4 Probes.** Recorded and musical sounds have no known frequency or level to assert. Each
  section therefore tags probe sources (`<section>.probe.<pass>.<name>`: a 1 kHz sine, pink or
  white noise, a click) on the same objects, with the same settings as the real sounds. They are
  never in the mix (the passes are soloed); `check.py` renders them alone and asserts the known
  answers on them.
- **S5 Reproducible**: same inputs, same WAV, bit for bit.

## Assembly

`assemble.py <cut>` joins sections into one video:

1. For each section of the cut, take its picture (a folder of numbered frames, where a missing
   frame holds the one before it, as in a preview rendered with a step; or a video) and its WAV,
   and check them against `section.json`: aspect, frame count, WAV length = frames × 1600 samples,
   first and last frame black, first and last 0.2 s silent, true peak, loudness of the reference
   pass, and that the WAV was rendered from the manifest as it is (the report's frames, gain and
   passes, and not older than the manifest; `outro` R5). Any failure stops the assembly.
2. Join the pictures in order with one encode, scaled to the largest size among them. Where the
   cut trims a title page, the first 8 frames that remain are faded from black.
3. Join the WAVs in order, sample-exact, with no gain change, into `<cut>.wav`.
4. Mux once (`soundstage preview <cut>.wav --video ... --width 0`), so that the sound is encoded
   once and no encoder padding accumulates at the joins.
5. Write `<cut>.chapters.txt` with the start time and title of every section (video chapter
   marks), and `<cut>.sections.txt`, a table of length, loudness and peak per section.

A clip (`cuts.Clip`) is checked as its section is (step 1) and cut hard: its frames, its sound with
its fixed gain, a 15 ms fade where the sound is cut and, with a tail, its sound running on under
the next part while fading out. A cut that opens on a clip fades in from black. The joined sound's
true peak is checked again (S2).

Each section is also muxed alone into `<key>.mp4`. The deliverables for editing are the WAVs.

## Code layout

```
examples/showcase/
  sections/<key>/        README.md, section.py, build.py, check.py (and steps.py where a step differs)
  kit/
    story.py             storyboard dataclasses and the manifest (stdlib only)
    blender/base.py      scene format, palette, materials, keyframes, cameras with the overlay root,
                         finishing (markers, sound settings, manifest, save)
    blender/overlay.py   title page, lower third, section tag, code panel, fades, cards, callouts;
                         instruments: level bars, read-out, gauge, band strip, travel ruler, map
                         inset, stereo bar, lobe map, sight map, plan map
    blender/models.py    vehicles (cars, ambulance, truck, scooter, motorbike, race car, plane, jet),
                         figure, busker with accordion, tennis player, houses, church, stage,
                         railway track, level crossing, train and its cab, tennis court,
                         basketball hoop, grandstand, interiors (living room, gym, church nave),
                         fireworks, props
    blender/town.py      the town's layout (with the side street for `finale`)
    blender/frames.py    renders frames of a section's .blend (checks and previews)
    audio.py             per-pass render, the section's WAV and report
    checks.py            probes, geometry from the bake, section-level checks
    measure.py           measurement helpers
    hearing.py           the ear model's pan law, screen lateral, head shadow and rear cue, for
                         expected values (stdlib only)
  sounds/                README.md, make.py (synthesis), sources.toml and fetch.py (recordings),
                         audition.py (A8)
  cuts.py                the cuts: lists of section keys and clips
  showcase.py            build, bake, audio, check and preview for one, several or all sections
  assemble.py            joins a cut
```

## Engine limits that shape the scenes

- One reverb per render: an environment is a pass, not a zone. A drive through a tunnel with the
  reverb changing on the way cannot be rendered in one pass.
- A sample's gain and pitch are constant over a shot (animated parameters are not implemented):
  vehicles keep their speed, engines do not rev up.
- One-shots have no random variation: repeated events (footsteps, hits) alternate between
  numbered samples by hand.
- A cone changes the level of all frequencies alike.
- The output is stereo: no height, and front and back differ only by the rear cue.
- A one-shot with `sync_to_picture` must be received before the next camera cut.

## What is measured and what needs ears

Measured per section by `check.py` on the probes and by the audio script: the known answers in
each README, loudness, peaks, cut tails. Read as images: debug plots, spectrograms, one still per
pass and title page. Not measurable: whether a recorded engine sounds like the vehicle on screen,
whether a synthesized sound is convincing. The sounds are
approved by ear before the scenes are built ([`../sounds/README.md`](../sounds/README.md)), and
each section is judged by ear on its preview clip.
