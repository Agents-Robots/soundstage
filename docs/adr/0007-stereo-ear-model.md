# 0007. Stereo target with a hybrid ear model; binaural optional

- Status: Accepted
- Date: 2026-10-25
- Ticket: —

## Context

The animations are watched on all kinds of devices: speakers, laptops, phones, sometimes
headphones. The user chose stereo for speakers and any device as the main target. Plain amplitude
panning gives left/right but sounds flat. Binaural (HRTF) rendering gives front/back and
elevation on headphones but colours the sound on speakers. Stereo cannot tell front from back by
itself.

## Decision

- Default panner `hybrid`:
  - constant-power amplitude pan from the lateral angle, its level difference limited off-screen
    to `ild_limit_db` (default 12 dB at ±90°; added after #46: unlimited, a source at the side was
    in one ear only on headphones);
  - interaural time difference (Woodworth), scaled by `itd_scale` (default 0.5) to limit comb
    filtering on speakers and in mono downmixes;
  - head-shadow shelf per ear (Brown–Duda spherical head), scaled by `head_shadow` (default 0.5);
  - a rear cue (low-pass and slight attenuation) for sources behind the camera.
- `amplitude` panner as the plainest option (pan only).
- `binaural` (SOFA HRTF) as a later option for headphone versions (Phase 4, FR-52).

## Alternatives considered

- **Amplitude panning only**: the most robust on speakers, but weak spatial impression and no
  cue for sources passing behind the camera.
- **Binaural by default**: best on headphones, coloured and narrow on speakers.
- **Ambisonics as the master format**, decoded to stereo: flexible (re-pan in Fairlight, 360
  video), but more processing and no gain for the main target; kept as an option (FR-53).
- **Full ITD and head shadow**: more natural on headphones, but comb filtering on speakers and in
  mono downmixes.

## Consequences

- The scale factors are starting values; they get tuned by ear in Phase 2 and the results recorded
  in the signal-model spec.
- Front/back stays ambiguous on stereo, by nature; the rear cue only hints at it. The picture
  carries most of that information anyway.
- Switching a render to `amplitude` or later `binaural` is a setting (`--set panner=…`), not a
  re-bake.
