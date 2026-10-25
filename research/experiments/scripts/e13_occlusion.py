"""E13: occlusion: the engine's response to visibility (attenuation per frequency, partial
visibility, attack and release), and a source baked passing behind a wall edge. Needs Blender for
the second part.

Writes research/figures/e13_occlusion.png.
"""

import json
import math
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, csd, sosfiltfilt, welch

from common import REPO, RATE, render, rms_db, sample, save, scene, table
from soundstage.engine import filters

PLAIN = {"panner": "amplitude", "air_absorption": 0.0, "doppler_factor": 0.0}
FREQS = (125, 250, 500, 1000, 2000, 4000, 8000)
BANDS = (250.0, 1000.0, 4000.0)


def transfer_db(x: np.ndarray, y: np.ndarray, f) -> np.ndarray:
    fr, pxy = csd(x, y, fs=RATE, nperseg=8192)
    _, pxx = welch(x, fs=RATE, nperseg=8192)
    return np.interp(f, fr, 20 * np.log10(np.abs(pxy / pxx)))


def model_db(v: np.ndarray, f) -> tuple[np.ndarray, np.ndarray]:
    """Per-band target g(f) = v + (1 - v) T(f) at ``f``, and what gain + one-pole realize."""
    t = filters.db_to_gain(-12.0) / np.sqrt(1 + (np.asarray(f, float) / 1500.0) ** 2)
    target = np.interp(np.log(f), np.log(BANDS), v) + (1 - np.interp(np.log(f), np.log(BANDS), v)) * t
    g, fc = filters.occlusion_filter(np.repeat(v[None], 4000, axis=0), list(BANDS), -12.0, 1500.0, 1e-3)
    realized = g[-1] / np.sqrt(1 + (np.asarray(f, float) / fc[-1]) ** 2)
    return 20 * np.log10(target), 20 * np.log10(realized)


def engine_part(noise: str) -> None:
    def render_with(v_after, frames=(1.0, 30.0, 31.0, 150.0)):
        v = np.ones((4, 1, 3))
        v[2:] = v_after
        return render.render(scene([{"sample": noise, "loop_phase": 0.0}], [[0, 10, 0]], frame_end=150,
                                   settings=PLAIN, visibility=(np.array(frames), v))).audio[:, 0]

    ref = render_with(1.0)
    rows = []
    for v in ([0.0, 0.0, 0.0], [1.0, 0.6, 0.2], [0.6, 0.2, 0.0]):
        out = render_with(np.array(v))
        seg = slice(int(2.0 * RATE), int(5.0 * RATE))
        measured = transfer_db(ref[seg], out[seg], FREQS)
        target, realized = model_db(np.array(v), FREQS)
        for f, a, b, c in zip(FREQS, target, realized, measured):
            rows.append([str(v), f, f"{a:.2f}", f"{b:.2f}", f"{c:.2f}"])
    print("Attenuation (dB) of a noise source after visibility drops to v (bands 250/1000/4000 Hz):\n"
          "target = per-band v + (1 - v) T(f), interpolated over log frequency; realized = broadband gain and\n"
          "one-pole the engine derives; measured = transfer function of the render\n")
    print(table(["v", "Hz", "target", "realized", "measured"], rows))

    tone = sample("tone.wav", 0.5 * np.sin(2 * np.pi * 250 * np.arange(6 * RATE) / RATE))
    steps = []
    for label, before, after in (("hidden (attack)", 1.0, 0.0), ("reappears (release)", 0.0, 1.0)):
        v = np.full((4, 1, 3), before)
        v[2:] = after
        out = render.render(scene([{"sample": tone}], [[0, 10, 0]], frame_end=150, settings=PLAIN,
                                  visibility=(np.array([1.0, 60.0, 61.0, 150.0]), v))).audio[:, 0]
        env = np.sqrt(np.convolve(out ** 2, np.ones(480) / 480, mode="same"))  # 10 ms RMS
        lo, hi = np.median(env[int(1.0 * RATE): int(1.8 * RATE)]), np.median(env[int(3.5 * RATE): int(4.5 * RATE)])
        seg = env[int(1.9 * RATE): int(3.0 * RATE)]
        frac = (seg - lo) / (hi - lo)
        t10, t90 = (np.argmax(frac >= 0.1), np.argmax(frac >= 0.9)) if hi > lo else \
            (np.argmax(frac >= 0.1), np.argmax(frac >= 0.9))
        steps.append([label, f"{20 * np.log10(hi / lo):+.2f}", f"{abs(t90 - t10) / RATE * 1000:.0f}"])
    print("\nStep in visibility at frame 60.5 (250 Hz tone; the visibility samples are 1/30 s apart):\n")
    print(table(["step", "level change dB", "10-90 % time ms"], steps))


SCENE = """
import bpy, math, sys
sys.path.insert(0, {repo!r})
from soundstage.blender import tag
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
s = bpy.context.scene
s.frame_start, s.frame_end, s.render.fps = 1, 120, 30
bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
s.collection.objects.link(cam)
s.camera = cam
cam.rotation_euler = (math.radians(90), 0, 0)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 10, 0))
bpy.context.object.scale = (10, 1, 6)
e = bpy.data.objects.new("Src", None)
s.collection.objects.link(e)
for f, x in ((1, -20.0), (121, 0.0)):
    e.location = (x, 20, 0)
    e.keyframe_insert("location", frame=f)
tag.add_sound(e, {sample!r}, loop_phase=0.0)
bpy.ops.wm.save_as_mainfile(filepath={path!r})
"""


def blender_part(noise: str) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="e13_"))
    venv = REPO / ".venv" / "bin"
    (tmp / "scene.py").write_text(SCENE.format(repo=str(REPO), sample=noise, path=str(tmp / "wall.blend")))
    subprocess.run(["blender", "-b", "--factory-startup", "--python-exit-code", "1", "--python", str(tmp / "scene.py")],
                   check=True, capture_output=True)
    subprocess.run([str(venv / "soundstage"), "bake", str(tmp / "wall.blend"), "--out", str(tmp / "bake"),
                    "--substeps", "1", "--pad", "0.2"], check=True, capture_output=True)
    arrays = np.load(tmp / "bake" / "scene.npz")
    manifest = json.loads((tmp / "bake" / "scene.json").read_text())
    for name, extra in (("occluded", []), ("open", ["--set", "occlusion_gain_db=0", "--set", "occlusion_cutoff_hz=20000"])):
        subprocess.run([str(venv / "soundstage"), "render", str(tmp / "bake" / "scene.json"), "-o",
                        str(tmp / f"{name}.wav"), "--set", "air_absorption=0", "--set", "panner=amplitude", *extra],
                       check=True, capture_output=True)
    occ, _ = sf.read(tmp / "occluded.wav")
    opn, _ = sf.read(tmp / "open.wav")
    t_vis = (arrays["vis_frames"] - 1) / 30
    vis = arrays["src_visibility"][:, 0]
    hop = int(0.05 * RATE)
    att = {}
    for f in BANDS:
        sos = butter(4, (f / math.sqrt(2), f * math.sqrt(2)), "bandpass", fs=RATE, output="sos")
        a, b = sosfiltfilt(sos, occ.sum(axis=1)), sosfiltfilt(sos, opn.sum(axis=1))
        n = len(a) // hop
        ra = np.sqrt((a[: n * hop].reshape(n, hop) ** 2).mean(axis=1))
        rb = np.sqrt((b[: n * hop].reshape(n, hop) ** 2).mean(axis=1))
        att[f] = 20 * np.log10(ra / rb)
    t_att = (np.arange(n) + 0.5) * hop / RATE
    rows = []
    for b, f in enumerate(BANDS):
        partly = (vis[:, b] > 0) & (vis[:, b] < 1)
        rows.append([f"{f:.0f}", f"{t_vis[partly][0]:.1f}-{t_vis[partly][-1]:.1f}" if partly.any() else "-",
                     f"{att[f][t_att > 3.5].mean():.2f}"])
    print(f"\nBaked: source 20 m away passing behind a wall edge at 5 m/s (occluders: "
          f"{manifest['occlusion']['occluders']}); line of sight blocked from about t = 1.9 s\n")
    print(table(["band Hz", "partly visible s", "attenuation behind the wall dB"], rows))
    return {"t_vis": t_vis, "vis": vis, "t_att": t_att, "att": att}


def main() -> None:
    noise = sample("noise.wav", np.random.default_rng(4).standard_normal(RATE * 4) * 0.1)
    engine_part(noise)
    baked = blender_part(noise)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (a, b) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    for i, f in enumerate(BANDS):
        a.step(baked["t_vis"], baked["vis"][:, i], where="post", label=f"{f:.0f} Hz")
        b.plot(baked["t_att"], baked["att"][f], label=f"{f:.0f} Hz octave")
    a.set(ylabel="visibility", title="source passing behind a wall edge: baked visibility per band")
    a.legend()
    b.set(xlabel="s", ylabel="occluded / open (dB)", ylim=(-25, 2), title="rendered attenuation per octave band")
    b.legend()
    save(fig, "e13_occlusion.png")


if __name__ == "__main__":
    main()
