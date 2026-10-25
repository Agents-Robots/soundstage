# 0008. Cinematic air physics with overridable constants

- Status: Accepted
- Date: 2026-10-25
- Ticket: —

## Context

Many of the user's scenes are in space (stations, cargo ships, space battles), where physically
there is no sound at all. Film convention gives space scenes sound anyway. The question is how
physical the model should be: real propagation delay and Doppler, or a stylized model where sound
arrives instantly.

## Decision

Pretend there is air everywhere, and model it physically by default:

- speed of sound 343 m/s, real propagation delay and Doppler from source and camera motion;
- distance attenuation by distance models, air absorption by distance;
- every constant overridable per scene (`scene["sfx_settings"]`), per source (tag multipliers
  such as `doppler`, `air_absorption`) and per render (`--set`).

Stylized behaviour is reached through the same knobs: `doppler_factor = 0` (constant delay, no
pitch change), `sync_to_picture` for one-shots, `air_absorption = 0`.

## Alternatives considered

- **Stylized model with no delay**: Doppler as a pitch effect from radial velocity with a strength
  knob, sound always in sync with the picture. Simpler, but drifts from the picture for distant
  sources and loses the "heard after seen" realism that sells scale.
- **Medium per region** (air inside stations, vacuum outside): physically interesting, but needs
  volumes in the scene and gives silent shots, which is not what the films want.

## Consequences

- Distant one-shots are heard late; generator scripts set `sync_to_picture=True` where a late
  sound would look like a mistake.
- Very fast objects (fighters, missiles) can approach Mach 1 in scene units, which triggers the
  rate clamp; scene scale and `doppler` per source are the controls.
- The same engine serves atmospheric scenes (cities, planets) without changes.
