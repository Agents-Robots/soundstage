# Survey: existing solutions, libraries, formats

Done on 2026-10-25 before the design, updated after Phases 0, 2 and 3, and on 2026-10-29 for
many sources and the camera lens. Facts about third-party
tools reflect what was found then; recheck before relying on details. The acoustic models
themselves are in [models/](models/), measurements in [experiments/](experiments/).

## Existing solutions

| Option | Has | Missing / problem | Verdict |
|---|---|---|---|
| **Blender Speaker objects + `bpy.ops.sound.mixdown`** (audaspace inside Blender) | Distance models, attenuation, reference/max distance, cone, Doppler settings (speed of sound + factor), constant-power panning relative to the active camera; mono sources only for 3D | Measured in Phase 0 ([E01](experiments/E01-blender-speaker-baseline.md)): no Doppler shift in rendered audio, 3D parameters stepped once per audio buffer, headless mixdown leaves speakers out (a video render works), 16-bit audio from renders; no delay, air absorption, occlusion, reverb or stems; little control or insight | **Baseline** (`tools/blender_mixdown.py`). Speaker objects are read as sources (FR-8, [ADR 0012](../docs/adr/0012-speakers-and-instanced-tags-as-sources.md)). |
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

## Many sources

How games, film tools and research handle thousands of sources (traffic, aircraft, armies), done
after [E16](experiments/E16-culling.md) showed that culling alone does not make render time
independent of the number of sources.

| Approach | Where | How it works | For soundstage |
|---|---|---|---|
| **Voice limits, virtual voices** | Wwise, FMOD, Unreal (Sound Concurrency) | A fixed number of voices is mixed; the rest are virtual: tracked, not mixed, resumed at the right position. Which ones go virtual follows an audibility estimate (FMOD: distance, volume, priority, occlusion) or a volume threshold. Per-sound, per-bus and global limits; Unreal resolves a full group by stopping the farthest, quietest, lowest-priority or oldest sound | Real-time engines trade error for a fixed CPU budget: an audible sound can be dropped. Culling (`cull_db`) is the offline counterpart with a bounded error |
| **HDR audio** | Wwise | A dynamic window follows the loudest sound; voices below the window are virtualised | Close to the per-group relative budget of culling |
| **One voice, many positions** | Wwise multi-position (`SetMultiplePositions`, MultiSources / MultiDirections) | One signal played from many positions (a river, a row of torches) at the cost of one voice; the positions cannot have their own gains or sounds | Sources sharing a sample could share one dry signal and one voice |
| **Density-driven beds** | The Witcher 3 (NPCs counted in four quadrants around the listener, sent to Wwise as parameters), CRIWARE's crowd example (low/medium/high density loops crossfaded by one parameter), Ghost of Tsushima's ambience system; RTS practice: one composite sound per unit at a distance | Individual emitters only near the listener; everything farther is a designed bed whose layers and level follow the count or density per direction | The common game answer for crowds and traffic. In soundstage terms: per direction sector, a bed driven by the power of the distant sources it replaces |
| **Clustering** | Research: Tsingos, Gallo, Drettakis 2004 (hundreds of moving sources: culling by masking, dynamic clustering, pre-mix per cluster); Moeck et al. 2007 (thousands of sources on a PC: hierarchical clustering, progressive pre-mix; listeners wanted more clusters on visible sources). Product: Dolby Atmos spatial coding (Breebaart et al. 2019) groups up to 128 objects into 12–16 elements for delivery | Group sources by position and loudness, mix each group's signals, render the group as one source at its centroid | [#31](https://github.com/Agents-Robots/soundstage/issues/31). Atmos shows the error is acceptable in professional delivery |
| **Stochastic sampling** | Wand, Straßer 2004 | A hierarchy of sample sources; louder sources are picked more often. A stadium of about 16 000 fans was rendered from 2000 sampled sources with acceptable quality | Efficient mainly for static sources |
| **Particle renderer** | Sound Particles (used in film and game post-production) | Thousands to millions of "particles" (sources) with random sounds, motion and gain/delay/EQ/pitch variation, distance, speed of sound, Doppler and air, rendered to a virtual microphone (mono to Atmos); FBX import from animation | The closest product to soundstage; its documentation does not say how it scales |
| **Recorded aggregates** | Film: the Uruk-hai chant in *The Two Towers* was recorded with a cricket crowd of about 25 000 in Wellington; Total War uses group vocal recordings for battle scale | The crowd is recorded as a crowd, and individual hero sounds are placed on top | A recorded bed instead of simulated soldiers |
| **Traffic auralization** | Acoustics research: traffic flow built from synthesised single pass-bys (Fu et al.), superposition of pass-bys (TAURA); environmental noise models treat roads as line sources | Individual vehicles near the listener, superposition or line sources for the flow | Same as soundstage near the camera; a line source or bed for far traffic |

Conclusion: no professional system renders thousands of sources individually at full detail. All
of them keep a few near, loud sources individual and represent the rest by aggregates: clusters,
beds driven by density, shared voices. Real-time engines also never hold whole-shot arrays per
source; they process one buffer at a time, which is why their memory does not grow with the shot
length ([#32](https://github.com/Agents-Robots/soundstage/issues/32)).

## Camera lens and sound direction

Whether the camera's field of view should change where sources are heard.

| Approach | Where | How the direction is chosen |
|---|---|---|
| **Ears at the camera** | Games (Unity, Unreal, Wwise, FMOD: the listener is placed at the camera), Blender's speakers ([E01](experiments/E01-blender-speaker-baseline.md)), soundstage | Direction relative to the camera's orientation; the field of view plays no part |
| **Split listener** | Third-person games: CRIWARE Focus Point (distance from the character, direction from the camera), Unreal's listener attenuation override (attenuation at the player, panning at the camera), Wwise's distance probe | Direction still from the camera, without the lens |
| **View cone emphasis** | Unreal attenuation focus (`FocusAzimuth` 30°, `NonFocusAzimuth` 60° by default) | Sounds outside a cone around the view direction are attenuated and lose priority; the cone is a setting, not the lens |
| **Screen as the frame of reference** | Film and TV mixing: on-screen dialogue in the centre, effects panned by hand to their place in the frame, off-screen sounds to the side or the surrounds. Dolby Atmos places objects in room coordinates whose front wall is the screen | Panning follows the picture, so a zoom or a cut changes where a sound is panned |
| **Screen-related remapping and zoom** | MPEG-H 3D Audio (ISO/IEC 23008-3): objects flagged `isScreenRelativeObject` are remapped from the reference screen of the mix to the playback screen. Azimuths between the reference screen edges map linearly onto the playback screen edges, and the rest is stretched piecewise to cover the full circle. Extensions remap for a zoomed area of the picture; a related method adapts higher-order ambisonics to the screen | Direction follows the picture geometry on the actual screen |
| **Acoustic zoom** | Research (Schultz-Amling et al. 2010, Fraunhofer, on DirAC): the spatial audio follows the visual zoom; a zoom changes the view angle, not the camera position, so it is not the same as moving the listener | Directions remapped consistently with the image |

Perception: viewers fuse a sound with its picture across offsets of about 10–20° (untrained
listeners about 15–19°, trained ones about 9–10°), more when the source is visible.

For soundstage ([E17](experiments/E17-lens-and-pan.md)): with the default 50 mm lens a source at
the frame edge is heard at 9° on ±30° loudspeakers, where an HD viewer at 3 picture heights sees
the edge at 16.5°; with a 200 mm lens at 2.3°. Ears at the camera are right for distance, delay,
Doppler and occlusion (a zoom does not move the camera). The professional answer for the direction
is the picture: film mixers and MPEG-H pan on-screen sources to their position on the screen. A
lens-aware pan would need the camera's field of view in the bake.

## Libraries

| Library | Use | Notes |
|---|---|---|
| numpy, scipy | Arrays, `CubicSpline` (positions), `spatial.transform.RotationSpline` (camera rotation), `optimize.least_squares` (air-absorption fit), `signal` (filter design, spectrogram, test measurements) | Core |
| soundfile (libsndfile) | Read WAV/FLAC/OGG, write WAV float/PCM | Core |
| soxr (python-soxr) | High-quality sample-rate conversion | Core; better and faster than `resample_poly` for arbitrary ratios |
| numba | Per-sample kernels: time-varying filters, fractional-delay reads, control-rate interpolation; `nogil` so sources render in parallel threads | Core (ADR 0002) |
| pyloudnorm | BS.1770 integrated loudness, normalization, K-weighting filters (for the loudness range) | Core (report) |
| pedalboard (Spotify) | Limiter, reverb, VST3 hosting | Considered for Phase 3, not used: its limiter works on sample peaks and its gain cannot be applied to stems; the reverb is synthesized from EFX presets instead ([mixing and loudness](models/mixing-and-loudness.md), [reverb](models/reverb.md)) |
| matplotlib | Debug plot | Optional extra `plot` |
| sofar | Read SOFA HRTF files (binaural, Phase 4) | Optional extra `hrtf`; alternatives: spaudiopy (also ambisonics/SH tools), hrtfpykit (research-oriented, 2026), python-sofa |
| Blender `aud` | Only in `tools/blender_mixdown.py` (Phase 0 baseline); its loop/limit chains and file writer are unreliable ([E01](experiments/E01-blender-speaker-baseline.md)). Blender 5.2.2 ships numpy 2.3.4, which bake uses | Checked in Blender 5.2.2 |
| pyfar | ISO 9613-1 air attenuation, filters, SOFA | Considered for air absorption; not needed for one formula ([air absorption](models/air-absorption.md)) |

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
- Models and experiments: see the references in each document under models/ and experiments/, and [papers/](papers/README.md). Phase 2 web sources: [JOS: time-varying delay reads](https://ccrma.stanford.edu/~jos/pasp/Time_Varying_Delay_Line_Reads.html), [JOS: bandlimited resampling implementation](https://ccrma.stanford.edu/~jos/resample/Implementation.html), [JOS: windowed sinc interpolation](https://ccrma.stanford.edu/~jos/pasp/Windowed_Sinc_Interpolation.html), [O. Niemitalo: Polynomial interpolators for high-quality resampling of oversampled audio](http://yehar.com/blog/wp-content/uploads/2009/08/deip.pdf), [scipy RotationSpline](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.transform.RotationSpline.html), [ISO 9613-1 formula (sengpielaudio)](https://sengpielaudio.com/AirdampingFormula.htm), [pyfar air attenuation](https://pyfar.readthedocs.io/en/latest/_modules/pyfar/constants/constants.html), [V. Zavalishin: Preserving the LTI system topology in s- to z-plane transforms](https://www.native-instruments.com/fileadmin/redaktion_upload/pdf/KeepTopology.pdf), [Csound zdf_1pole](https://csound.com/manual/opcodes/zdf_1pole/), [KVR: smooth filter changes](https://www.kvraudio.com/forum/viewtopic.php?p=8608941), [auditory.org: Brown–Duda head shadow in Sound Sprocket](https://auditory.org/postings/1996/175.html), [Princeton 3D3A: spherical head ITD](https://3d3a.princeton.edu/document/166), [Lee and Rumsey: level and time panning of phantom images](https://eprints.hud.ac.uk/19670), [Ardour: stereo panner and comb filtering](https://manual.ardour.org/mixing/panning/stereo_panner/), [Amplitude panning (sine and tangent law)](https://en.wikipedia.org/wiki/Amplitude_panning), [OpenAL Soft stereo panning response](https://github.com/kcat/openal-soft/issues/194), [pyroomacoustics](https://ar5iv.labs.arxiv.org/html/1710.04196)
- Many sources: [FMOD virtual voices](https://fmod.com/docs/2.03/api/managing-resources-in-the-core-api.html), [Unreal Sound Concurrency](https://dev.epicgames.com/documentation/en-us/unreal-engine/sound-concurrency-reference-guide), [Wwise HDR audio](https://designingsound.org/2013/06/21/finding-your-way-with-high-dynamic-range-audio-in-wwise/), [Wwise virtual voices Q&A](https://audiokinetic.com/qa/6164/virtual-voices-bad-practice?show=6174), [Wwise multi-position Q&A](https://www.audiokinetic.com/qa/1177/how-do-i-simulate-a-sound-that-is-not-a-point-sound-source), [Wwise Unreal integration: multiple positions](https://documentation.help/Wwise-UE4-Integration/features__blueprint.html), [Witcher 3 crowds and walla (Wwise Tour 2016)](https://www.audiokinetic.com/learn/videos/bv4LBbrmu0A), [CRIWARE crowd system](https://blog.criware.com/index.php/2023/05/08/crowd-system/), [Ghost of Tsushima ambience (GDC)](https://gdcvault.com/play/1026976/Big-World-Small-Team-Designing), [Unity forum: hundreds to thousands of audio sources](https://discussions.unity.com/t/what-is-the-recommended-way-to-manage-hundreds-to-thousands-of-audio-sources/809600), [Moeck et al. 2007](https://researchportal.ip-paris.fr/en/publications/progressive-perceptual-audio-rendering-of-complex-scenes/), [Wand and Straßer: SIGGRAPH 2004 talk](https://history.siggraph.org/wp-content/uploads/2022/12/2004-Talks-Wand_Multi-Resolution-Sound-Rendering.pdf), [Breebaart et al. 2019 (AES)](https://aes2.org/publications/elibrary-page/?id=20487), [Avid: delivering Dolby Atmos (spatial coding elements)](https://www.avid.com/resource-center/encoding-and-delivering-dolby-atmos-music), [Sound Particles (product description)](https://www.pluginboutique.com/products/6425-Sound-Particles-Pro), [Helm's Deep crowd recording (TheOneRing.net, 2002)](https://theonering.net/torwp/2002/02/16/22715-spy-report-from-tt-sound-test-at-nz-cricket-match-2), [Total War: Three Kingdoms audio](https://gamedeveloper.com/audio/behind-the-audio-of-i-total-war-three-kingdoms-i-), [Fu et al.: traffic flow auralisation](https://etheses.whiterose.ac.uk/28802/6/Fu_203026484_ThesisDeposit.pdf), [Dreier and Vorländer: vehicle pass-by auralization](https://author.ioa.org.uk/conference-proceeding/internoise-proceedings-v3/171-dreir)
- Camera lens and sound direction: [CRIWARE Focus Point](https://blog.criware.com/?p=3854), [Wwise Q&A: distance from the player, panning from the camera](https://www.audiokinetic.com/qa/6112/unity-distance-relative-the-player-panning-relative-camera), [Wwise distance probe Q&A](https://audiokinetic.com/qa/12743/how-does-distance-probe-interact-with-reverb-volume-unreal), [Unreal attenuation focus settings](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/SoundAttenuationSettings), [panning in film post (PremiumBeat)](https://www.premiumbeat.com/blog/sonic-space-in-video-projects/), [dialogue panning in *Gravity* (Designing Sound)](https://designingsound.org/2014/01/30/dialogue-on-the-move-panning-in-gravity-cars-and-strange-days/), [Dolby: Atmos object coordinates (patent US10334387)](https://patents.google.com/patent/US10334387), [MPEG-H screen-related object remapping (patent US10192563)](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10192563), [audio linked with video zoom (patent US10986457)](https://patents.google.com/patent/US10986457), [screen-related adaptation of HOA (patent US10771912)](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10771912), [Schultz-Amling et al. 2010: acoustical zooming](https://publica.fraunhofer.de/handle/publica/366604), [consistent acoustic scene reproduction (patent application US20170078819)](https://patents.justia.com/patent/20170078819), [audio-visual alignment of central and peripheral events](https://arxiv.org/pdf/2003.06656), [horizontal audio-visual spatial congruence (Surrey thesis)](https://openresearch.surrey.ac.uk/esploro/outputs/doctoral/Influences-on-perceived-horizontal-audio-visual-spatial/99511762002346), [SMPTE RP 173](https://pub.smpte.org/latest/rp173/rp0173-2002_withdrawn2011.pdf), [ITU-R BS.775-1](https://itu.int/dms_pubrec/itu-r/rec/bs/R-REC-BS.775-1-199407-S!!PDF-F.pdf)
- [spaudiopy](https://spaudiopy.readthedocs.io/en/latest/spaudiopy.io.html), [hrtfpykit](https://hrtfpykit.readthedocs.io/en/latest/), [python-sofa](https://python-sofa.readthedocs.io/_/downloads/en/latest/pdf/), [omi_audio](https://github.com/mcfletch/omi_audio)
- Resolve: [Fairlight ambisonics discussion](https://forum.blackmagicdesign.com/viewtopic.php?p=1145515), [Resolve 19 audio tools](https://www.pro-tools-expert.com/production-expert-1/davinci-resolve-19-beta-1-announced-with-impressive-audio-tools), [Resolve 20.1 and ASAF](https://www.mixonline.com/news/quick-mix-august-7-2025-blackmagic-design-the-old-sawmills-focusrite-live-nation-and-more), [multichannel import thread](https://forum.blackmagicdesign.com/viewtopic.php?p=877844), [Resolve 18.6](https://www.production-expert.com/production-expert-1/blackmagic-design-annnounce-davinci-resolve-186)
