"""The steps of ``production`` that differ from a scene section (``showcase.py`` calls them; repo venv).

- ``bake``: nothing; the animations are baked in their own projects.
- ``audio``: takes the race's sound from the animation's own mix (the stems soundstage rendered,
  ``RACE_STEMS``), renders the metropolis scene from the animation's own bake with ``soundstage
  render`` (``RENDERS``, into ``src/``; skipped when the render is newer than its bake), resamples the
  race to 30 fps, applies the fixed gains, the race's limiter and the fades at the cuts, and writes ``passes/``,
  ``production.wav`` and ``production.report.json`` as the kit's audio step does.
- ``frames``: renders the overlays with a transparent film and lays them over the animations' frames,
  scaled to the width and centred on black (both are 2.39:1).
"""

from __future__ import annotations

import functools
import json
import subprocess
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1]), str(HERE)]

import numpy as np  # noqa: E402
import section as S  # noqa: E402
import soundfile as sf  # noqa: E402
import soxr  # noqa: E402
from kit import audio as kit_audio  # noqa: E402
from kit import story  # noqa: E402
from PIL import Image  # noqa: E402

from soundstage.engine import mix, report  # noqa: E402

REPO = HERE.parents[3]
SOUNDSTAGE = REPO / ".venv" / "bin" / "soundstage"


def projects() -> dict[str, Path]:
    local = HERE / "sources.local.toml"
    if not local.exists():
        sys.exit(f"{local} is missing: name the animations' project folders there ([projects] race = ..., metropolis = ...)")
    return {k: Path(v) for k, v in tomllib.loads(local.read_text())["projects"].items()}


def bake(out_dir: Path, a) -> None:
    print("production: nothing to bake (the animations are baked in their own projects)")


# --- sound ---------------------------------------------------------------------------------------------

def render_sources(out_dir: Path) -> dict[str, list[Path]]:
    src = out_dir / "src"
    src.mkdir(parents=True, exist_ok=True)
    roots = projects()
    out = {}
    for k, renders in S.RENDERS.items():
        out[k] = []
        for i, (scene, args) in enumerate(renders):
            wav = src / f"{k}{i}.wav"
            bake_file = roots[k] / scene
            if not wav.exists() or wav.stat().st_mtime < bake_file.stat().st_mtime:
                cmd = [str(SOUNDSTAGE), "render", scene, "-o", str(wav), "--report", *args]
                print("$ " + " ".join(cmd), flush=True)
                subprocess.run(cmd, check=True, cwd=roots[k])
            out[k].append(wav)
    return out


def race_sound(rate: int) -> tuple[np.ndarray, dict]:
    """The race scene's stems from the animation's mix, at the animation's frame rate. The mix steps the
    engines and the air back while the radio speaks (``SPEECH_DUCK_DB``); with the voices left out, its
    gain curves undo that: where a stem's curve dips under the scene's median, the stem is lifted back
    by the dip, at most by the step."""
    root = projects()["race"]
    name, start = S.RACE_MIX
    recipe = json.loads((root / f"{name}.recipe.json").read_text())
    n = round(S.SECTION.passes[0].frames / S.ANIM_FPS["race"] * rate)
    first = round((start - recipe["film_t0"]) * rate)
    curves = np.load(root / f"{name}_curves.npz")
    t = start + np.arange(n) / rate
    t_curve = float(curves["film_t0"]) + np.arange(len(curves["engines"])) / int(curves["rate"])
    x, lifted = np.zeros((n, 2)), {}
    for stem in S.RACE_STEMS:
        y, sr = sf.read(root / f"{name}_stem_{stem}.wav", start=first, stop=first + n, always_2d=True, dtype="float64")
        if sr != rate or len(y) != n:
            raise SystemExit(f"production.race: {name}_stem_{stem}.wav: {len(y)} samples at {sr} Hz, want {n} at {rate}")
        curve = np.interp(t, t_curve, curves[stem])
        lift = np.clip(np.median(curve) / np.maximum(curve, 1e-9), 1.0, 10 ** (S.SPEECH_DUCK_DB / 20))
        x += y * lift[:, None]
        lifted[stem] = round(float(20 * np.log10(lift.max())), 2)
    info = {"mix": name, "start_s": start, "stems": list(S.RACE_STEMS), "lifted_db_max": lifted,
            **{k: recipe.get(k) for k in ("date", "commit", "soundstage_commit")}}
    return x, info


def fade(x: np.ndarray, rate: int, fade_in_s: float, fade_out_s: float, silent_s: float = 0.0) -> np.ndarray:
    """Fades in and out (sine squared); the last ``silent_s`` silent (C5 at the section's end)."""
    n = len(x)
    g = np.ones(n)
    a, b, z = int(fade_in_s * rate), int(fade_out_s * rate), int(silent_s * rate)
    if a:
        g[:a] = np.sin(np.linspace(0, np.pi / 2, a)) ** 2
    if b:
        g[n - b - z:n - z] = np.cos(np.linspace(0, np.pi / 2, b)) ** 2
    g[n - z:] = 0.0
    return x * g[:, None]


def audio(out_dir: Path, a) -> None:
    man = kit_audio.manifest(out_dir)
    rate, spf = man["sample_rate"], story.SAMPLES_PER_FRAME
    files = render_sources(out_dir)
    total = np.zeros((man["frames"][1] * spf, 2))
    passes = out_dir / "passes"
    passes.mkdir(exist_ok=True)
    rows = []
    last_pass = man["passes"][-1]["key"]
    for p in man["passes"]:
        k, (first, last) = p["key"], p["window"]
        n = (last - first + 1) * spf
        if k == "race":
            x, origin = race_sound(rate)
            reports = []
        else:
            x = sum(sf.read(f, always_2d=True, dtype="float64")[0] for f in files[k])
            reports = [json.loads(f.with_suffix(".report.json").read_text()) for f in files[k]]
            origin = [{"scene": r["scene"], "overrides": r.get("overrides"), "timing_s": r.get("timing_s"),
                       "far_field": r.get("far_field"), "groups": sorted(r.get("groups") or {})} for r in reports]
        if S.ANIM_FPS[k] != story.FPS:  # shown at 30 fps: its sound runs 1001/1000 as fast
            x = soxr.resample(x, rate * story.FPS / S.ANIM_FPS[k], rate, quality="VHQ")
        if abs(len(x) - n) > 2:
            raise SystemExit(f"production.{k}: {len(x)} samples for {last - first + 1} frames")
        x = np.pad(x, ((0, max(0, n - len(x))), (0, 0)))[:n] * 10 ** (S.GAIN_DB[k] / 20)
        if k == "race":
            origin["limiter"] = mix.finish(x, {}, rate, limit=S.RACE_LIMIT_DBTP)
        if k == last_pass:
            x = fade(x, rate, S.FADE_S, S.END_FADE_S, kit_audio.EDGE_S + 0.05)
        else:
            x = fade(x, rate, S.FADE_S, S.FADE_S)
        wav = passes / f"production.{k}.wav"
        mix.write_wav(wav, x, rate)
        total[(first - 1) * spf:last * spf] = x
        timing = sum(sum(v for v in (r.get("timing_s") or {}).values() if isinstance(v, float)) for r in reports)
        rows.append({"pass": k, "frames": [first, last], "settings": p["settings"], "master": report.metrics(x, rate),
                     "sources": sum(len(r["sources"]) for r in reports) if reports else None,
                     "render_seconds": round(timing, 2) if reports else None, "peak_rss_mb": None,
                     "anim_mix" if k == "race" else "anim_render": origin, "warnings": []})
    wav = out_dir / "production.wav"
    mix.write_wav(wav, total, rate)
    edge = int(kit_audio.EDGE_S * rate)
    ends = [float(np.abs(total[:edge]).max()), float(np.abs(total[-edge:]).max())]
    ref = next(r for r in rows if r["pass"] == man["reference"])
    summary = {"output": str(wav.resolve()), "sample_rate": rate, "fps": float(story.FPS), "frames": man["frames"],
               "gain_db": man["gain_db"], "master": report.metrics(total, rate),
               "reference": {"pass": man["reference"], **ref["master"]},
               "ends_dbfs": [None if e == 0 else round(20 * np.log10(e), 1) for e in ends], "passes": rows,
               "machine": kit_audio.machine(), "bake_warnings": []}
    report.write_report(wav.with_suffix(".report.json"), summary)
    print("production:\n" + kit_audio.describe(summary))


# --- picture -------------------------------------------------------------------------------------------

@functools.cache
def race_renders(render_pass: int) -> tuple[Path, ...]:
    """The race's render folders of one pass of its cut, newest first (named by date)."""
    root = projects()["race"]
    dirs = [d for pattern in S.RACE_RENDERS for d in root.glob(pattern.format(render_pass)) if d.is_dir()]
    return tuple(sorted(dirs, key=lambda d: d.name, reverse=True))


def race_shot(n: int) -> tuple[tuple, int]:
    """The race's shot that holds the scene's frame ``n`` (from 0), and the frame within the shot."""
    for shot in S.RACE_SHOTS:
        if n < shot[3]:
            return shot, n
        n -= shot[3]
    raise SystemExit(f"production.race: frame {n} beyond the scene")


@functools.cache
def shot_render(shot: tuple) -> Path:
    """The newest render of the shot's pass that has all of the shot's frames: a render still in
    progress replaces a shot only once the shot is complete, never in the middle of it."""
    camera, render_pass, race0, count = shot
    for d in race_renders(render_pass):
        if all((d / S.RACE_FRAME.format(f)).exists() for f in range(race0, race0 + count)):
            return d
    raise SystemExit(f"production.race: no render of pass {render_pass} has all of {camera} ({race0}-{race0 + count - 1})")


def race_frame(n: int) -> Path:
    """The race scene's frame ``n`` (from 0), from the newest complete render of its shot."""
    shot, k = race_shot(n)
    return shot_render(shot) / S.RACE_FRAME.format(shot[2] + k)


def anim_frame(k: str, n: int) -> Path:
    if k == "race":
        return race_frame(n)
    pattern, first = S.METRO_FRAMES
    return projects()[k] / pattern.format(first + n)


def frames(out_dir: Path, a) -> None:
    """The overlays rendered from the .blend (skipped while every one in the range is newer than it),
    laid over the animations' frames."""
    over = out_dir / "overlay"
    blend = out_dir / "production.blend"
    last = a.last or S.SECTION.window(S.SECTION.passes[-1].key).last
    wanted = [over / f"{n:05d}.png" for n in range(max(a.first, 1), last + 1, a.step)]
    if all(f.exists() and f.stat().st_mtime > blend.stat().st_mtime for f in wanted):
        print(f"production: {len(wanted)} overlay frames newer than {blend.name}, not rendered again")
    else:
        subprocess.run(["blender", "-b", str(blend), "-y", "--python",
                        str(HERE.parents[1] / "kit" / "blender" / "frames.py"), "--", "--out", str(over),
                        "--percent", str(a.percent), "--samples", str(a.samples), "--step", str(a.step),
                        "--first", str(a.first), "--last", str(a.last)], check=True)
    dest = out_dir / "frames"
    dest.mkdir(exist_ok=True)
    windows = {p.key: S.SECTION.window(p.key) for p in S.SECTION.passes}
    first_pass = S.SECTION.passes[0].key
    used = set()
    done = 0
    for f in sorted(over.glob("*.png")):
        n = int(f.stem)
        if n < a.first or (a.last and n > a.last):
            continue
        done += 1
        top = Image.open(f).convert("RGBA")
        k = next((key for key, w in windows.items() if w.first <= n <= w.last), first_pass)
        offset = max(0, n - windows[k].first)  # the title page shows the first pass's first frame
        src = anim_frame(k, offset)
        used.add(src.parent)
        anim = Image.open(src).convert("RGB")
        w = top.width
        h = round(anim.height * w / anim.width)
        canvas = Image.new("RGBA", top.size, (0, 0, 0, 255))
        canvas.paste(anim.resize((w, h), Image.LANCZOS).convert("RGBA"), (0, (top.height - h) // 2))
        Image.alpha_composite(canvas, top).convert("RGB").save(dest / f.name)
    print(f"production: {done} frames composed into {dest}, from")
    print("\n".join(f"  {d}" for d in sorted(used)))
