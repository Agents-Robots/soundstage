"""Build, bake, render, check and preview showcase sections (repo venv; sections/README.md).

    .venv/bin/python examples/showcase/showcase.py sounds
    .venv/bin/python examples/showcase/showcase.py all intro sources       # build, bake, audio, check
    .venv/bin/python examples/showcase/showcase.py build|bake|audio|check KEY ...
    .venv/bin/python examples/showcase/showcase.py frames KEY ... [--percent 50] [--samples 16] [--step 1]
    .venv/bin/python examples/showcase/showcase.py preview KEY ...         # <key>_preview.mp4 from the frames

Outputs go to ``out/showcase/<key>/`` (gitignored): the .blend, ``section.json``, ``bake/``,
``passes/``, ``<key>.wav`` and its report, ``check.json``, ``frames/`` and the preview.

A section whose folder has a ``steps.py`` replaces the steps that module defines (functions named
after the step, taking the section's output folder and the parsed arguments): ``production`` takes its
sound and picture from finished animations instead of baking and rendering a scene.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = REPO / "out" / "showcase"
PY = sys.executable
sys.path[:0] = [str(REPO), str(HERE)]


def run(cmd: list[str]) -> None:
    print("$ " + " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True)


def build(key: str, a) -> None:
    run(["blender", "-b", "--factory-startup", "-y", "--python", HERE / "sections" / key / "build.py", "--",
         "--out", OUT / key])


def bake(key: str, a) -> None:
    """The section's bake, and one per bake variant of the manifest (its settings set by a run
    script written next to it; ``frames``, "A-B", limits it to those frames)."""
    run([REPO / ".venv" / "bin" / "soundstage", "bake", OUT / key / f"{key}.blend", "--out", OUT / key / "bake"])
    man = json.loads((OUT / key / "section.json").read_text())
    for name, settings in man.get("bakes", {}).items():
        settings = dict(settings)
        frames = settings.pop("frames", None)
        script = OUT / key / f"bake_{name}.py"
        script.write_text(f"import sys\nsys.path.insert(0, {str(REPO)!r})\nfrom soundstage.blender import tag\n"
                          f"tag.set_scene_settings(**{settings!r})\n")
        run([REPO / ".venv" / "bin" / "soundstage", "bake", OUT / key / f"{key}.blend", "--run", script,
             *(["--frames", frames] if frames else []), "--out", OUT / key / f"bake_{name}"])


def audio(key: str, a) -> None:
    from kit import audio as kit_audio
    summary = kit_audio.render_section(OUT / key)
    print(f"{key}:\n{kit_audio.describe(summary)}")


def check(key: str, a) -> None:
    subprocess.run([PY, HERE / "sections" / key / "check.py", "--dir", OUT / key], check=False)


def frames(key: str, a) -> None:
    run(["blender", "-b", OUT / key / f"{key}.blend", "-y", "--python", HERE / "kit" / "blender" / "frames.py", "--",
         "--out", OUT / key / "frames", "--percent", a.percent, "--samples", a.samples, "--step", a.step,
         "--first", a.first, "--last", a.last])


def preview(key: str, a) -> None:
    run([REPO / ".venv" / "bin" / "soundstage", "preview", OUT / key / f"{key}.wav", "--frames", OUT / key / "frames",
         "--width", "0", "-o", OUT / key / f"{key}_preview.mp4"])


def sounds(a) -> None:
    run([PY, HERE / "sounds" / "make.py", "--out", OUT / "sounds"])
    run([PY, HERE / "sounds" / "fetch.py", "--out", OUT / "sounds"])


STEPS = {"build": build, "bake": bake, "audio": audio, "check": check, "frames": frames, "preview": preview}


def section_step(key: str, step: str):
    """The section's own step from its ``steps.py``, or None."""
    path = HERE / "sections" / key / "steps.py"
    if not path.exists():
        return None
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(f"steps_{key}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.path.remove(str(path.parent))
    return getattr(mod, step, None)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("step", choices=[*STEPS, "all", "sounds"])
    p.add_argument("keys", nargs="*")
    p.add_argument("--percent", type=int, default=50)
    p.add_argument("--samples", type=int, default=16)
    p.add_argument("--step", type=int, default=1, dest="frame_step")
    p.add_argument("--first", type=int, default=0, help="frames: from this frame (0: the first)")
    p.add_argument("--last", type=int, default=0, help="frames: to this frame (0: the last)")
    a = p.parse_args()
    a.step_ = a.step
    a.step = a.frame_step
    if a.step_ == "sounds":
        sounds(a)
        return
    for key in a.keys:
        if not (HERE / "sections" / key / "section.py").exists():
            sys.exit(f"no section {key!r} in {HERE / 'sections'}")
        for step in (["build", "bake", "audio", "check"] if a.step_ == "all" else [a.step_]):
            own = section_step(key, step)
            if own:
                own(OUT / key, a)
            else:
                STEPS[step](key, a)


if __name__ == "__main__":
    main()
