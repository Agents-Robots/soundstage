"""E17: where a source at the edge of the frame is heard, against the camera lens.

The engine pans from the direction relative to the camera, independent of the lens. For a 36 mm
sensor and several focal lengths, a static 1 kHz source is placed at the right edge of the frame
(azimuth = half the horizontal field of view), 20 m away, and rendered with the amplitude panner.
The channel level difference is measured, and the phantom image angle it gives on loudspeakers at
±30° follows from the tangent law (Bennett et al. 1985; Pulkki 1997):
tan φ = tan 30° · (g_R − g_L) / (g_R + g_L). This is compared with the angle at which a viewer
sees the edge of the screen: 16:9 at 3 picture heights (the HD reference position of SMPTE RP 173)
and at 1.5 (a UHD viewing distance).

Second table: the same with ``pan_reference = "screen"`` (default ``screen_edge_deg`` 16.5°), for a
source at the frame edge, half way to it, and off-screen at 60°.
"""

import numpy as np

from common import render, sample, scene, sine, table

SENSOR_MM = 36.0
FOCALS_MM = [14, 24, 35, 50, 85, 135, 200, 400]
DISTANCE_M = 20.0
SPEAKER_DEG = 30.0


def edge_level_difference(azimuth_deg: float, focal_mm: float | None = None) -> float:
    """R/L level difference in dB of a source at the given azimuth (right of the view axis); with a
    focal length, panned through that lens (``pan_reference = "screen"``)."""
    a = np.radians(azimuth_deg)
    pos = [DISTANCE_M * np.sin(a), DISTANCE_M * np.cos(a), 0.0]  # listener looks along world +Y
    src = {"sample": sample("sine.wav", sine(1000.0, 3.0)), "mode": "loop"}
    settings = {"panner": "amplitude", "air_absorption": 0.0}
    frame = None
    if focal_mm is not None:
        settings["pan_reference"] = "screen"
        half = SENSOR_MM / 2 / focal_mm
        frame = (-half, half)
    sc = scene([src], [pos], frame_end=60, settings=settings, frame=frame)
    out = render.render(sc).audio[24000:-24000]
    left, right = (np.sqrt(np.mean(np.square(out[:, k]))) for k in (0, 1))
    return float(20 * np.log10(right / left))


def phantom_deg(level_difference_db: float, speaker_deg: float = SPEAKER_DEG) -> float:
    g = 10 ** (level_difference_db / 20)  # g_R / g_L
    return float(np.degrees(np.arctan(np.tan(np.radians(speaker_deg)) * (g - 1) / (g + 1))))


def screen_edge_deg(heights: float, aspect: float = 16 / 9) -> float:
    return float(np.degrees(np.arctan(aspect / 2 / heights)))


def main() -> None:
    hd, uhd = screen_edge_deg(3.0), screen_edge_deg(1.5)
    rows = []
    for f in FOCALS_MM:
        half = float(np.degrees(np.arctan(SENSOR_MM / 2 / f)))
        ild = edge_level_difference(half)
        rows.append([f"{f} mm", f"{2 * half:.1f}°", f"{half:.1f}°", f"{ild:.1f}", f"{phantom_deg(ild):.1f}°"])
    print(f"Viewer's angle to the screen edge: HD at 3H {hd:.1f}°, UHD at 1.5H {uhd:.1f}°.\n")
    print(table(["lens (36 mm sensor)", "horizontal field of view", "frame edge: azimuth",
                 "R/L level (dB)", "heard at (±30° speakers)"], rows))
    # the lens whose frame edge is heard at the HD screen edge: invert the sine pan law
    lam = 4 / np.pi * np.arctan(np.tan(np.radians(hd)) / np.tan(np.radians(SPEAKER_DEG)))
    print(f"\nFrame edge heard at the HD screen edge ({hd:.1f}°) for a lateral sine of {lam:.2f}: azimuth "
          f"{np.degrees(np.arcsin(lam)):.1f}°, a {SENSOR_MM / 2 / np.tan(np.arcsin(lam)):.0f} mm lens.")

    rows = []
    for f in FOCALS_MM:
        half = float(np.degrees(np.arctan(SENSOR_MM / 2 / f)))
        quarter = float(np.degrees(np.arctan(SENSOR_MM / 4 / f)))  # half way from the centre to the edge
        cells = [phantom_deg(edge_level_difference(az, f)) for az in (half, quarter, 60.0)]
        rows.append([f"{f} mm", *(f"{c:.1f}°" for c in cells), f"{phantom_deg(edge_level_difference(60.0)):.1f}°"])
    print("\nScreen-relative panning (screen_edge_deg 16.5°; on screen: atan(u tan 16.5°), 8.4° at u = 0.5):\n")
    print(table(["lens", "frame edge heard at", "half way heard at", "60° (off-screen) heard at",
                 "60°, camera mode"], rows))


if __name__ == "__main__":
    main()
