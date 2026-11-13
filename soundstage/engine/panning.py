"""Pan laws and panners.

- Pan laws (registry ``PAN_LAWS``, setting ``pan_law``): ``sine`` (phi = (lambda+1) pi/4) and
  ``power`` (g^2 = (1 +- lambda)/2, Blender's speakers). Both constant power.
- Panners (registry ``PANNERS``, setting ``panner``): ``amplitude`` (pan law only) and ``hybrid``
  (pan law with the level difference limited to ``ild_limit_db`` off-screen, Woodworth ITD scaled
  by ``itd_scale``, Brown-Duda head shadow per ear scaled by ``head_shadow``, rear cue). A panner supplies per-ear delays, per-ear stages and gains from the
  path (ADR 0009); ``binaural`` follows in Phase 4.
- Screen-relative panning (setting ``pan_reference = "screen"``, the default): the lateral sine is remapped so
  that a source in the frame is heard, on loudspeakers at +-30 deg, where a viewer sees it on a
  screen whose edges are ``screen_edge_deg`` from the centre (tangent law); off-screen directions
  are stretched to +-90 deg, directions behind the camera are kept.

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

SPEAKER_DEG = 30.0
"""Loudspeaker angle the screen mapping is calibrated for (ITU-R BS.775 stereo)."""


def _law_inverse(law, ratio: np.ndarray) -> np.ndarray:
    """Lateral sine at which ``law`` gives the channel ratio (g_R - g_L) / (g_R + g_L)."""
    lam = np.linspace(-1.0, 1.0, 4097)
    gl, gr = law(lam)
    return np.interp(ratio, (gr - gl) / (gr + gl), lam)


def screen_lateral(q: np.ndarray, tan_left: np.ndarray, tan_right: np.ndarray, edge_deg: float, law,
                   r_min: float) -> np.ndarray:
    """Lateral sine (n,) for camera-space vectors q (n, 3), panning through the lens.

    ``tan_left``/``tan_right`` (n,) are x / -z of the frame edges (NaN: no perspective camera, the
    direction relative to the camera is used). In the frame, the image coordinate
    u = (tan(azimuth) - centre) / half width is heard at atan(u * tan(edge_deg)) by the tangent law;
    between the frame edges and +-90 deg the lateral sine runs linearly in azimuth to +-1.
    """
    x, z = q[:, 0], q[:, 2]
    horizontal = np.hypot(x, z)
    r_e = np.sqrt(np.einsum("ni,ni->n", q, q) + r_min * r_min)
    theta = np.arctan2(x, -z)  # azimuth, 0 ahead, positive right
    lam = np.sin(theta)  # camera mode, also behind the camera and without a frame
    ok = np.isfinite(tan_left) & np.isfinite(tan_right) & (tan_right > tan_left)
    tl, tr = np.where(ok, tan_left, -1.0), np.where(ok, tan_right, 1.0)
    th_l, th_r = np.arctan(tl), np.arctan(tr)
    k = np.tan(np.radians(edge_deg)) / np.tan(np.radians(SPEAKER_DEG))
    edge = _law_inverse(law, np.array([-k, k]))
    with np.errstate(divide="ignore", invalid="ignore"):
        u = (np.tan(theta) - 0.5 * (tr + tl)) / (0.5 * (tr - tl))
        inside = _law_inverse(law, np.clip(u, -1.0, 1.0) * k)
        right = edge[1] + (1.0 - edge[1]) * (theta - th_r) / (np.pi / 2 - th_r)
        left = edge[0] - (1.0 + edge[0]) * (th_l - theta) / (th_l + np.pi / 2)
    front = np.abs(theta) <= np.pi / 2
    mapped = np.where(theta > th_r, right, np.where(theta < th_l, left, inside))
    lam = np.where(ok & front, mapped, lam)
    return lam * horizontal / r_e


def limited_lateral(lateral: np.ndarray, knee: float, limit: float) -> np.ndarray:
    """Lateral sine for the pan gains with the channel level difference limited: unchanged up to
    ``knee`` (the screen edge), then linear in the lateral sine to ``limit`` at +-1. A limit below the
    knee scales the whole range by ``limit`` instead."""
    if limit >= 1.0:
        return lateral
    a = np.abs(lateral)
    if limit < knee:
        return lateral * limit
    return np.sign(lateral) * np.where(a <= knee, a, knee + (limit - knee) * (a - knee) / (1.0 - knee))


def ild_limits(law, limit_db: float | None, edge_deg: float) -> tuple[float, float]:
    """(knee, limit) of ``limited_lateral``: the lateral sines at which ``law`` puts the screen edge
    (tangent law on loudspeakers at +-30 deg) and gives a level difference of ``limit_db``."""
    if limit_db is None:
        return 1.0, 1.0
    k = np.tan(np.radians(edge_deg)) / np.tan(np.radians(SPEAKER_DEG))
    f = 10.0 ** (-limit_db / 20.0)
    knee, limit = _law_inverse(law, np.array([k, (1.0 - f) / (1.0 + f)]))
    return float(knee), float(limit)


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

    def pan_gains(self, lateral: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return self.law(lateral)

    def gains(self, path) -> tuple[np.ndarray, np.ndarray]:
        return self.pan_gains(path.lateral)


class HybridPanner(AmplitudePanner):
    name = "hybrid"
    rear_cue = True

    def __init__(self, settings: dict):
        super().__init__(settings)
        self.knee, self.limit = ild_limits(self.law, settings["ild_limit_db"], settings["screen_edge_deg"])

    def pan_gains(self, lateral: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """The pan law with the level difference limited (ADR 0007): on headphones a source at the
        side is otherwise in one ear only."""
        return self.law(limited_lateral(lateral, self.knee, self.limit))

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
