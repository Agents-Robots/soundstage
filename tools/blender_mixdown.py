"""Baseline: render soundstage tags with Blender's own Speaker objects (Phase 0).

Runs in Blender, like ``bake.py``::

    blender -b shot.blend --factory-startup -y --python-exit-code 1 --python tools/blender_mixdown.py -- \
        --out baseline.wav [--run tags.py ...] [--frames A-B] [--scene NAME] [--doppler F] \
        [--speed-of-sound C] [--method render|mixdown]

Applies the tags (``--run`` scripts as in the bake), then gives every source the same dry signal
soundstage would play: the sample decoded with Blender's ``aud`` module (downmixed, pitched, with
``gain_db``), placed at its trigger frames or looped from the first frame with its fades, composed
in numpy and written to a temporary WAV. The spatialization is then all Blender's: each spatial
source becomes a Speaker parented to its object at ``offset``, with one NLA sound strip from the
first frame, ``distance_reference``, ``distance_max`` and ``attenuation`` from the tag, and the
scene's distance model, speed of sound and Doppler factor from the scene settings (Blender has one
distance model and one Doppler factor per scene: the first spatial source's model is used). Beds
become sequencer sound strips. The listener is the scene camera. Loops start at phase 0 without
seam crossfade, so compare levels, pan and pitch, not loop phase.

The audio comes from a video render whose picture is a black sequencer strip (``--method render``,
the default; 16-bit). ``bpy.ops.sound.mixdown`` (``--method mixdown``) leaves speakers out in
background mode, and runs as a job that the script has to wait for. Output: a 32-bit float WAV of
the shot's length, sample 0 at the first frame. Findings: docs/research.md (Phase 0).
"""

from __future__ import annotations

import argparse
import math
import shutil
import struct
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import aud  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402

from soundstage.blender import schema, tag, util  # noqa: E402
from soundstage.blender.bake import collect_sources  # noqa: E402
from soundstage.blender.util import log  # noqa: E402

DISTANCE_MODELS = {
    "inverse_clamped": "INVERSE_CLAMPED",
    "linear_clamped": "LINEAR_CLAMPED",
    "exponential_clamped": "EXPONENT_CLAMPED",
    "none": "NONE",
}


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="blender_mixdown.py")
    p.add_argument("--out", required=True, help="output WAV (32-bit float)")
    p.add_argument("--run", action="append", default=[], help="tagging script to run first")
    p.add_argument("--frames", help="frame range A-B (default: scene range)")
    p.add_argument("--scene", help="scene name (default: the active scene)")
    p.add_argument("--doppler", type=float, help="Doppler factor (default: scene setting doppler_factor)")
    p.add_argument("--speed-of-sound", type=float, help="m/s (default: scene setting speed_of_sound)")
    p.add_argument("--method", choices=("render", "mixdown"), default="render",
                   help="render: audio of a video render (default); mixdown: bpy.ops.sound.mixdown, which "
                        "leaves speakers out in background mode (Blender 5.2)")
    p.add_argument("--timeout", type=float, default=600.0, help="seconds to wait for the mixdown job")
    return p.parse_args(argv)


def db(gain_db: float) -> float:
    return 10.0 ** (gain_db / 20.0)


def write_wav(path: str | Path, x: np.ndarray, rate: int) -> None:
    """32-bit float WAV, exactly ``len(x)`` frames (aud's writer pads or aborts depending on length)."""
    data = np.ascontiguousarray(x, dtype="<f4")
    channels = data.shape[1] if data.ndim == 2 else 1
    fmt = struct.pack("<HHIIHH", 3, channels, rate, rate * channels * 4, channels * 4, 32)
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 4 + 8 + len(fmt) + 8 + data.nbytes) + b"WAVE")
        f.write(b"fmt " + struct.pack("<I", len(fmt)) + fmt)
        f.write(b"data" + struct.pack("<I", data.nbytes) + data.tobytes())


def dry_sound(src: dict, fps: float, frame_start: int, length_s: float, rate: int, channels: int) -> np.ndarray:
    """The source's dry signal from ``frame_start`` on, as soundstage would play it (loop phase 0).

    Composed in numpy from the decoded sample: aud's own ``loop``/``limit`` chains either never end
    (``loop(-1)``) or fail when written.
    """
    sample = aud.Sound.file(src["sample"]).resample(rate, True)
    if src["pitch"] != 1.0:
        sample = sample.pitch(src["pitch"]).resample(rate, True)
    x = np.asarray(sample.data(), dtype=np.float32)
    x = x[:, None] if x.ndim == 1 else x
    if channels == 1:
        x = x.mean(axis=1, keepdims=True)
    elif x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1) / math.sqrt(2.0)  # beds: mono duplicated at -3.01 dB (signal-model.md)
    x = x[:, :channels] * db(src["gain_db"])
    n = round(length_s * rate)
    out = np.zeros((n, channels), dtype=np.float32)

    def index(frame: float) -> int:
        return round((frame - frame_start) * rate / fps)

    def ramp(seconds: float, size: int) -> np.ndarray:
        k = max(1, round(seconds * rate))
        return np.minimum(np.arange(size) / k, 1.0)[:, None]

    if src["mode"] == "once":
        frames = src["frame"] if isinstance(src["frame"], list) else [src["frame"]]
        hit = x * ramp(src["fade_in"], len(x)) if src["fade_in"] > 0 else x
        for f in frames:
            k = index(f)
            a, b = max(k, 0), min(k + len(hit), n)
            if a < b:
                out[a:b] += hit[a - k:b - k]
    else:
        k0 = index(src["frame"]) if src["frame"] is not None else 0
        a = max(k0, 0)
        reps = math.ceil((n - k0) / len(x)) + 1
        tiled = np.tile(x, (reps, 1))
        out[a:] = tiled[a - k0:a - k0 + n - a]
        if src["frame"] is not None and src["fade_in"] > 0:
            out[a:] *= ramp(src["fade_in"], n - a)
        if src["end_frame"] is not None:
            e = min(max(index(src["end_frame"]), 0), n)
            out[e:] *= 1.0 - ramp(src["fade_out"], n - e)
    return out


def add_speaker(scene, src: dict, wav: str, frame_start: int, frame_end: int, scale: float):
    obj = scene.objects[src["object"]]
    scene.frame_set(frame_start)
    bpy.ops.object.speaker_add(location=(0, 0, 0))
    spk = bpy.context.object
    spk.name = f"baseline_{src['id']}"
    spk.data.sound = bpy.data.sounds.load(wav)
    strip = spk.animation_data.nla_tracks[0].strips[0]
    strip.frame_end_ui = frame_end + 1
    spk.parent = obj
    spk.matrix_parent_inverse.identity()
    spk.location = src["offset"]
    d = spk.data
    d.volume, d.volume_min, d.volume_max = 1.0, 0.0, 1.0
    d.distance_reference = src["ref_distance"] / scale
    d.distance_max = src["max_distance"] / scale if src["max_distance"] else 3.4e38
    d.attenuation = src["rolloff"]
    return spk


def wait_for(path: Path, min_bytes: int, timeout: float) -> int:
    """Wait until the mixdown job has written at least ``min_bytes`` and the file stopped growing."""
    t0, last = time.monotonic(), -1
    while time.monotonic() - t0 < timeout:
        size = path.stat().st_size if path.exists() else 0
        if size >= min_bytes and size == last:
            return size
        last = size
        time.sleep(0.5)
    raise SystemExit(f"mixdown did not finish within {timeout:g} s ({last} of {min_bytes} bytes)")


def main(args: argparse.Namespace) -> None:
    scene = util.activate_scene(args.scene)
    util.run_scripts(args.run)
    scene = bpy.context.scene
    settings = schema.resolve_settings(tag.get_scene_settings(scene))
    sources, warnings = collect_sources(scene, settings, skip_invalid=False)
    for w in warnings:
        log(f"WARNING {w}")
    frame_start, frame_end = util.parse_frames(args.frames, scene)
    scene.frame_start, scene.frame_end = frame_start, frame_end
    fps = util.fps(scene)
    rate = int(settings["sample_rate"])
    length_s = (frame_end - frame_start + 1) / fps
    scale = scene.unit_settings.scale_length or 1.0

    spatial = [s for s in sources if s["spatial"]]
    models = {s["distance_model"] for s in spatial}
    if len(models) > 1:
        log(f"WARNING Blender has one distance model per scene; using {spatial[0]['distance_model']} for all")
    if spatial:
        scene.audio_distance_model = DISTANCE_MODELS[spatial[0]["distance_model"]]
    scene.audio_doppler_speed = args.speed_of_sound or settings["speed_of_sound"] / scale
    scene.audio_doppler_factor = settings["doppler_factor"] if args.doppler is None else args.doppler
    scene.audio_volume = min(1.0, db(settings["master_gain_db"]))
    scene.render.ffmpeg.audio_mixrate = rate

    tmp = Path(tempfile.mkdtemp(prefix="soundstage_baseline_"))
    seq = scene.sequence_editor_create()
    for i, src in enumerate(sources):
        wav = str(tmp / f"{i:03d}.wav")
        channels = 1 if src["spatial"] else 2
        write_wav(wav, dry_sound(src, fps, frame_start, length_s, rate, channels), rate)
        if src["spatial"]:
            add_speaker(scene, src, wav, frame_start, frame_end, scale)
        else:
            seq.strips.new_sound(f"bed_{src['id']}", wav, i + 1, frame_start)
        log(f"source {src['id']}: {'speaker' if src['spatial'] else 'sequencer strip'}")

    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    t0 = time.monotonic()
    n = round(length_s * rate)
    if args.method == "mixdown":
        bpy.ops.sound.mixdown(filepath=str(out), container="WAV", codec="PCM", format="F32", mixrate=rate)
        wait_for(out, n * 2 * 4, args.timeout)
    else:
        render_audio(scene, seq, tmp / "render.mkv", out, frame_start, frame_end, rate, n)
    shutil.rmtree(tmp, ignore_errors=True)
    log(f"wrote {out}: {n} samples, {args.method} {time.monotonic() - t0:.1f} s, "
        f"distance model {scene.audio_distance_model}, doppler {scene.audio_doppler_factor:g} "
        f"at {scene.audio_doppler_speed:g} m/s")


def render_audio(scene, seq, video: Path, out: Path, frame_start: int, frame_end: int, rate: int, n: int) -> None:
    """Render the scene's audio through a video render whose picture is a black sequencer strip.

    The render steps through every frame, which updates the speakers and the listener, and muxes
    the scene audio (16-bit FLAC: Blender's video audio has no float format); the picture costs
    nothing because the sequencer output replaces the 3D render.
    """
    black = seq.strips.new_effect("baseline_black", "COLOR", max((s.channel for s in seq.strips), default=0) + 1,
                                  frame_start=frame_start, length=frame_end - frame_start + 1)
    black.color = (0.0, 0.0, 0.0)
    r = scene.render
    r.use_sequencer = True
    r.resolution_x, r.resolution_y, r.resolution_percentage = 16, 16, 100
    r.image_settings.media_type = "VIDEO"
    r.image_settings.file_format = "FFMPEG"
    r.ffmpeg.format, r.ffmpeg.codec = "MKV", "H264"
    r.ffmpeg.audio_codec, r.ffmpeg.audio_channels, r.ffmpeg.audio_mixrate = "FLAC", "STEREO", rate
    r.filepath = str(video.with_suffix(""))
    r.use_file_extension = False
    bpy.ops.render.render(animation=True)
    x = aud.Sound.file(r.filepath).data()[:n]
    if len(x) < n:
        raise SystemExit(f"rendered audio has {len(x)} samples, expected {n}")
    write_wav(out, x, rate)

if __name__ == "__main__":
    main(parse_args(util.script_args()))
