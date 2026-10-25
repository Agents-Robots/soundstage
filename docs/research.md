# Research: existing solutions, libraries, formats

Done on 2026-10-25 before the design. Facts about third-party tools reflect what was found
then; recheck before relying on details.

## Existing solutions

| Option | Has | Missing / problem | Verdict |
|---|---|---|---|
| **Blender Speaker objects + `bpy.ops.sound.mixdown`** (audaspace inside Blender) | Distance models, attenuation, reference/max distance, cone, Doppler (speed of sound + factor), panning relative to the active camera, render to WAV/FLAC; mono sources only for 3D | Amplitude panning only; Doppler as a pitch effect without propagation delay; no air absorption, occlusion, reverb or stems; little control or insight; headless mixdown is poorly documented (bug reports exist) | **Baseline**: spiked in Phase 0 to have a reference to beat. Speaker objects are also read as an alternative tag source (FR-8). |
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

## Sources

- Blender: [aud module](https://docs.blender.org/api/5.1/aud.html), [Speaker API](https://docs.blender.org/api/5.0/bpy.types.Speaker.html), [sound operators / mixdown](https://docs.blender.org/api/blender_python_api_current/bpy.ops.sound.html), [mixdown bug #99039](https://developer.blender.org/T99039), [GSoC 2011 3D audio](https://wiki.blender.org/index.php/User:NeXyon/GSoC2011/3D_Audio/Speaker_Objects), [bmusic speaker tutorial](https://bmusic.readthedocs.io/en/latest/tutorials/speaker.html)
- [audaspace](https://github.com/neXyon/audaspace)
- [Steam Audio](https://partner.steamgames.com/doc/features/steam_audio), [audionimbus-sys (Rust)](https://docs.rs/audionimbus-sys), [Steam Audio 4.0](https://www.phoronix.com/news/Steam-Audio-SDK-4.0)
- [Pyroomacoustics](https://infoscience.epfl.ch/record/261435?ln=en), [DynamicSound](https://arxiv.org/html/2601.15433v1), [SONNET segmented moving source](https://arxiv.org/pdf/2411.13179)
- [JOS: Doppler simulation](https://ccrma.stanford.edu/~jos/pasp/Doppler_Simulation.html), [DAFx-02 Doppler and the Leslie](https://ccrma.stanford.edu/%7Ejos/doppler/dafx02.pdf), [variable delay line software](https://ccrma.stanford.edu/~jos/doppler/Variable_Delay_Line_Software.html), [time-varying delay reads](https://ccrma.stanford.edu/~jos/pasp05/Time_Varying_Delay_Line_Reads.html)
- [spaudiopy](https://spaudiopy.readthedocs.io/en/latest/spaudiopy.io.html), [hrtfpykit](https://hrtfpykit.readthedocs.io/en/latest/), [python-sofa](https://python-sofa.readthedocs.io/_/downloads/en/latest/pdf/), [omi_audio](https://github.com/mcfletch/omi_audio)
- Resolve: [Fairlight ambisonics discussion](https://forum.blackmagicdesign.com/viewtopic.php?p=1145515), [Resolve 19 audio tools](https://www.pro-tools-expert.com/production-expert-1/davinci-resolve-19-beta-1-announced-with-impressive-audio-tools), [Resolve 20.1 and ASAF](https://www.mixonline.com/news/quick-mix-august-7-2025-blackmagic-design-the-old-sawmills-focusrite-live-nation-and-more), [multichannel import thread](https://forum.blackmagicdesign.com/viewtopic.php?p=877844), [Resolve 18.6](https://www.production-expert.com/production-expert-1/blackmagic-design-annnounce-davinci-resolve-186)
