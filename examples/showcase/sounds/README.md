# Showcase sounds

The sounds of the [showcase sections](../sections/README.md). Two kinds:

- **Synthesized** by a seeded script, `make.py`: sounds with a simple, known structure (sirens,
  horns, bells, impacts, noise-like sounds, music loops). Reproducible, no licence.
- **Recorded**, fetched by `fetch.py` from the list in `sources.toml`: sounds that do not
  synthesize convincingly (engines, a train, footsteps, firework bangs, a level-crossing bell, a
  basketball, hand claps, an accordion). Synthesized impacts with a tonal thump sound like a drum.
  CC0 or public domain only, so that the video and the repo carry no attribution duty; author and
  source are listed anyway and shown on the end card.

No sound file is in git. Both scripts write to `out/showcase/sounds/`, which is the sections'
`samples_root`, with a table of measures per sound (`make.json`, `fetch.json`). `make.py` also
makes the probe sounds of the checks (1 kHz sine, pink noise, a white-noise burst, click). `audition.py` writes the
audition clip of A8.

## Requirements for every sound

- **A1 Dry and close.** No reverberation, no ambience, no second source in the background: the
  engine adds distance, air and space. A recording made at a distance or in a room already has
  them.
- **A2 No motion in the recording.** No pass-by, no Doppler shift, no fade: the engine adds them.
  Vehicle recordings are made on board or beside a standing vehicle.
- **A3 Mono** for spatial sources (stereo recordings are mixed down, checked for phase
  cancellation); stereo only for beds.
- **A4 Loops are steady**: level within ± 1.5 dB (short-term, 0.4 s) over the loop, pitch drift
  below 1 %, at least 4 s long, seamless (`make.py` and `sources.toml` make every loop so), with
  no audible period. Sections tag them with `loop_crossfade=0`: the engine's default 50 ms seam
  crossfade blends material 50 ms apart, which for a sound with a steady rhythm or pitch (music, an
  engine firing at 90 Hz) is out of step and stutters once per loop.
- **A5 One-shots start on the onset** (within 5 ms) and end in silence.
- **A6 48 kHz, 24 bit, peak at −3 dBFS**, no clipping. Sources are uncompressed or lossless
  where the site offers them; a Freesound preview (MP3, 128 kbit/s, nothing above about 16 kHz)
  is accepted for engines, beds and distant sounds such as fireworks, where little of what is
  heard lies above 16 kHz, and its entry in `sources.toml` says so.
- **A7 Recorded sounds** have an entry in `sources.toml`: URL, author, licence, SHA-256 of the
  download, and the processing (channel, cut points, loop points, gain), applied by `fetch.py`, so
  the result is reproducible from the original.
- **A8 Approved by ear.** `audition.py` writes an audition clip (each sound played dry and
  loudness-matched, its name and source on screen). A sound is used in a section only after the user has approved it there;
  A1, A2 and "sounds like the thing on screen" cannot be measured.

Measured by the scripts for every sound: length, peak, loudness, spectrum plot; for loops the
level variation and the pitch drift (A4), for one-shots the onset time (A5).

## Recorded

| File | Sound | Needs | Used in |
|---|---|---|---|
| `car_engine.wav` | Petrol car engine at a steady 2500 to 3500 rpm | A2, A4; at least 6 s | intro, sources, doppler, around (scooter, pitched up), occlusion (motorbike, pitched up), scale (cars and trucks, pitched), finale |
| `car_idle.wav` | The same or a similar engine idling | A4 | sources, scale |
| `race_engine.wav` | Engine at steady high revs, pitched up in the sections for a racing car (no CC0 racing engine holds steady revs) | A2, A4; at least 4 s | doppler, cuts |
| `train_roll.wav` | A train rolling, heard from inside | A2, A4 | doppler, finale |
| `crossing_bell.wav` | Level-crossing bell, no train | A1, A4; the loop a whole number of strikes | doppler, finale |
| `footstep_1.wav` … `footstep_4.wav` | Single steps on a hard floor | A1, A5; four different steps | intro, reverb, finale |
| `firework_bang_1.wav` … `_3.wav` | Small aerial firework, one bang each | A5; three different bangs, sharp onset, under 1.1 s | delay, finale |
| `tennis_hit_1.wav`, `_2.wav` | Racket hitting a ball | A1, A5; two hits of the same racket, a body below 1 kHz | screen |
| `jet_whine.wav` | Jet engine from the front: fan whine | A2, A4; most energy 2 to 5 kHz | directivity |
| `jet_roar.wav` | Jet engine from behind: exhaust roar | A2, A4; most energy below 1 kHz | directivity |
| `accordion_loop.wav` | A busker's tune on an accordion, solo | A1, A4; 200 Hz to 8 kHz, at least 10 s | occlusion, finale |
| `basketball_1.wav` … `_3.wav` | Single bounces of a basketball on a hard floor | A1, A5; three bounces of one ball | reverb |
| `handclap_1.wav`, `_2.wav` | Single hand claps | A1, A5; two claps of the same hands | reverb |
| `crowd_bed.wav` | A large crowd, stereo | A3, A4; steady babble, no single voice, at least 20 s | cuts |

If no CC0 recording meets A1 to A4, the sound falls back to `car_engine.wav` at another pitch
(`race_engine`) or to a synthesized version, and the section's README says so.

### Where recordings come from

`fetch.py` downloads without a login or token, so it uses two sources, searched in this order:

1. **Wikimedia Commons.** The API (`generator=search` with `filetype:audio`) returns the licence
   in each file's `extmetadata`, and files download directly, often as the original WAV, FLAC or
   Ogg. A search for car engines and footsteps found nothing under CC0 (CC BY and CC BY-SA
   only), so `fetch.py` has no Commons download yet.
2. **Freesound, CC0 only** (search filter `license:"Creative Commons 0"`). The originals and the
   API need a login; the HQ preview (MP3, 128 kbit/s) downloads without one, so `fetch.py` uses
   it under the A6 exception. It checks the licence on the sound's own page on every online run,
   and the file's SHA-256 against `sources.toml`.

The recordings in use, with author, page and processing, are the entries of `sources.toml`.

Not used: general web search (mostly paid libraries), YouTube (no licence, blocks scripts), and
Pixabay (its own licence, which forbids redistributing a file on its own).

Processing that has proved necessary for such recordings, applied by `fetch.py` from the
`sources.toml` entry:

- Engines: cut the steadiest stretch (a standing engine at constant revs, or the plateau of a
  pass-by, never its approach or departure: those carry their own Doppler, against A2).
- Field recordings have almost nothing below 100 Hz; an engine that needs weight (a truck, a
  jet) gets a synthesized sub layer at its firing frequency. The car recordings are used without.
- Crowds and beds: a stereo recording keeps both channels (`stereo = true`); several recordings
  would have their level evened out per second before they are layered. No CC0 recording of a
  cheering crowd holds its level within ± 1.5 dB; `crowd_bed` is a hall full of people chatting.

Freesound 322178 (an F-16 starting up and idling) was measured for the jet and not used: 61 % of
it is below 1 kHz and only 7 % between 2 and 5 kHz, roar and hiss with little whine.

## Synthesized

| File | Sound | Structure | Used in |
|---|---|---|---|
| `tyre_noise.wav` | Road noise of a rolling vehicle | noise between 400 Hz and 2.5 kHz, slow random level changes, 6 s loop | most vehicle scenes |
| `siren_two_tone.wav` | Two-tone emergency horn | 440 Hz and 585 Hz alternating every 0.75 s, harmonics up to 5 kHz, 3 s loop | intro, doppler, finale |
| `car_horn.wav` | Car horn | 420 Hz and 500 Hz together, 0.6 s | sources |
| `church_bell.wav` | One strike of a church bell | hum, prime, tierce, quint and nominal partials over a 320 Hz prime; the hum decays by 60 dB in 4.5 s, shorter than a real bell, so that a strike ends within a pass | sources, finale |
| `train_horn.wav` | Train horn | three chimes at once, 311, 370 and 494 Hz (D#4, F#4, B4): reed tones with all harmonics up to 6 kHz that start 4 % flat and rise to pitch in 80 ms, a little breath noise, the bells' resonance around 1.2 kHz; 2 s | finale |
| `prop_plane.wav` | Propeller plane | two-blade propeller and four-cylinder engine at 2700 rpm: harmonics of the 90 Hz blade pass, exhaust bursts on the 90 Hz firing, crank rumble, air hiss; 4 s loop. Every CC0 recording of a plane outside it is a fly-by (against A2) | doppler |
| `drum_loop.wav` | Music from a stage | kick, snare, hi-hats (8 to 12 kHz), bass and chord stabs at 120 bpm, one bar of exactly 2 s, on a sixteenth grid; the kick times go to `make.json` for the stage lights | distance |
| `thunder.wav` | Thunder | crack, then 4 s of rumble, 4.5 s in all | delay |
| `hammer_hit.wav` | Hammer on wood | 2 ms click and a 900 Hz knock, 120 ms | delay |
| `town_bed.wav` | Town ambience (stereo) | birds, light wind, far traffic hum, 20 s loop | intro, sources, occlusion, finale |

`prop_plane.wav` is the synthesized sound most likely to sound artificial; a recording that meets
A1 to A4 replaces it under the same file name, with no change to a section.
