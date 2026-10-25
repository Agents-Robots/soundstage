# Research: existing solutions, libraries, formats

Done on 2026-10-25 before the design. Facts about third-party tools reflect what was found
then; recheck before relying on details.

## Existing solutions

| Option | Has | Missing / problem | Verdict |
|---|---|---|---|
| **Blender Speaker objects + `bpy.ops.sound.mixdown`** (audaspace inside Blender) | Distance models, attenuation, reference/max distance, cone, Doppler settings (speed of sound + factor), constant-power panning relative to the active camera; mono sources only for 3D | Measured in Phase 0 (below): no Doppler shift in rendered audio, 3D parameters stepped once per audio buffer, headless mixdown leaves speakers out (a video render works), 16-bit audio from renders; no delay, air absorption, occlusion, reverb or stems; little control or insight | **Baseline** (`tools/blender_mixdown.py`). Speaker objects may still be read as an alternative tag source (FR-8). |
| **audaspace** standalone (C++ with Python bindings, Apache-2.0) | Blender's audio engine as a library; 3D device, sequencer | No pip package found; same DSP limits as in Blender | No |
| **Steam Audio** (Valve, C SDK) | HRTF, occlusion, reflections, pathing for moving sources | No Python binding (Rust wrapper audionimbus exists); real-time game API; heavy | No (ideas for occlusion and reflections) |
| **pyroomacoustics** | Room acoustics by image sources, arrays | Static sources only; moving sources need a segmented approximation | No (could generate room IRs for the reverb later) |
| **OpenAL Soft, FMOD, Wwise, Unity, Unreal** | Full real-time 3D game audio | Real-time engines; offline frame-exact sync to Blender needs large glue | No |
| **DaVinci Resolve Fairlight** 3D panner, ADM / Atmos objects, ambisonics (v19+), binaural monitoring (v19+, Apple Spatial Audio in 20.1) | Native immersive mixing | Positions would have to be keyframed by hand or exported as ADM object metadata (room-relative, needs Atmos tooling) | No for positioning. Ambisonic output (FR-53) can use Fairlight's ambisonic buses later. |
| **omi_audio** (MIT, numpy) | Emitters with distance curve, cone, gain | No Doppler, delay, occlusion, reverb, HRTF | No |
| **Research: DynamicSound** (arXiv 2601.15433) | Moving sources with propagation delay, Doppler, distance attenuation, air absorption, first-order reflections | Research code for microphone arrays | Confirms the method |
| **J. O. Smith (CCRMA): Doppler via variable delay lines** | The standard method: a time-varying delay driven by the geometry produces exact Doppler | | **Adopted** (ADR 0006) |

Conclusion: nothing does offline, frame-exact, scriptable spatial audio for a Blender camera path
with control over the model. The core is small with numpy/scipy, and the physics is well
established, so it is built here.

## Libraries

| Library | Use | Notes |
|---|---|---|
| numpy, scipy | Arrays, `CubicSpline`, `signal` (filter design, resampling, spectrogram), `fftconvolve`, `spatial.transform.Rotation`/`Slerp` | Core |
| soundfile (libsndfile) | Read WAV/FLAC/OGG, write WAV float/PCM | Core |
| soxr (python-soxr) | High-quality sample-rate conversion | Core; better and faster than `resample_poly` for arbitrary ratios |
| numba | Per-sample kernels: time-varying filters, fractional-delay reads | Core (ADR 0002) |
| pyloudnorm | BS.1770 integrated loudness, normalization | Core (report) |
| pedalboard (Spotify) | Limiter, optional effects, VST3 hosting | Optional extra `fx` |
| matplotlib | Debug plot | Optional extra `plot` |
| sofar | Read SOFA HRTF files (binaural, Phase 4) | Optional extra `hrtf`; alternatives: spaudiopy (also ambisonics/SH tools), hrtfpykit (research-oriented, 2026), python-sofa |
| Blender `aud` | Not used for rendering; Blender 5.2.2 ships numpy 2.3.4, which bake uses | Checked in Blender 5.2.2 |

HRTF datasets for Phase 4: MIT KEMAR, SADIE II, the CIPIC set, all available as SOFA files.

## Formats

- **Input samples**: WAV, FLAC, OGG via libsndfile; any rate and depth. MP3 is avoided (encoder
  delay shifts onsets).
- **Scene interchange**: JSON manifest + NPZ arrays (ADR 0004). Considered: one big JSON (slow and
  large for trajectories), HDF5 (extra dependency, and Blender has no h5py), USD (heavy, and
  audio schemas there are not established), CSV (no structure).
- **Output**: WAV 48 kHz, 32-bit float default, 24-bit PCM optional (ADR 0005). 48 kHz is the
  video standard and Resolve's default project rate. Float avoids clipping before the final mix in
  Fairlight. Not chosen: embedding audio in the video (Resolve handles them separately anyway),
  ADM BWF / Atmos (needs Atmos tooling), ambisonics as default (stereo is the target).
- **Resolve import**: multichannel WAVs are split or mapped per channel; mono files with `.L`/`.R`
  suffixes group into one clip (18.6+). Stereo WAVs import as stereo clips. Ambisonic import
  conventions (AmbiX ACN/SN3D) are not clearly documented; test before relying on them (Phase 4).

## Phase 0: Blender Speaker baseline (measured)

Measured on 2026-10-25 with Blender 5.2.2. `tools/blender_mixdown.py` gives every soundstage
source the same dry signal soundstage plays and lets Blender spatialize it: a Speaker per spatial
source (parented to its object at `offset`, with `distance_reference`, `distance_max`,
`attenuation` from the tag and the scene's distance model, speed of sound and Doppler factor), a
sequencer sound strip per bed, the scene camera as listener. Compared on the flyby example against
soundstage's render of the same tags; the measurement source was a 1 kHz sine on the ship
(`ref_distance` 15 m, passing 25 m in front of the camera at 30 m/s), and a click on the crate at
frame 180.

Getting audio out of Blender headless:

- `bpy.ops.sound.mixdown` runs as a job: under `blender -b` it returns `FINISHED` at once and the
  process exits after the first 2048 samples. Waiting until the file has its full size fixes that.
- Even then the mixdown contains only sequencer strips: Speakers stay silent, with or without
  `-setaudio`, after stepping through the frames, and after `bpy.ops.sound.bake_animation`.
- A video render with an audio codec does contain the speakers. With a black color strip in the
  sequencer and `render.use_sequencer`, the 3D render is skipped (240 frames in 0.4 s). The audio
  of a video render is 16-bit (FLAC or PCM; no float option). This is the tool's default method.
- Blender 5 needs `image_settings.media_type = "VIDEO"` before `file_format = "FFMPEG"`.
  `bpy.ops.object.speaker_add` creates the speaker's NLA sound strip; a speaker made through
  `bpy.data` has none and plays nothing.
- In the `aud` module, `Sound.loop(-1).limit(...)` never ends on a mono sound (it wrote 17 GB),
  and `Sound.write` (through ffmpeg) pads the file or aborts the process with "filling the audio
  frame failed", depending on the length. The tool composes signals in numpy from `Sound.data()`
  and writes float WAVs with the standard library.

Results:

| | Blender speakers | soundstage (Phase 1) |
|---|---|---|
| Onset of the one-shot at frame 180 | sample 286 400, exact | sample 286 400, exact |
| Level against the inverse-clamped law | within ±0.5 dB | within ±0.1 dB |
| Pan law | constant power, `g_L² = (1 − sin θ)/2`, `g_R² = (1 + sin θ)/2` (θ: azimuth from the front; fit within 0.03 in linear gain) | constant power, `φ = (λ + 1)π/4` |
| Channel balance with the source 76° to the side (124 m) | 18 dB | 32 dB |
| Doppler (factor 1 and 10, 343 m/s) | none: 1000 Hz throughout (expected 1094 Hz approaching, 921 Hz receding) | none (Phase 2) |
| Parameter updates | once per audio buffer (4608 samples with FLAC, 96 ms); level steps up to 0.47 dB within 1 ms during the pass | 1 ms control rate, interpolated; at most 0.019 dB per ms |
| Flyby mix (same tags) | −23.3 LUFS, 1.2 s | −23.4 LUFS, 1.2 s render (plus 0.9 s bake) |
| Output | 16-bit, via a video render | 32-bit float WAV |

Conclusions:

- Blender's speakers are a usable reference for distance and timing: both engines agree there.
- What soundstage has to beat in Phase 2: Doppler and travel delay (Blender produces neither in
  rendered audio), smooth parameter changes for fast passes, float output.
- Panning differs. Blender's law splits power linearly with the lateral sine and keeps the far
  channel at −18 dB at 76°; soundstage's pans almost hard (−32 dB). Whether the amplitude part of
  the panner should move towards `g² = (1 ± λ)/2` is a listening question for the Phase 2 ear-model
  tuning.
- Lists of dicts as custom properties survive save and reload in Blender 5.2 (checked in Phase 1,
  [spec/tagging.md](spec/tagging.md)), so tags need no JSON-string fallback.

Reproduce:

```bash
blender -b out/flyby.blend --factory-startup -y --python-exit-code 1 \
    --python tools/blender_mixdown.py -- --run examples/flyby_sounds.py --out out/flyby/blender.wav
```

## Sources

- Blender: [aud module](https://docs.blender.org/api/5.1/aud.html), [Speaker API](https://docs.blender.org/api/5.0/bpy.types.Speaker.html), [sound operators / mixdown](https://docs.blender.org/api/blender_python_api_current/bpy.ops.sound.html), [mixdown bug #99039](https://developer.blender.org/T99039), [GSoC 2011 3D audio](https://wiki.blender.org/index.php/User:NeXyon/GSoC2011/3D_Audio/Speaker_Objects), [bmusic speaker tutorial](https://bmusic.readthedocs.io/en/latest/tutorials/speaker.html)
- [audaspace](https://github.com/neXyon/audaspace)
- [Steam Audio](https://partner.steamgames.com/doc/features/steam_audio), [audionimbus-sys (Rust)](https://docs.rs/audionimbus-sys), [Steam Audio 4.0](https://www.phoronix.com/news/Steam-Audio-SDK-4.0)
- [Pyroomacoustics](https://infoscience.epfl.ch/record/261435?ln=en), [DynamicSound](https://arxiv.org/html/2601.15433v1), [SONNET segmented moving source](https://arxiv.org/pdf/2411.13179)
- [JOS: Doppler simulation](https://ccrma.stanford.edu/~jos/pasp/Doppler_Simulation.html), [DAFx-02 Doppler and the Leslie](https://ccrma.stanford.edu/%7Ejos/doppler/dafx02.pdf), [variable delay line software](https://ccrma.stanford.edu/~jos/doppler/Variable_Delay_Line_Software.html), [time-varying delay reads](https://ccrma.stanford.edu/~jos/pasp05/Time_Varying_Delay_Line_Reads.html)
- [spaudiopy](https://spaudiopy.readthedocs.io/en/latest/spaudiopy.io.html), [hrtfpykit](https://hrtfpykit.readthedocs.io/en/latest/), [python-sofa](https://python-sofa.readthedocs.io/_/downloads/en/latest/pdf/), [omi_audio](https://github.com/mcfletch/omi_audio)
- Resolve: [Fairlight ambisonics discussion](https://forum.blackmagicdesign.com/viewtopic.php?p=1145515), [Resolve 19 audio tools](https://www.pro-tools-expert.com/production-expert-1/davinci-resolve-19-beta-1-announced-with-impressive-audio-tools), [Resolve 20.1 and ASAF](https://www.mixonline.com/news/quick-mix-august-7-2025-blackmagic-design-the-old-sawmills-focusrite-live-nation-and-more), [multichannel import thread](https://forum.blackmagicdesign.com/viewtopic.php?p=877844), [Resolve 18.6](https://www.production-expert.com/production-expert-1/blackmagic-design-annnounce-davinci-resolve-186)
