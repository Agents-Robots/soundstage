# 0011. Reverb: EFX presets synthesized into impulse responses, one send bus

- Status: Accepted
- Date: 2026-10-25
- Ticket: #21

## Context

Shots need a space around the camera: a hangar, a street, a forest, a station hall (FR-48). The
reverb must be reproducible bit for bit (NFR-2), need no licensed files, be choosable by name by an
agent or a user, and its decay must be verifiable without listening.

## Decision

- An environment is either one of the 113 **EFX reverb presets** (the I3DL2/EAX parameter sets of
  OpenAL, also known from DirectSound and game engines), by name, or an impulse-response file.
- A preset becomes a stereo **impulse response**: sparse early taps, then decaying noise in
  complementary 1/3-octave bands, each decaying with `T60(f)` from the preset's low/mid/high decay
  times, section energies from the preset's gains, HF/LF shelves; seeded from the preset name.
- Every source feeds **one mono send** with the EFX distance convention (the source's distance law
  with the preset's room rolloff, normally 0); the summed send is **convolved once** per chunk. The
  return is its own stem.

## Alternatives considered

- **Own parameter set or named presets of our own** (`small_room`, `hall`, …): nobody knows them,
  and they would need their own calibration.
- **Algorithmic reverb** (feedback delay networks, Freeverb, `pedalboard.Reverb`): cheaper per
  sample, but offline that does not matter; convolution makes the decay per band and the level
  exactly controllable and testable ([E12](../../research/experiments/E12-reverb.md)).
- **Recorded impulse responses as presets**: licensing, size, and no parameters to reason about;
  still possible as files.
- **Per-source convolution or per-source reverb**: N convolutions instead of one, for no audible
  benefit with one environment per shot.
- **Spatial or region-based reverb** (portals, several rooms): needs room volumes in the scenes;
  left for later.

## Consequences

- One environment per render; a shot that moves between spaces is split or mixed in Resolve.
- The preset names become part of the interface (scene setting `reverb`, `soundstage presets`).
- EFX features not modelled: reflection/late panning, echo, modulation.
- The synthesis takes about 1 s for an 11 s preset, once per render.
