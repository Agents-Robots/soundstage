"""Panners: constant-power ``amplitude`` and ``hybrid`` (pan + scaled ITD + head shadow).

Computes per-ear gains (and hands ITD and head-shadow parameters to propagation and filters) from
the lateral angle of the retarded source direction. ``binaural`` (SOFA HRIR convolution) is added
in Phase 4.

Spec: docs/spec/signal-model.md#panning; decision: ADR 0007. Phase 1 (amplitude), Phase 2 (hybrid).
"""
