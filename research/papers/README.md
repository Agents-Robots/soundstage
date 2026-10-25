# Papers and standards

The sources behind the acoustic models. Openly accessible PDFs are downloaded by
[`fetch.py`](fetch.py) into `research/papers/pdf/<key>.pdf`; that folder is gitignored, because
several copies are author or publisher copies that may be read but not redistributed, and the
repository may become public.

```bash
python3 research/papers/fetch.py        # stdlib only; skips files already present
```

| Key | Reference | Used for | Open copy |
|---|---|---|---|
| `smith2002doppler` | J. O. Smith, S. Serafin, J. Abel, D. Berners, "Doppler Simulation and the Leslie", Proc. DAFx-02, Hamburg, 2002 | Doppler as a time-varying delay driven by geometry ([doppler and delay](../models/doppler-and-delay.md)) | CCRMA |
| `smith2002resample` | J. O. Smith, "Digital Audio Resampling" (online book; method of Smith & Gossett, ICASSP 1984) | Bandlimited interpolation, cutoff scaling when reading faster ([fractional delay](../models/fractional-delay.md)) | CCRMA |
| `niemitalo2001` | O. Niemitalo, "Polynomial Interpolators for High-Quality Resampling of Oversampled Audio", 2001 | Optimal-2× 6-point polynomial and its coefficients ([fractional delay](../models/fractional-delay.md)) | author's site |
| `zavalishin2008tpt` | V. Zavalishin, "Preserving the LTI system topology in s- to z-plane transforms", Native Instruments, 2008 | TPT one-pole filters under modulation ([time-varying filters](../models/time-varying-filters.md)) | Internet Archive copy of the NI file |
| `zavalishin2020vafilter` | V. Zavalishin, "The Art of VA Filter Design", rev. 2.1.2, 2020 | TPT/zero-delay-feedback filter structures ([time-varying filters](../models/time-varying-filters.md)) | mirror; the book allows unmodified copies |
| `brown1998` | C. P. Brown, R. O. Duda, "A Structural Model for Binaural Sound Synthesis", IEEE Trans. Speech and Audio Processing 6(5):476–488, 1998 | Head-shadow filter, ITD ([head shadow](../models/head-shadow.md), [ITD](../models/itd.md)) | UC eScholarship |
| `pulkki1997` | V. Pulkki, "Virtual Sound Source Positioning Using Vector Base Amplitude Panning", J. Audio Eng. Soc. 45(6):456–466, 1997 | Sine/tangent laws, constant-power panning ([panning](../models/panning.md)) | AudioLabs Erlangen course copy |
| `openal11` | OpenAL 1.1 Specification and Reference, Creative Labs, 2005 | Distance models, cone law ([distance](../models/distance-attenuation.md), [directivity](../models/directivity.md)) | openal.org |
| `fink2016` | M. Fink, M. Holters, U. Zölzer, "Signal-Matched Power-Complementary Cross-Fading and Dry-Wet Mixing", Proc. DAFx-16, Brno, 2016 | Correlation-adaptive loop crossfade ([loops and one-shots](../models/loops-and-one-shots.md)) | HSU Hamburg |
| `itu1770` | ITU-R BS.1770-4, "Algorithms to measure audio programme loudness and true-peak audio level", 2015 | LUFS and true peak in the report | ITU (free) |
| `dynamicsound2026` | DynamicSound, arXiv:2601.15433, 2026 | Confirms the delay-line method for moving sources ([survey](../survey.md)) | arXiv |
| `kapralos2007` | B. Kapralos, M. Jenkin, E. Milios, "Diffraction Modeling for Interactive Virtual Acoustical Environments", Proc. GRAPP 2007, pp. 241–248, doi:10.5220/0002075802410248 (Huygens–Fresnel visibility, with a review of diffraction methods) | How Tsingos and Gascuel compute occlusion from the first Fresnel zone ([occlusion](../models/occlusion.md)) | SciTePress |
| `valimaki2017velvet` | V. Välimäki, B. Holm-Rasmussen, B. Alary, H.-M. Lehtonen, "Late Reverberation Synthesis Using Filtered Velvet Noise", Applied Sciences 7(5):483, 2017 | Velvet-noise late tail for low-diffusion presets ([reverb](../models/reverb.md)) | Aalto (open access) |
| `albrecht2013distance` | R. Albrecht, T. Lokki, "Adjusting the perceived distance of virtual speech sources by modifying binaural room impulse responses", ICAD 2013 | Direct-to-reverberant ratio as a distance cue ([reverb](../models/reverb.md)) | Aalto |
| `ebu_r128` | EBU R 128, "Loudness normalisation and permitted maximum level of audio signals" | Loudness targets, −1 dBTP ([mixing and loudness](../models/mixing-and-loudness.md)) | EBU (free) |
| `ebu_tech3341` | EBU Tech 3341, "Loudness Metering: 'EBU Mode' metering to supplement EBU R 128 loudness normalization" | Test signals for the loudness meter ([E14](../experiments/E14-loudness-and-limiter.md)) | EBU (free) |
| `ebu_tech3342` | EBU Tech 3342, "Loudness Range: A measure to supplement EBU R 128 loudness normalization" | Loudness-range algorithm and test signals ([mixing and loudness](../models/mixing-and-loudness.md)) | EBU (free) |

Without an open copy (cited by reference only):

| Reference | Used for |
|---|---|
| ISO 9613-1:1993, "Acoustics – Attenuation of sound during propagation outdoors – Part 1: Calculation of the absorption of sound by the atmosphere" | Air absorption coefficient ([air absorption](../models/air-absorption.md)); the formula as reproduced by [sengpielaudio](https://sengpielaudio.com/AirdampingFormula.htm) and [pyfar](https://pyfar.readthedocs.io/en/latest/_modules/pyfar/constants/constants.html), checked against ISO 9613-2 Table 2 ([E05](../experiments/E05-air-absorption.md)) |
| ISO 9613-2:1996, Table 2 | Reference values for the test of the ISO 9613-1 implementation |
| T. I. Laakso, V. Välimäki, M. Karjalainen, U. K. Laine, "Splitting the Unit Delay – Tools for Fractional Delay Filter Design", IEEE Signal Processing Magazine 13(1):30–60, 1996, doi:10.1109/79.482137 | Background on fractional-delay filters ([fractional delay](../models/fractional-delay.md)) |
| H. Lee, F. Rumsey, "Level and Time Panning of Phantom Images for Musical Sources", J. Audio Eng. Soc. 61(12), 2013 ([abstract](https://eprints.hud.ac.uk/19670)) | Why level panning stays primary on loudspeakers ([ITD](../models/itd.md)) |
| R. S. Woodworth, *Experimental Psychology*, Holt, 1938 | ITD formula ([ITD](../models/itd.md)) |
| G. F. Kuhn, "Model for the interaural time differences in the azimuthal plane", J. Acoust. Soc. Am. 62(1):157–167, 1977 | Low-frequency ITD, why Woodworth is a high-frequency formula ([ITD](../models/itd.md)) |
| N. Tsingos, J.-D. Gascuel, "Soundtracks for Computer Animation: Sound Rendering in Dynamic Environments with Occlusions", Graphics Interface 1997 (`tsingos1997` in `fetch.py`; the proceedings server answers 403 to scripted downloads) | Fresnel-ellipsoid visibility for occlusion ([occlusion](../models/occlusion.md)) |
| N. Tsingos, J.-D. Gascuel, "Fast Rendering of Sound Occlusion and Diffraction Effects for Virtual Acoustic Environments", AES 104th Convention, 1998 | The same method with graphics hardware ([occlusion](../models/occlusion.md)) |
| D. Giannoulis, M. Massberg, J. D. Reiss, "Digital Dynamic Range Compressor Design — A Tutorial and Analysis", JAES 60(6):399–408, 2012 (`giannoulis2012` in `fetch.py`; the author's server failed the TLS handshake) | Real-time limiter designs, the alternative to the offline limiter ([mixing and loudness](../models/mixing-and-loudness.md)) |
| J. A. Moorer, "About This Reverberation Business", Computer Music Journal 3(2):13–28, 1979 | Exponentially decaying noise as late reverberation ([reverb](../models/reverb.md)) |
| V. Välimäki, J. Parker, L. Savioja, J. O. Smith, J. Abel, "Fifty Years of Artificial Reverberation", IEEE TASLP 20(5):1421–1448, 2012 | Survey of reverberation algorithms ([reverb](../models/reverb.md)) |
| A. W. Bronkhorst, T. Houtgast, "Auditory distance perception in rooms", Nature 397:517–520, 1999 | Direct-to-reverberant ratio and distance ([reverb](../models/reverb.md)) |
| Z. Maekawa, "Noise reduction by screens", Applied Acoustics 1(3):157–173, 1968 | Barrier attenuation from the Fresnel number, an alternative for occlusion ([occlusion](../models/occlusion.md)) |
| OpenAL Soft, `include/AL/efx-presets.h` (LGPL) | The 113 EFX reverb presets, converted by `tools/efx_presets.py` into `soundstage/engine/data/efx_presets.json` ([reverb](../models/reverb.md)) |

Equations in the PDFs are often images: render the page with `pdftoppm -f N -l N -r 110 -png
<pdf> <prefix>` (poppler-utils) and read the PNG; `pdftotext -layout` finds the page.
