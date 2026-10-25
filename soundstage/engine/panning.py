"""Pan laws and panners.

- Pan laws (registry ``PAN_LAWS``, setting ``pan_law``): ``sine`` (phi = (lambda+1) pi/4) and
  ``power`` (g^2 = (1 +- lambda)/2, Blender's speakers). Both constant power.
- Panners (registry ``PANNERS``, setting ``panner``): ``amplitude`` (pan law only) and ``hybrid``
  (pan law, Woodworth ITD scaled by ``itd_scale``, Brown-Duda head shadow per ear scaled by
  ``head_shadow``, rear cue). A panner supplies per-ear delays, per-ear stages and gains from the
  path (ADR 0009); ``binaural`` follows in Phase 4.

Spec: docs/spec/signal-model.md#panning; decision: ADR 0007.
"""

from __future__ import annotations

import numpy as np

from soundstage.engine import filters


def sine_law(lateral: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Left and right gains for lateral sines in [-1, 1]; gL^2 + gR^2 = 1, centre -3.01 dB each."""
    phi = (np.clip(lateral, -1.0, 1.0) + 1.0) * (np.pi / 4.0)
    return np.cos(phi), np.sin(phi)


def power_law(lateral: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Power split linearly with the lateral sine (Blender's speakers): gL^2 = (1 - l)/2."""
    lam = np.clip(lateral, -1.0, 1.0)
    return np.sqrt(0.5 * (1.0 - lam)), np.sqrt(0.5 * (1.0 + lam))


PAN_LAWS = {"sine": sine_law, "power": power_law}


def woodworth_itd(lateral: np.ndarray, head_radius: float, speed_of_sound: float, scale: float) -> np.ndarray:
    """ITD in seconds, positive when the source is on the right (right ear leads)."""
    theta = np.arcsin(np.clip(lateral, -1.0, 1.0))
    return scale * (head_radius / speed_of_sound) * (theta + np.sin(theta))


class AmplitudePanner:
    name = "amplitude"
    rear_cue = False

    def __init__(self, settings: dict):
        self.settings = settings
        self.law = PAN_LAWS[settings["pan_law"]]

    def itd(self, path) -> np.ndarray | None:
        return None

    def ear_stages(self, path, rate: int) -> tuple[list, list]:
        return [], []

    def gains(self, path) -> tuple[np.ndarray, np.ndarray]:
        return self.law(path.lateral)


class HybridPanner(AmplitudePanner):
    name = "hybrid"
    rear_cue = True

    def itd(self, path) -> np.ndarray | None:
        s = self.settings
        if s["itd_scale"] <= 0:
            return None
        return woodworth_itd(path.lateral, s["head_radius"], s["speed_of_sound"], s["itd_scale"])

    def ear_stages(self, path, rate: int) -> tuple[list, list]:
        s = self.settings
        if s["head_shadow"] <= 0:
            return [], []
        stages = []
        for cos_theta in (-path.lateral, path.lateral):  # left ear axis -X, right ear +X
            alpha = filters.head_shadow_alpha(cos_theta, s["head_shadow"])
            b0, b1, a1 = filters.head_shadow_coefficients(alpha, s["head_radius"], s["speed_of_sound"], rate)
            stages.append([filters.ShelfStage(path.grid, b0, b1, a1, path.jumps)])
        return stages[0], stages[1]


PANNERS = {"amplitude": AmplitudePanner, "hybrid": HybridPanner}
