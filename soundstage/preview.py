"""Preview: mux a rendered mix with the shot's frames (or a video) into an MP4 for a sync check.

Picture and sound are aligned by frame number. The mix's first frame and fps come from its report
(``<mix>.report.json``) or from the command line. A frame sequence's frame numbers come from the
file names; it is linked into a gap-free numbered sequence in a temporary directory, with gaps
holding the previous image, and read by ffmpeg at the exact (rational) frame rate, so video frame k
is picture frame ``first + k``. The audio is trimmed or delayed by a whole number of samples, so
that its sample at picture frame N is the mix's sample of frame N, padded with silence if the
picture runs longer, to exactly the picture's length. A video must have the mix's frame rate.
Runs in the repo venv; needs ffmpeg and ffprobe (``--ffmpeg``, ``$SOUNDSTAGE_FFMPEG`` or ``PATH``).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import soundfile as sf

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr", ".bmp", ".webp"}
NUMBERED = re.compile(r"(.*?)(\d+)(\.\w+)")


class PreviewError(Exception):
    """Missing input, inconsistent timing or an ffmpeg failure."""


@dataclass
class PreviewResult:
    output: Path
    fps: Fraction
    picture_frames: tuple[int, int]  # first and last picture frame (Blender frame numbers)
    held_frames: int  # missing frames in the sequence, filled with the previous image
    audio_offset_samples: int  # mix samples skipped (> 0) or silence inserted (< 0) at the start


def find_ffmpeg(explicit: str | None = None) -> str:
    ffmpeg = explicit or os.environ.get("SOUNDSTAGE_FFMPEG") or shutil.which("ffmpeg")
    if not ffmpeg:
        raise PreviewError("ffmpeg not found: put it on PATH, set SOUNDSTAGE_FFMPEG, or pass --ffmpeg")
    return ffmpeg


def as_fraction(fps: float) -> Fraction:
    """Frame rate as a fraction: 30 -> 30/1, 29.97002997 -> 30000/1001."""
    return Fraction(fps).limit_denominator(1001)


def mix_timing(wav: Path, start_frame: int | None, fps: float | None) -> tuple[int, Fraction]:
    """First frame and fps of a mix: explicit values win over the report next to the WAV."""
    report = wav.with_suffix(".report.json")
    if (start_frame is None or fps is None) and report.is_file():
        data = json.loads(report.read_text())
        start_frame = data["frames"][0] if start_frame is None else start_frame
        fps = data["fps"] if fps is None else fps
    if start_frame is None or fps is None:
        raise PreviewError(f"no {report.name} next to the mix: pass --start-frame and --fps")
    return int(start_frame), as_fraction(fps)


def find_sequence(spec: str | Path) -> list[tuple[int, Path]]:
    """Numbered images, sorted by frame: every numbered image in a directory, or the files of a prefix.

    ``renders/shot1/`` takes the largest set of files that share a prefix and an extension
    (``000001.png``, ``frame_0001.png``); ``renders/shot1/frame_`` takes ``frame_<n>.<ext>`` only.
    """
    path = Path(spec)
    directory, prefix = (path, None) if path.is_dir() else (path.parent, path.name)
    if not directory.is_dir():
        raise PreviewError(f"{directory} is not a directory")
    groups: dict[tuple[str, str], list[tuple[int, Path]]] = {}
    for f in directory.iterdir():
        m = NUMBERED.fullmatch(f.name)
        if not m or m.group(3).lower() not in IMAGE_EXTENSIONS or not f.is_file():
            continue
        if prefix is not None and m.group(1) != prefix:
            continue
        groups.setdefault((m.group(1), m.group(3).lower()), []).append((int(m.group(2)), f))
    if not groups:
        raise PreviewError(f"no numbered images in {spec}")
    items = sorted(max(groups.values(), key=len))
    frames = [n for n, _ in items]
    if len(set(frames)) != len(frames):
        raise PreviewError(f"frame numbers occur twice in {spec} (e.g. 0001.png and 001.png)")
    return items


def link_sequence(items: list[tuple[int, Path]], directory: Path) -> int:
    """Symlink images as 000000.ext, 000001.ext, ... with no gaps; return the number of held frames."""
    ext = items[0][1].suffix.lower()
    by_frame = dict(items)
    held, current = 0, items[0][1]
    for k, frame in enumerate(range(items[0][0], items[-1][0] + 1)):
        if frame in by_frame:
            current = by_frame[frame]
        else:
            held += 1
        os.symlink(current.resolve(), directory / f"{k:06d}{ext}")
    return held


def audio_filter(offset_samples: int, length_samples: int) -> str:
    """Trim (offset > 0) or delay (offset < 0) the mix by whole samples; pad or cut to the length."""
    if offset_samples > 0:
        head = f"atrim=start_sample={offset_samples},asetpts=PTS-STARTPTS"
    elif offset_samples < 0:
        head = f"adelay=delays={-offset_samples}S:all=1"
    else:
        head = "anull"
    return f"{head},apad=whole_len={length_samples},atrim=end_sample={length_samples}"


def video_filter(width: int) -> str:
    """Scale to ``width`` (0: keep the size), with even dimensions for yuv420p."""
    if width:
        return f"scale={width}:-2:flags=lanczos,format=yuv420p"
    return "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p"


def preview(wav: str | Path, output: str | Path, *, frames: str | Path | None = None, video: str | Path | None = None,
            fps: float | None = None, start_frame: int | None = None, video_start_frame: int | None = None,
            width: int = 1280, ffmpeg: str | None = None) -> PreviewResult:
    """Write an H.264 + AAC MP4 of the picture with the mix aligned by frame number."""
    if (frames is None) == (video is None):
        raise PreviewError("pass either a frame sequence or a video")
    wav, output = Path(wav), Path(output)
    if not wav.is_file():
        raise PreviewError(f"{wav} not found")
    first_mix_frame, rate_fps = mix_timing(wav, start_frame, fps)
    sample_rate = sf.info(str(wav)).samplerate
    ff = find_ffmpeg(ffmpeg)
    output.parent.mkdir(parents=True, exist_ok=True)
    encode = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-vf", video_filter(width)]

    with tempfile.TemporaryDirectory(prefix="soundstage_preview_") as tmp:
        if frames is not None:
            items = find_sequence(frames)
            first, last = items[0][0], items[-1][0]
            held = link_sequence(items, Path(tmp))
            picture = ["-framerate", str(rate_fps), "-start_number", "0",
                       "-i", str(Path(tmp) / f"%06d{items[0][1].suffix.lower()}")]
            n_frames = last - first + 1
        else:
            video = Path(video)
            if not video.is_file():
                raise PreviewError(f"{video} not found")
            n_frames, video_fps = probe_video(ff, video)
            if video_fps != rate_fps:
                raise PreviewError(f"{video.name} runs at {float(video_fps):g} fps, the mix at {float(rate_fps):g} fps")
            first = first_mix_frame if video_start_frame is None else int(video_start_frame)
            last, held = first + n_frames - 1, 0
            picture = ["-i", str(video)]
            if width == 0:
                encode = ["-c:v", "copy"]
        offset = round((first - first_mix_frame) * sample_rate / rate_fps)
        length = round(n_frames * sample_rate / rate_fps)
        cmd = [ff, "-y", "-v", "error", *picture, "-i", str(wav),
               "-map", "0:v:0", "-map", "1:a:0", *encode, "-frames:v", str(n_frames),
               "-af", audio_filter(offset, length), "-c:a", "aac", "-b:a", "192k", "-ar", str(sample_rate),
               "-movflags", "+faststart", str(output)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise PreviewError(f"ffmpeg failed ({proc.returncode}): {proc.stderr.strip()[-2000:]}")
    return PreviewResult(output, rate_fps, (first, last), held, offset)


def probe_video(ffmpeg: str, path: Path) -> tuple[int, Fraction]:
    """Frame count and frame rate of a video (ffprobe next to ffmpeg, or on PATH)."""
    ffprobe = Path(ffmpeg).with_name("ffprobe")
    ffprobe = str(ffprobe) if ffprobe.is_file() else shutil.which("ffprobe")
    if not ffprobe:
        raise PreviewError("ffprobe not found next to ffmpeg or on PATH")
    proc = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                           "stream=nb_read_packets,r_frame_rate", "-of", "json", str(path)],
                          capture_output=True, text=True)
    streams = json.loads(proc.stdout or "{}").get("streams") if proc.returncode == 0 else None
    if not streams:
        raise PreviewError(f"no video stream in {path}: {proc.stderr.strip()}")
    return int(streams[0]["nb_read_packets"]), as_fraction(float(Fraction(streams[0]["r_frame_rate"])))
