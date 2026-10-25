"""Distance gain, panning, cones, rear cue (Phase 1, Phase 2).

- inverse_clamped, rolloff 1: -6.02 dB +/- 0.1 dB at 2x ref_distance; unity inside ref_distance.
- linear_clamped reaches 0 at max_distance; exponential matches (d/ref)^-rolloff.
- Constant-power pan: gL^2 + gR^2 == 1 over a full sweep; source on +X is louder right.
- Source passing through the camera: pan and gain change smoothly (near-field softening).
- Cone: unity inside inner/2, outer gain beyond outer/2, linear in between.
- Rear cue: no effect in front and at the side; full rear_gain_db and cutoff straight behind.
"""
