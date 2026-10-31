"""E07: retarded-time solver accuracy: plain fixed point (original spec) against the engine's
fixed point + Newton, for constant-velocity sources at Mach 0.1-0.95, with the analytic solution
(the pass is late in a long bake, so every emission time lies inside the baked range);
and the frequency error that the delay error causes (via the playback rate 1 - d tau/dt).
"""

import numpy as np  # noqa: E402

from soundstage.engine.control import ControlGrid  # noqa: E402
from soundstage.engine.geometry import SceneGeometry  # noqa: E402

from common import RATE, scene, table  # noqa: E402

C, Y = 343.0, 20.0


def analytic(t, v, x0):
    a = v * v - C * C
    b = -2 * v * (x0 + v * t)
    c = (x0 + v * t) ** 2 + Y * Y
    return (-b - np.sqrt(b * b - 4 * a * c)) / (2 * a)


def main() -> None:
    rows = []
    for mach in (0.1, 0.3, 0.5, 0.8, 0.95):
        v = mach * C
        x0 = -25.0 * v  # passes the camera at t = 25 s; emission times stay inside the baked range
        frames = np.arange(1, 902, dtype=float)
        t = (frames - 1) / 30
        pos = np.stack([x0 + v * t, np.full_like(t, Y), np.zeros_like(t)], axis=1)[:, None, :]
        sc = scene([{"sample": "x.wav"}], pos, frame_end=900)
        grid = ControlGrid.covering(sc.sample_of(721), sc.sample_of(811), RATE)  # 24-27 s
        geo = SceneGeometry(sc, grid)
        exact = analytic(grid.times, v, x0)
        track, _ = geo.tracks(0)
        p = geo.p
        tau = np.linalg.norm(track(grid.times) - p, axis=1) / C  # plain fixed point, 4 iterations
        for _ in range(4):
            tau = np.linalg.norm(track(grid.times - tau) - p, axis=1) / C
        engine = geo.path(0).tau
        dt = grid.step / grid.rate
        rate_exact = 1 - np.gradient(exact, dt)
        f_fp = np.abs((1 - np.gradient(tau, dt)) / rate_exact - 1).max() * 100
        f_en = np.abs((1 - np.gradient(engine, dt)) / rate_exact - 1).max() * 100
        rows.append([mach, f"{np.abs(tau - exact).max():.2e}", f"{f_fp:.3f}", f"{np.abs(engine - exact).max():.2e}",
                     f"{f_en:.5f}"])
    print("Largest error over the pass (source 20 m from the camera, reception 24-27 s, pass at 25 s):\n")
    print(table(["Mach", "fixed point x4: tau error (s)", "pitch error (%)", "engine: tau error (s)", "pitch error (%)"],
                rows))


if __name__ == "__main__":
    main()
