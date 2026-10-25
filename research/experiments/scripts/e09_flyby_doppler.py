"""E09: the flyby example with Phase 1-equivalent settings and with the Phase 2 defaults. Needs Blender.

Bakes the flyby with its own tags (examples/flyby_sounds.py), renders the ship's engine loop alone
both ways, plots spectrograms, and prints the report's delay and playback-rate ranges against the
expected Doppler factors for 30 m/s. Writes research/figures/e09_flyby_spectrogram.png.
"""

import json
import subprocess
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from scipy.signal import spectrogram  # noqa: E402

from common import REPO, save, table  # noqa: E402

PHASE1 = ["--set", "panner=amplitude", "--set", "air_absorption=0", "--set", "doppler_factor=0"]


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="e09_"))
    venv = REPO / ".venv" / "bin"
    subprocess.run([str(venv / "python"), str(REPO / "tools" / "make_test_samples.py")], check=True, capture_output=True)
    subprocess.run(["blender", "-b", "--factory-startup", "--python-exit-code", "1", "--python",
                    str(REPO / "examples" / "flyby.py"), "--", "--save", str(tmp / "flyby.blend")], check=True,
                   capture_output=True)
    subprocess.run([str(venv / "soundstage"), "bake", str(tmp / "flyby.blend"), "--run",
                    str(REPO / "examples" / "flyby_sounds.py"), "--out", str(tmp / "bake")], check=True,
                   capture_output=True)
    scene = str(tmp / "bake" / "scene.json")
    for name, extra in (("phase1", PHASE1), ("phase2", [])):
        subprocess.run([str(venv / "soundstage"), "render", scene, "-o", str(tmp / f"ship_{name}.wav"), "--solo",
                        "Ship:0", "--report", *extra], check=True, capture_output=True)
    subprocess.run([str(venv / "soundstage"), "render", scene, "-o", str(tmp / "mix.wav"), "--report"], check=True,
                   capture_output=True)
    report = json.loads((tmp / "mix.report.json").read_text())
    rows = [[s["id"], s.get("distance_m"), s.get("delay_ms"), s.get("rate")] for s in report["sources"] if s.get("rate")]
    c, v = 343.0, 30.0
    print(f"Flyby, Phase 2 defaults (expected for 30 m/s: rate {c / (c + v):.3f} receding, {c / (c - v):.3f} "
          "approaching head-on, plus the camera's 1.25 m/s):\n")
    print(table(["source", "distance m", "delay ms", "playback rate"], rows))
    print(f"\nmaster: {report['master']}")

    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    for ax, name, title in zip(axes, ("phase1", "phase2"), ("Phase 1-equivalent settings", "Phase 2 defaults")):
        x, r = sf.read(tmp / f"ship_{name}.wav")
        f, t, s = spectrogram(x.sum(axis=1), fs=r, nperseg=8192, noverlap=7168)
        ax.pcolormesh(t, f, 10 * np.log10(s + 1e-12), vmin=-120, vmax=-40, shading="auto")
        ax.set_ylim(0, 1200)
        ax.set_ylabel("Hz")
        ax.set_title(f"ship engine loop alone: {title}")
    axes[1].set_xlabel("s (frame = 30 t + 1); closest approach at about 4 s")
    save(fig, "e09_flyby_spectrogram.png")


if __name__ == "__main__":
    main()
