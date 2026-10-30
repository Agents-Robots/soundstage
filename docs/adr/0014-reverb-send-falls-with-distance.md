# 0014. The reverb send falls with distance: the revised theory, then spreading

- Status: Accepted
- Date: 2026-10-30
- Ticket: #35

## Context

ADR 0011 gave every source a send with the EFX convention: the source's distance law with the
preset's room rolloff, which is 0 for nearly all presets, so a source's reverberant level does not
fall with distance. That is the classical diffuse-field theory of a closed room. With thousands of
sources spread over a city (FR-56) it fails: a car 1.5 km away feeds the reverb as much as one at
8 m, the reverberant energy grows with the area the sources cover (+40 dB from 100 m to 10 km of
sources around the camera, [E19](../../research/experiments/E19-reverb-send.md)), and a city shot
with 2200 sources became a constant wash of reverb at −10 LUFS, the limiter working throughout.
Setting room rolloff 1 instead (the send follows the direct sound) fixed the level but took most of
the reverb off the close passes too.

## Decision

The send's gain is the EFX law (unchanged: the source's distance model with the room rolloff) times
a factor that depends on the distance `d` and the environment's mid-frequency decay time `T`
(the preset's `decay_time`, or the T30 at 500 Hz–2 kHz of an impulse-response file):

```
b(d) = exp(−ln(1000) · d / (c T))          d ≤ R      (Barron and Lee's revised theory)
b(d) = b(R) · R / d                          d > R      (spherical spreading)
R    = c T / ln(1000)                                   (default; scene reverb_radius_m)
```

Inside the listener's space, the reverberation a source excites decays from its emission on, and
reaches a listener at `d` only after `d / c`: by then it has fallen by `60 · (d / c) / T` dB. This
is the revised theory of Barron and Lee, measured in concert halls; the classical theory (constant
level) is its limit for small rooms. From outside the listener's space, sound reaches that space as
it reaches the listener, so its reverberation falls as the direct sound. The default `R` is where
both fall equally fast per log distance, so `b` is smooth; its level there is −8.7 dB. The scene
setting `reverb_send_law` (`revised`, default; `efx`) switches the factor off.

## Alternatives considered

- **EFX room rolloff 0 everywhere** (the previous behaviour): right for a few sources in a closed
  room; wrong for sources spread over a large or open space (Context).
- **Room rolloff 1** (the send follows the direct sound; the default of many game engines' send
  curves): the reverberant level is then right for distant sources but 10–20 dB too low for close
  ones in large spaces (30 m in a hall: −11.5 dB against −1.3 dB from the revised theory).
- **Barron and Lee alone**: falls exponentially without bound; a source 1 km away in the city
  preset would be 98 dB down, which ignores that its sound still reaches the listener's space.
- **A critical-distance model from room volume and absorption** (Sabine): needs volumes and surface
  absorption the scenes do not provide.
- **Per-region reverbs and portals**: the general answer, but much larger (spatial environments,
  ADR 0011's "later").

## Consequences

- Every render with a reverb changes: sources beyond about a tenth of `c T` get less reverb (city
  streets, `T` 1.79 s: −1.0 dB at 10 m, −2.9 dB at 30 m, −9.7 dB at 100 m, −29.7 dB at 1 km).
  `reverb_send_law = "efx"` gives the previous renders back.
- The reverberant energy of sources spread over an area grows like the direct sound's (by the log
  of the area's radius), not with the area.
- One environment per render remains; `R` describes the listener's space, not each source's.

## Notes

- References: M. Barron and L.-J. Lee, "Energy relations in concert auditoriums. I", J. Acoust. Soc.
  Am. 84(2), 618–628, 1988.
