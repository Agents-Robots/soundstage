# Requirements

What `soundstage` must do and why. Each requirement has a stable ID and the phase that delivers
it ([roadmap](roadmap.md)). IDs are never renumbered; a dropped requirement stays listed as
*dropped* with the reason.

## Background

Animations are produced by Python scripts that build the scene inside Blender (headless), animate
a camera rig through it, render frames (locally or on a render farm) and assemble the clip in DaVinci Resolve.
The animations have no sound. Sound effects from the environment are wanted, placed acoustically
correctly relative to the camera, rendered offline to a file that lines up frame-exactly with the
image sequence.

Decisions taken with the user (2026-10-25):

- Sound sources are **tagged on Blender objects** by the generator scripts (ADR [0003](adr/0003-tags-as-custom-properties.md)).
- Main playback target is **stereo for speakers and any device**; binaural is optional later (ADR [0007](adr/0007-stereo-ear-model.md)).
- Typical shots have **a handful to about 50** simultaneous sources.
- **Cinematic air physics**: air everywhere (also in space scenes), speed of sound 343 m/s, real
  propagation delay and Doppler, every constant overridable (ADR [0008](adr/0008-cinematic-air-physics.md)).

## Glossary

| Term | Meaning |
|---|---|
| Source | One sound attached to one object (an object may carry several). |
| Listener | The camera that renders the shot (the scene's active camera per frame). |
| Shot | A frame range of one .blend file that becomes one audio file. |
| Bake | Headless Blender run that exports positions and settings to the scene file. |
| One-shot | A sample played once, starting at a given frame. |
| Loop | A sample repeated seamlessly while the source is active. |
| Bed | A non-spatial source (ambience, music): no distance or pan processing. |
| Stem | The sum of all sources in one group, written as its own file. |

## Functional requirements

### Input: tagging sources in Blender

| ID | Requirement | Phase |
|---|---|---|
| FR-1 | A generator script attaches a sound to any object with one call (`tag.add_sound(obj, sample, …)`); the tag is stored in the .blend as a custom property and survives save/reload. | 1 |
| FR-2 | An object can carry several sounds (e.g. engine loop plus a one-shot horn). | 1 |
| FR-3 | A sound is either a **one-shot** at a frame, or a **loop** that is active from a start frame (default: already running before the shot) to an optional end frame, with fade-in/out. | 1 |
| FR-4 | Per-sound parameters: gain, pitch, reference and maximum distance, rolloff, distance model, group (stem), spatial/bed. Defaults make a plain `add_sound(obj, sample)` useful. | 1 |
| FR-5 | Scene-wide settings (speed of sound, Doppler strength, air absorption, panner, samples root, master gain) are stored on the scene and overridable on the command line. | 1 |
| FR-6 | A sound can be placed at a local offset from the object origin (e.g. an engine nozzle at the rear). | 2 |
| FR-7 | Per-sound directivity cone (inner angle, outer angle, outer gain) around a chosen object axis. | 2 |
| FR-8 | Native Blender Speaker objects are read as sources too (their sound, volume, distances, cone and NLA start frame), so sounds can also be placed in the UI. | 3 |
| FR-9 | Tagged objects inside collection instances (and geometry-nodes instances) produce one source per instance; the number per tagged object is limited to the closest ones. | 3 |
| FR-10 | Animated parameters: a keyframed custom property on the object (e.g. gain or pitch for engine throttle) modulates the sound over time. | 4 |

### Bake: from the scene to the scene file

| ID | Requirement | Phase |
|---|---|---|
| FR-20 | Bake runs headless (`blender -b … --factory-startup`) and needs no GPU, no display and no add-on installation. | 1 |
| FR-21 | Bake records, for each frame of the shot, the listener's world transform and each source's world position (and forward axis from Phase 2). | 1 |
| FR-22 | Bake samples sub-frames (default 4 per frame) so fast motion and Doppler are smooth. | 2 |
| FR-23 | Bake covers padding before and after the shot, long enough for the longest propagation delay, so sounds emitted before the first frame arrive correctly. | 2 |
| FR-24 | Bake follows camera switches (markers bound to cameras) and records them as cuts. | 2 |
| FR-25 | Bake computes visibility of each source from the listener by ray casting against the scene, per frequency band, often enough for smooth occlusion (default 10 Hz). | 3 |
| FR-26 | Bake respects the scene unit scale (`unit_settings.scale_length`), so distances are in metres. | 1 |
| FR-27 | Bake writes a versioned, documented scene file ([scene-format](spec/scene-format.md)) that can also be produced or edited without Blender. | 1 |
| FR-28 | Bake reports tagging errors (missing sample file, unknown parameter, bad value) with object name and stops, unless told to skip. | 1 |
| FR-29 | A scan lists the shot's cameras, moving objects (distance range to the camera, closest frame, side, speed, keyframes) and static objects near the camera, so an agent can choose sound sources for an existing animation. | 1 |
| FR-30 | Tags can be applied at bake time by a script, without modifying the .blend. | 1 |
| FR-31 | Bake records the camera's frame edges (lens, sensor fit, aspect, shift) per time sample, for screen-relative panning (FR-55). | 4 |

### Render: from the scene file to audio

| ID | Requirement | Phase |
|---|---|---|
| FR-40 | Loudness depends on distance via a distance model (inverse clamped by default, linear and exponential as options). | 1 |
| FR-41 | Left/right placement depends on the source's side relative to the camera (constant-power panning). | 1 |
| FR-42 | Sound travels at the speed of sound: a source at 343 m is heard 1 s after it is seen (optional per-source `sync_to_picture` for one-shots). | 2 |
| FR-43 | Doppler shift follows from the motion of both source and camera, with a strength factor (0 = off, 1 = physical, >1 = exaggerated). | 2 |
| FR-44 | Interaural time difference and head shadow add direction cues beyond level panning, at a strength suited to speaker playback. | 2 |
| FR-45 | Air absorption: high frequencies drop with distance. | 2 |
| FR-46 | Sources behind the camera are marked by a mild low-pass and attenuation (stereo cannot otherwise tell front from back). | 2 |
| FR-47 | Occluded sources are attenuated and low-passed, with smooth transitions. | 3 |
| FR-48 | A reverb send models the environment (preset or impulse response per scene); the reverb level falls more slowly with distance than the direct sound. | 3 |
| FR-49 | Camera cuts produce clean audio cuts: no Doppler sweep across a cut, short crossfade. | 2 |
| FR-50 | Non-spatial bed sources (ambience, music) are mixed with gain and fades only. | 1 |
| FR-51 | Supersonic or near-supersonic motion does not break the render: the playback rate is clamped and a warning is reported. | 2 |
| FR-52 | Optional binaural output from a SOFA HRTF set, for headphone versions. | 4 |
| FR-53 | Optional first-order (or higher) AmbiX ambisonic output for 360 video or re-panning in Fairlight. | 4 |
| FR-54 | Random variation of one-shots (gain, pitch, choice among several samples), seeded. | 4 |
| FR-55 | Screen-relative panning: sources in the frame are heard where the viewer sees them on the screen, through the camera lens (zooms and lens shift included); on by default, the direction relative to the camera as the alternative. | 4 |
| FR-56 | Shots with thousands of sources (traffic, swarms, crowds) render within minutes and bounded memory: the loudest sources of each group get the full chain, the rest a cheaper far-field rendering with the same distance, delay, Doppler, pan and air absorption; the bake computes the far sources' visibility from the direct path alone. | 4 |

### Output and mixing

| ID | Requirement | Phase |
|---|---|---|
| FR-60 | Output is a stereo WAV at 48 kHz, 32-bit float by default, 24-bit PCM optional. | 1 |
| FR-61 | Sample 0 of the output corresponds exactly to the first frame of the shot; the length equals the shot length. Works for fractional frame rates (23.976, 29.97). | 1 |
| FR-62 | Optional stems: one file per group, which sum to the master. | 3 |
| FR-63 | Render report (`.report.json`): sample peak, true peak, integrated loudness (LUFS), per source the distance range, playback-rate range, audible intervals and peak contribution, and all warnings. | 1 (basic), 3 (full) |
| FR-64 | Optional loudness normalization to a target (e.g. −23 or −14 LUFS) and a true-peak limiter; off by default, since final mixing happens in Resolve. | 3 |
| FR-65 | Debug plot (`.plot.png`) of distance, gain, pan, delay and pitch per source over a frame axis. | 3 |
| FR-66 | Preview: mux the mix with the rendered frame sequence (or a video) into an MP4 for a quick sync check without Resolve. | 1 |
| FR-67 | Partial renders: a frame sub-range, solo/mute of sources or groups, for fast iteration. | 1 |
| FR-68 | Culling for shots with many sources: sources and voices whose summed contribution stays below a budget relative to their group (`cull_db`) are skipped where they do not matter, in the render and in the bake's visibility pass; the error stays within the budget; `cull_db = null` turns it off. | 4 |

## Non-functional requirements

| ID | Requirement | Phase |
|---|---|---|
| NFR-1 | **Reproducible from scripts**: the .blend is a build artifact; generator scripts plus samples rebuild the tags, and bake plus render rebuild the audio. | 1 |
| NFR-2 | **Deterministic**: same scene file, samples and settings give a bit-identical output. All randomness is seeded from source ids. | 1 |
| NFR-3 | **Performance**: 50 sources over a 5-minute shot render in at most 5 minutes on a current desktop CPU from Phase 2 on (Phase 1 has no target). Bake of a 5-minute shot at 4 sub-frames takes at most a few minutes for scenes that rebuild quickly. | 2 |
| NFR-4 | **No clicks or zipper noise** from parameter changes, cuts, loop seams, or sources passing through the camera. | 1 |
| NFR-5 | **Headless**: everything runs on a Linux machine without GPU, display or audio device. | 1 |
| NFR-6 | **Agent-verifiable**: every behaviour can be checked with numbers (report, tests) or images (plots, spectrograms), since agents cannot listen. | 1 |
| NFR-7 | **Separation**: Blender-side code depends only on `bpy` and Blender's numpy; engine code does not depend on `bpy`. | 1 |
| NFR-8 | **Documented defaults**: every constant has a documented default in the specs, and the code takes defaults from one place. | 1 |
| NFR-9 | **Precision**: positions in float64; arrival time error below one sample; output level error of known-answer tests below 0.1 dB. | 1 |
| NFR-10 | **Formats**: input samples WAV, FLAC or OGG at any sample rate and bit depth, mono or stereo. | 1 |

## Out of scope

- Real-time playback or live preview inside Blender.
- Geometric room acoustics (image sources, ray-traced reflections, diffraction around edges). The
  reverb send and occlusion are perceptual approximations.
- Music composition or sound design (samples come from libraries or are made elsewhere).
- Writing back into Resolve projects (the output is files; placement in Resolve is manual).
