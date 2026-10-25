"""Render and output (Phase 1, Phase 3).

- Output length and alignment: sample 0 = first frame for several frame rates.
- Float WAV written as 32-bit float; PCM_24 option dithered.
- Solo/mute and frame sub-ranges render only what is selected; sub-range sample 0 = its first frame.
- Determinism: two renders of the same scene are bit-identical.
- Camera cut: no sample step above the bound across the cut, no Doppler sweep.
- Stems sum to the master within float rounding (Phase 3).
- Report: LUFS matches pyloudnorm on the written file; true peak within 0.1 dB of a 4x
  oversampled reference (Phase 3).
"""
