"""E08: Phase 2 known answers, measured on rendered output (the same scenes as tests/).

Delay at 343 m, Doppler for a moving source and a moving camera at 34.3 m/s, Doppler factor 0 and
2, ITD at 90 degrees, and the level/frequency behaviour at a camera cut.
"""

import numpy as np
from scipy.signal import correlate, resample_poly

from common import RATE, frequency, listener_at, render, rms_db, sample, scene, sine, table

PLAIN = {"panner": "amplitude", "air_absorption": 0.0}
C, V = 343.0, 34.3


def flyby(sine_path, moving="source", settings=None):
    frames = np.arange(1, 392, dtype=float)
    x = -220.0 + V * (frames - 1) / 30
    line = np.stack([x, np.zeros_like(x), np.zeros_like(x)], axis=1)
    s = {**PLAIN, **(settings or {})}
    if moving == "source":
        return scene([{"sample": sine_path}], (line + [0, 3, 0])[:, None, :], frame_end=390, settings=s)
    return scene([{"sample": sine_path}], [[0, 3, 0]], frame_end=390, settings=s, listener=listener_at(line))


def up_down(out):
    mono = out.sum(axis=1)
    return frequency(mono[int(2.0 * RATE): int(2.5 * RATE)]), frequency(mono[int(11.5 * RATE): int(12.0 * RATE)])


def main() -> None:
    tone = sample("sine.wav", sine())
    click = np.zeros(RATE // 2)
    click[0] = 1.0
    click_path = sample("click.wav", click)
    rows = []

    out = render.render(scene([{"sample": click_path, "mode": "once", "frame": 10}], [[0, 343, 0]], frame_end=90,
                              settings=PLAIN)).audio
    got = (int(np.argmax(np.abs(out).max(axis=1))) - 9 * 1600) / RATE
    rows.append(["delay of a click at 343 m", "1.000000 s", f"{got:.6f} s"])

    for label, moving, settings, expect in (
            ("moving source, k = 1", "source", None, (C / (C - V), C / (C + V))),
            ("moving camera, k = 1", "camera", None, ((C + V) / C, (C - V) / C)),
            ("moving source, k = 0", "source", {"doppler_factor": 0.0}, (1.0, 1.0)),
            ("moving source, k = 2", "source", {"doppler_factor": 2.0}, (1 + 2 * V / (C - V), 1 - 2 * V / (C + V)))):
        up, down = up_down(render.render(flyby(tone, moving, settings)).audio)
        rows.append([f"Doppler, {label}", f"{1000 * expect[0]:.1f} / {1000 * expect[1]:.1f} Hz", f"{up:.1f} / {down:.1f} Hz"])

    noise = sample("noise.wav", np.random.default_rng(3).standard_normal(RATE // 4) * 0.3)
    for scale in (1.0, 0.5):
        s = {"panner": "hybrid", "head_shadow": 0.0, "itd_scale": scale, "air_absorption": 0.0, "rear_gain_db": 0.0}
        out = render.render(scene([{"sample": noise, "mode": "once", "frame": 5}], [[100, 0, 0]], settings=s)).audio
        left, right = (resample_poly(out[:, i], 4, 1) for i in (0, 1))
        lag = (np.argmax(correlate(left, right, mode="full")) - (len(right) - 1)) / (4 * RATE)
        rows.append([f"ITD at 90°, itd_scale {scale}", f"{0.656 * scale:.3f} ms", f"{lag * 1000:.3f} ms"])

    frames = np.arange(1, 62, dtype=float)
    cam = np.zeros((len(frames), 3))
    cam[frames >= 31, 1] = -95.0
    out = render.render(scene([{"sample": tone}], [[0, 5, 0]], settings=PLAIN, listener=listener_at(cam),
                              cuts=(31,))).audio[:, 0]
    cut = RATE
    near, far = out[cut - RATE // 2: cut - 2000], out[cut + 600: cut + RATE // 2]
    rows.append(["camera cut 5 m → 100 m: level change", f"{20 * np.log10(5 / 100):.2f} dB",
                 f"{rms_db(far) - rms_db(near):.2f} dB"])
    rows.append(["camera cut: frequency 12-60 ms after", "1000.0 Hz", f"{frequency(out[cut + 600: cut + 3000]):.1f} Hz"])
    step = np.abs(np.diff(out[cut - 2000: cut + 2000])).max() / (2 * np.pi * 1000 / RATE * np.abs(near).max())
    rows.append(["camera cut: largest sample step / sine's own", "≤ 1.5", f"{step:.2f}"])
    print(table(["quantity", "expected", "measured"], rows))


if __name__ == "__main__":
    main()
