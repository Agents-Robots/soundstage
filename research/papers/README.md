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

Without an open copy (cited by reference only):

| Reference | Used for |
|---|---|
| ISO 9613-1:1993, "Acoustics – Attenuation of sound during propagation outdoors – Part 1: Calculation of the absorption of sound by the atmosphere" | Air absorption coefficient ([air absorption](../models/air-absorption.md)); the formula as reproduced by [sengpielaudio](https://sengpielaudio.com/AirdampingFormula.htm) and [pyfar](https://pyfar.readthedocs.io/en/latest/_modules/pyfar/constants/constants.html), checked against ISO 9613-2 Table 2 ([E05](../experiments/E05-air-absorption.md)) |
| ISO 9613-2:1996, Table 2 | Reference values for the test of the ISO 9613-1 implementation |
| T. I. Laakso, V. Välimäki, M. Karjalainen, U. K. Laine, "Splitting the Unit Delay – Tools for Fractional Delay Filter Design", IEEE Signal Processing Magazine 13(1):30–60, 1996, doi:10.1109/79.482137 | Background on fractional-delay filters ([fractional delay](../models/fractional-delay.md)) |
| H. Lee, F. Rumsey, "Level and Time Panning of Phantom Images for Musical Sources", J. Audio Eng. Soc. 61(12), 2013 ([abstract](https://eprints.hud.ac.uk/19670)) | Why level panning stays primary on loudspeakers ([ITD](../models/itd.md)) |
| R. S. Woodworth, *Experimental Psychology*, Holt, 1938 | ITD formula ([ITD](../models/itd.md)) |
| G. F. Kuhn, "Model for the interaural time differences in the azimuthal plane", J. Acoust. Soc. Am. 62(1):157–167, 1977 | Low-frequency ITD, why Woodworth is a high-frequency formula ([ITD](../models/itd.md)) |

Reading the PDFs' equations needs a PDF renderer (`pdftoppm` from poppler-utils), which is not
installed on the development machine; formulas taken from papers whose equations could not be
rendered are marked as checked against secondary sources in the model documents.
