# Architecture Decision Records

One file per decision: `NNNN-short-title.md`, numbered in order. Copy
[0000-template.md](0000-template.md).

Write an ADR when a choice is hard to reverse, affects how other parts are built, or rejected a
plausible alternative that someone might propose again. Don't edit an accepted ADR's decision.
Supersede it with a new one and set the old one's status to `Superseded by NNNN`. Later findings
that refine the implementation without changing the decision go in a `Notes` section at the end.

| ADR | Title | Status |
|---|---|---|
| [0001](0001-standalone-engine-with-blender-bake.md) | Standalone engine fed by a headless Blender bake | Accepted |
| [0002](0002-python-numpy-numba.md) | Python with numpy/scipy, numba for per-sample kernels | Accepted |
| [0003](0003-tags-as-custom-properties.md) | Sound sources as custom-property tags on objects | Accepted |
| [0004](0004-scene-interchange-json-npz.md) | Scene interchange as versioned JSON manifest plus NPZ arrays | Accepted |
| [0005](0005-output-48k-float-wav-frame-aligned.md) | Output 48 kHz 32-bit float WAV, sample 0 = first frame | Accepted |
| [0006](0006-propagation-retarded-time-delay-line.md) | Delay and Doppler from retarded time and a fractional-delay read | Accepted |
| [0007](0007-stereo-ear-model.md) | Stereo target with a hybrid ear model; binaural optional | Accepted |
| [0008](0008-cinematic-air-physics.md) | Cinematic air physics with overridable constants | Accepted |
| [0009](0009-processing-chain.md) | Per-source processing chain with replaceable models | Accepted |
| [0010](0010-occlusion-fresnel-visibility-box-occluders.md) | Occlusion from Fresnel-zone visibility against bounding boxes, baked in Blender | Accepted |
| [0011](0011-reverb-efx-presets-synthetic-ir.md) | Reverb: EFX presets synthesized into impulse responses, one send bus | Accepted |
| [0012](0012-speakers-and-instanced-tags-as-sources.md) | Speaker objects and tags inside instances are sources | Accepted |
