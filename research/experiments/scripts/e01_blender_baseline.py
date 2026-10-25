"""E01 (Phase 0): Blender's speakers against soundstage on the flyby example. Needs Blender.

Builds the flyby, tags it with measurement sounds (a 1 kHz sine on the ship, a click on the crate at
frame 180), renders with tools/blender_mixdown.py (Doppler factor 1 and 0) and with soundstage at
Phase 1-equivalent settings (amplitude panner, no air absorption, no Doppler; the crate with
sync_to_picture), and compares level against the inverse-clamped law, the pan law, Doppler, onset
and parameter steps. Writes research/figures/e01_pan_law.png.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from scipy.signal import hilbert  # noqa: E402

from common import REPO, RATE, save, table  # noqa: E402

TAGS = """
import os, sys, bpy
sys.path.insert(0, {repo!r})
from soundstage.blender import tag
for o in bpy.context.scene.objects:
    tag.clear_sounds(o)
tag.set_scene_settings(samples_root={samples!r})
if os.environ["WHICH"] == "ship":
    tag.add_sound(bpy.data.objects["Ship"], "sine_1k.wav", ref_distance=15, loop_crossfade=0.0)
else:
    tag.add_sound(bpy.data.objects["Crate"], "click.wav", mode="once", frame=180, ref_distance=5, sync_to_picture=True)
"""
PHASE1 = ["--set", "panner=amplitude", "--set", "air_absorption=0", "--set", "doppler_factor=0"]


def run(cmd, env=None):
    subprocess.run(cmd, check=True, capture_output=True, env={**os.environ, **(env or {})})


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="e01_"))
    venv = REPO / ".venv" / "bin"
    run([str(venv / "python"), str(REPO / "tools" / "make_test_samples.py")])
    run(["blender", "-b", "--factory-startup", "--python-exit-code", "1", "--python", str(REPO / "examples" / "flyby.py"),
         "--", "--save", str(tmp / "flyby.blend")])
    tags = tmp / "tags.py"
    tags.write_text(TAGS.format(repo=str(REPO), samples=str(REPO / "samples") + "/"))
    blender = ["blender", "-b", str(tmp / "flyby.blend"), "--factory-startup", "-y", "--python-exit-code", "1",
               "--python", str(REPO / "tools" / "blender_mixdown.py"), "--", "--run", str(tags)]
    for which in ("ship", "crate"):
        run(blender + ["--out", str(tmp / f"{which}_blender.wav")], {"WHICH": which})
        run([str(venv / "soundstage"), "bake", str(tmp / "flyby.blend"), "--run", str(tags), "--out",
             str(tmp / f"bake_{which}")], {"WHICH": which})
        run([str(venv / "soundstage"), "render", str(tmp / f"bake_{which}" / "scene.json"), "-o",
             str(tmp / f"{which}_soundstage.wav"), *PHASE1], {"WHICH": which})
    run(blender + ["--out", str(tmp / "ship_blender_d10.wav"), "--doppler", "10"], {"WHICH": "ship"})

    # geometry per frame from the bake: distance, lateral sine, inverse-law gain
    npz = np.load(tmp / "bake_ship" / "scene.npz")
    frames, m, p = npz["frames"], npz["listener_matrix"], npz["src_pos"][:, 0]
    sel = (frames >= 1) & (frames <= 240) & (np.mod(frames, 1) == 0)
    m, p = m[sel], p[sel]
    q = np.einsum("nji,nj->ni", m[:, :3, :3], p - m[:, :3, 3])
    d = np.linalg.norm(q, axis=1)
    lam = q[:, 0] / np.sqrt(d ** 2 + 0.25 ** 2)
    g = np.where(d > 15, 15 / d, 1.0)
    dry = 0.5 / np.sqrt(2)

    def levels(name):
        x, _ = sf.read(tmp / f"{name}.wav")
        w = x[: 240 * 1600].reshape(240, 1600, 2)
        return np.sqrt((w ** 2).mean(axis=1)) / dry  # (240, 2) linear, re. dry

    def freq(name, k):
        x, _ = sf.read(tmp / f"{name}.wav")
        row = x[k * 1600:(k + 1) * 1600].sum(axis=1)
        z = np.nonzero((row[:-1] <= 0) & (row[1:] > 0))[0]
        t = z + row[z] / (row[z] - row[z + 1])
        return (len(t) - 1) / ((t[-1] - t[0]) / RATE)

    # soundstage applies the distance law to the retarded distance (where the sound left the ship)
    from soundstage.engine.control import ControlGrid
    from soundstage.engine.geometry import SceneGeometry
    from soundstage.engine.scene import load_scene
    sc = load_scene(tmp / "bake_ship" / "scene.json")
    grid = ControlGrid.covering(0, sc.length_samples(), RATE)
    path = SceneGeometry(sc, grid).path(0)
    centres = (np.arange(240) * 1600 + 800 - grid.start) // grid.step
    d_ret = path.distance[centres]
    g_ret = np.where(d_ret > 15, 15 / d_ret, 1.0)
    rows = []
    for name, ref in (("ship_blender", g), ("ship_soundstage", g_ret)):
        lv = levels(name)
        total = np.sqrt((lv ** 2).sum(axis=1))
        err = 20 * np.log10(total / ref)
        bal = 20 * np.log10(lv[:, 1] / lv[:, 0])
        k76 = int(np.argmin(np.abs(np.degrees(np.arcsin(lam)) - 76)))
        rows.append([name.split("_")[1], f"±{np.abs(err).max():.2f}", f"{bal[k76]:.1f}",
                     f"{freq(name, 0):.0f} / {freq(name, 238):.0f}"])
    rows.append(["blender, doppler ×10", "", "", f"{freq('ship_blender_d10', 0):.0f} / {freq('ship_blender_d10', 238):.0f}"])
    print("Ship (1 kHz sine, ref 15 m, passing 25 m in front at 30 m/s):\n")
    print(table(["engine", "level vs inverse law (dB; soundstage: retarded distance)", "balance at 76° (dB)",
                 "frequency first / last frame (Hz)"], rows))

    onsets = []
    for name in ("crate_blender", "crate_soundstage"):
        x, _ = sf.read(tmp / f"{name}.wav")
        a = np.abs(x).max(axis=1)
        onsets.append([name.split("_")[1], int(np.argmax(a > 0.1 * a.max())), 179 * 1600])
    print("\nCrate click at frame 180 (soundstage with sync_to_picture):\n")
    print(table(["engine", "onset sample", "frame 180"], onsets))

    x, _ = sf.read(tmp / "ship_blender.wav")
    env = 20 * np.log10(np.abs(hilbert(x[:, 0])) + 1e-9)
    step = np.abs(env[48:] - env[:-48])
    big = np.nonzero(step > 0.1)[0] + 48
    starts = big[np.insert(np.diff(big) > 48, 0, True)]
    period = int(np.median(np.diff(starts))) if len(starts) > 2 else 0
    print(f"\nBlender level steps > 0.1 dB within 1 ms: {len(starts)}, typical spacing {period} samples")

    lv = levels("ship_blender")
    theta = np.degrees(np.arcsin(np.clip(lam, -1, 1)))
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(theta, 20 * np.log10(lv[:, 0] / g), ".", ms=3, label="Blender, left (measured)")
    ax.plot(theta, 20 * np.log10(lv[:, 1] / g), ".", ms=3, label="Blender, right (measured)")
    t = np.linspace(-80, 80, 161)
    s = np.sin(np.radians(t))
    ax.plot(t, 10 * np.log10((1 - s) / 2), "k--", lw=1, label="g² = (1 ∓ sin θ)/2 (power law)")
    ax.plot(t, 10 * np.log10((1 + s) / 2), "k--", lw=1)
    phi = (s + 1) * np.pi / 4
    ax.plot(t, 20 * np.log10(np.cos(phi)), "r:", lw=1, label="soundstage sine law")
    ax.plot(t, 20 * np.log10(np.sin(phi)), "r:", lw=1)
    ax.set_ylim(-40, 2)
    ax.set_xlabel("lateral angle θ (°)")
    ax.set_ylabel("channel gain re. distance law (dB)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    save(fig, "e01_pan_law.png")


if __name__ == "__main__":
    sys.exit(main())
