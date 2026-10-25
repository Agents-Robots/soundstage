"""Command-line entry point ``soundstage`` with the subcommands scan, bake, inspect, render, preview.

- ``scan``: runs ``blender/scan.py`` headless and prints the cameras, moving objects and static
  objects near the camera path (sound-source candidates); ``--out`` keeps the full JSON.
- ``bake``: runs ``blender/bake.py`` headless and writes scene.json + scene.npz.
- ``inspect``: summarizes a scene file (sources, distance ranges, cuts, warnings).
- ``render``: renders a scene file to a WAV, optionally with a JSON report.
- ``preview``: muxes a mix with the shot's frames or a video into an MP4 (ffmpeg), for a sync check.

Arguments, exit codes and report format: docs/spec/cli.md.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PREFIX = "[soundstage] "
BLENDER_DIR = Path(__file__).resolve().parent / "blender"


def find_blender(explicit: str | None) -> str:
    blender = explicit or os.environ.get("SOUNDSTAGE_BLENDER") or shutil.which("blender")
    if not blender:
        sys.exit("blender not found: put it on PATH, set SOUNDSTAGE_BLENDER, or pass --blender")
    return blender


def run_blender(script: str, blend: str, script_args: list[str], blender: str | None) -> int:
    """Run a soundstage script in headless Blender; print its [soundstage] lines, and the tail on failure."""
    if not Path(blend).is_file():
        print(f"error: {blend} not found", file=sys.stderr)
        return 1
    cmd = [find_blender(blender), "-b", blend, "--factory-startup", "-y", "--python-exit-code", "1",
           "--python", str(BLENDER_DIR / script), "--", *script_args]
    other: list[str] = []
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as proc:
        for line in proc.stdout:
            line = line.rstrip("\n")
            if line.startswith(PREFIX):
                print(line[len(PREFIX):], flush=True)
            else:
                other.append(line)
    if proc.returncode != 0:
        print(f"error: blender exited with code {proc.returncode}; last output:", file=sys.stderr)
        print("\n".join(other[-30:]), file=sys.stderr)
        return 1
    return 0


def _table(rows: list[list], header: list[str]) -> str:
    rows = [[str(c) for c in r] for r in rows]
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(header)]
    fmt = "  ".join(f"{{:{w}}}" for w in widths)
    return "\n".join([fmt.format(*header), fmt.format(*("-" * w for w in widths))] + [fmt.format(*r) for r in rows])


def _frames(f) -> str:
    if f is None:
        return "-"
    if isinstance(f, list):
        return f"{f[0]:g}" if len(f) == 1 else f"{f[0]:g}..{f[-1]:g} ({len(f)}x)"
    return f"{f:g}"


def _range(r: list | None) -> str:
    return f"{r[0]:g}-{r[1]:g}" if r else "-"


def cmd_scan(a: argparse.Namespace) -> int:
    out = Path(a.out) if a.out else Path(tempfile.mkdtemp()) / "scan.json"
    args = ["--out", str(out), "--samples", str(a.samples), "--max-static", str(a.max_static)]
    args += ["--frames", a.frames] if a.frames else []
    args += ["--scene", a.scene_name] if a.scene_name else []
    for r in a.run:
        args += ["--run", str(Path(r).resolve())]
    if run_blender("scan.py", a.blend, args, a.blender) != 0:
        return 1
    s = json.loads(out.read_text())
    print(f"\n{s['blend_file']}  scene {s['scene']}: frames {s['frame_start']}-{s['frame_end']} "
          f"@ {s['fps']:g} fps ({s['duration_s']} s), {s['counts']['objects']} objects")
    print("cameras: " + ", ".join(f"{c['name']} (frames {c['first_sampled_frame']}-{c['last_sampled_frame']})"
                                  for c in s["cameras"]))
    cp = s["camera_path"]
    print(f"camera path: {cp['length_m']} m, max {cp['max_speed_m_s']} m/s")
    moving = [m for m in s["moving"] if not m["moves_with_camera"]]
    attached = len(s["moving"]) - len(moving)
    print(f"\nmoving objects ({len(moving)}" + (f", plus {attached} attached to the camera" if attached else "") + "):")
    print(_table([[m["name"], m["type"], _range(m["distance_m"]), m["closest_frame"], m["side_at_closest"],
                   m["max_speed_m_s"], _range(m["moving_frames"])] for m in moving[: a.limit]],
                 ["object", "type", "dist m", "closest", "side", "max m/s", "moving"]))
    print(f"\nstatic objects nearest to the camera ({min(len(s['static_near']), a.limit)} of {s['counts']['static']}):")
    print(_table([[m["name"], m["type"], _range(m["distance_m"]), m["closest_frame"], m["side_at_closest"]]
                  for m in s["static_near"][: a.limit]], ["object", "type", "dist m", "closest", "side"]))
    if s["tagged"]:
        print(f"\nalready tagged: {len(s['tagged'])} sounds")
    print(f"\nfull JSON: {out}" if a.out else "\n(use --out scan.json to keep the full JSON)")
    return 0


def cmd_bake(a: argparse.Namespace) -> int:
    args = ["--out", str(Path(a.out).resolve())]
    args += ["--frames", a.frames] if a.frames else []
    args += ["--substeps", str(a.substeps)] if a.substeps else []
    args += ["--pad", str(a.pad)] if a.pad is not None else []
    args += ["--skip-invalid"] if a.skip_invalid else []
    args += ["--scene", a.scene_name] if a.scene_name else []
    for r in a.run:
        args += ["--run", str(Path(r).resolve())]
    return run_blender("bake.py", a.blend, args, a.blender)


def cmd_inspect(a: argparse.Namespace) -> int:
    import numpy as np

    from soundstage.engine import geometry
    from soundstage.engine.scene import SceneError, load_scene

    try:
        scene = load_scene(a.scene)
    except SceneError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    inside = (scene.frames >= scene.frame_start) & (scene.frames <= scene.frame_end + 1)
    q = geometry.camera_space(scene.listener_matrix[inside], scene.src_pos[inside])
    dist = np.linalg.norm(q, axis=2)
    dt = np.diff(scene.seconds(scene.frames[inside]))
    rows, data = [], []
    for s in scene.sources:
        p = s.params
        row = {"id": s.id, "group": s.group, "sample": os.path.basename(p["sample"]), "mode": p["mode"],
               "frame": p["frame"], "spatial": s.spatial}
        if s.spatial and dist.size:
            d = dist[:, s.track]
            row["distance_m"] = [round(float(d.min()), 2), round(float(d.max()), 2)]
            vr = np.diff(d) / dt if len(dt) else np.zeros(1)  # > 0 receding
            c = scene.settings["speed_of_sound"]
            row["max_radial_speed_m_s"] = round(float(np.abs(vr).max()), 2)
            # Doppler factor of a moving source: c / (c + v_r), approximate for a moving camera
            row["rate"] = [round(float(c / (c + vr.max())), 3), round(float(c / max(c + vr.min(), 1e-6)), 3)]
        data.append(row)
        rows.append([row["id"], row["group"], row["sample"], row["mode"],
                     _frames(p["frame"]),
                     _range(row.get("distance_m")) if s.spatial else "bed", row.get("max_radial_speed_m_s", "-"),
                     _range(row.get("rate"))])
    if a.json:
        print(json.dumps({"sources": data, "cuts": scene.cuts.tolist(), "warnings": scene.warnings}, indent=2))
        return 0
    print(f"{scene.path}: frames {scene.frame_start}-{scene.frame_end} @ {scene.fps:g} fps, "
          f"{len(scene.sources)} sources, listener {', '.join(scene.manifest['listener']['objects'])}")
    print(_table(rows, ["id", "group", "sample", "mode", "frame", "dist m", "radial m/s", "rate"]))
    if len(scene.cuts):
        print("cuts at frames: " + ", ".join(f"{c:g}" for c in scene.cuts))
    for w in scene.warnings:
        print(f"warning: {w}", file=sys.stderr)
    return 0


def cmd_render(a: argparse.Namespace) -> int:
    from soundstage.engine import mix, report, render
    from soundstage.engine.scene import SceneError, load_scene, parse_overrides

    try:
        overrides = parse_overrides(a.set)
        if a.quality:
            overrides["quality"] = a.quality
        scene = load_scene(a.scene, overrides)
    except SceneError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    frames = None
    if a.frames:
        x, _, y = a.frames.partition("-")
        frames = (int(x), int(y or x))
    out = Path(a.output) if a.output else scene.path.parent / "mix.wav"
    try:
        result = render.render(scene, frames=frames, solo=a.solo, mute=a.mute)
    except (OSError, RuntimeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    mix.write_wav(out, result.audio, result.rate, pcm24=a.pcm24)
    rep = report.build_report(scene, result, out, overrides)
    if a.report:
        report.write_report(out.with_suffix(".report.json"), rep)
    m = rep["master"]
    print(f"wrote {out}: {len(result.audio) / result.rate:.2f} s, frames {result.frames[0]}-{result.frames[1]}, "
          f"peak {m['peak_dbfs']} dBFS, {m['lufs_integrated']} LUFS")
    print(_table([[s["id"], s["group"], s["peak_dbfs"], s["audible_frames"], _range(s.get("distance_m"))]
                  for s in result.sources], ["source", "group", "peak dBFS", "audible frames", "dist m"]))
    for w in result.warnings:
        print(f"warning: {w}", file=sys.stderr)
    if a.report:
        print(f"report: {out.with_suffix('.report.json')}")
    return 1 if (a.strict and result.warnings) else 0


def cmd_preview(a: argparse.Namespace) -> int:
    from soundstage.preview import PreviewError, preview

    wav = Path(a.mix)
    out = Path(a.output) if a.output else wav.with_name(wav.stem + "_preview.mp4")
    try:
        res = preview(wav, out, frames=a.frames, video=a.video, fps=a.fps, start_frame=a.start_frame,
                      video_start_frame=a.video_start_frame, width=a.width, ffmpeg=a.ffmpeg)
    except PreviewError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    first, last = res.picture_frames
    print(f"wrote {out}: frames {first}-{last} @ {float(res.fps):g} fps ({(last - first + 1) / res.fps:.2f} s)")
    if res.held_frames:
        print(f"{res.held_frames} missing frames hold the previous image")
    if res.audio_offset_samples:
        what = "skipped" if res.audio_offset_samples > 0 else "of silence inserted"
        print(f"audio: {abs(res.audio_offset_samples)} samples {what} to line up with frame {first}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="soundstage", description="Spatial sound for Blender animations.")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scan", help="list cameras and sound-source candidates of a .blend")
    s.add_argument("blend")
    s.add_argument("--out", help="write the full JSON here")
    s.add_argument("--frames", help="frame range A-B (default: scene range)")
    s.add_argument("--samples", type=int, default=60, help="frames sampled over the shot")
    s.add_argument("--max-static", type=int, default=30, help="static objects to include in the JSON")
    s.add_argument("--limit", type=int, default=25, help="rows per table")
    s.add_argument("--run", action="append", default=[], help="script to run in Blender first")
    s.add_argument("--scene", dest="scene_name", help="scene name (default: the file's active scene)")
    s.add_argument("--blender")
    s.set_defaults(func=cmd_scan)

    b = sub.add_parser("bake", help="export a .blend shot to scene.json + scene.npz")
    b.add_argument("blend")
    b.add_argument("--out", required=True, help="output directory")
    b.add_argument("--frames", help="frame range A-B (default: scene range)")
    b.add_argument("--substeps", type=int, help="sub-frames per frame (default: scene setting, 4)")
    b.add_argument("--pad", type=float, help="padding seconds before/after (default: scene setting, 3)")
    b.add_argument("--run", action="append", default=[], help="tagging script to run in Blender first")
    b.add_argument("--skip-invalid", action="store_true", help="drop invalid tags instead of failing")
    b.add_argument("--scene", dest="scene_name", help="scene name (default: the file's active scene)")
    b.add_argument("--blender")
    b.set_defaults(func=cmd_bake)

    i = sub.add_parser("inspect", help="summarize a scene file")
    i.add_argument("scene")
    i.add_argument("--json", action="store_true")
    i.set_defaults(func=cmd_inspect)

    r = sub.add_parser("render", help="render a scene file to a WAV")
    r.add_argument("scene")
    r.add_argument("-o", "--output", help="output WAV (default: mix.wav next to scene.json)")
    r.add_argument("--frames", help="sub-range A-B (sample 0 = frame A)")
    r.add_argument("--solo", action="append", default=[], help="source id glob or group:NAME")
    r.add_argument("--mute", action="append", default=[], help="source id glob or group:NAME")
    r.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="override a scene setting")
    r.add_argument("--quality", choices=("standard", "high"), help="interpolation quality (same as --set quality=)")
    r.add_argument("--pcm24", action="store_true", help="24-bit PCM instead of 32-bit float")
    r.add_argument("--report", action="store_true", help="write <output>.report.json")
    r.add_argument("--strict", action="store_true", help="exit 1 if there are warnings")
    r.set_defaults(func=cmd_render)

    v = sub.add_parser("preview", help="mux a mix with the shot's frames or a video into an MP4")
    v.add_argument("mix", help="WAV from render (its .report.json supplies first frame and fps)")
    v.add_argument("-o", "--output", help="output MP4 (default: <mix>_preview.mp4)")
    pic = v.add_mutually_exclusive_group(required=True)
    pic.add_argument("--frames", help="directory of numbered images, or a prefix such as renders/frame_")
    pic.add_argument("--video", help="video file whose first frame is --video-start-frame")
    v.add_argument("--fps", type=float, help="frame rate (default: from the report)")
    v.add_argument("--start-frame", type=int, help="frame of the mix's first sample (default: from the report)")
    v.add_argument("--video-start-frame", type=int, help="frame of the video's first frame (default: --start-frame)")
    v.add_argument("--width", type=int, default=1280, help="output width in pixels; 0 keeps the size (default 1280)")
    v.add_argument("--ffmpeg")
    v.set_defaults(func=cmd_preview)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
