"""Join showcase sections into one video (repo venv; sections/README.md, "Assembly").

    .venv/bin/python examples/showcase/assemble.py trailer [--pictures DIR] [--out DIR]

For each section of the cut (``cuts.py``) its picture (``<pictures>/<key>/frames/`` with numbered
PNGs, or ``<pictures>/<key>.mp4``; by default the preview frames) and its WAV are checked against
``section.json``: size and aspect, frame count, WAV length, black first and last frames, silent first
and last 0.2 s, true peak, loudness of the reference pass, and that the WAV was rendered from the
manifest as it is (the report's frames, gain and passes; not older than the manifest). Any failure
stops the assembly. Then the WAVs are joined sample-exact with no gain change, the pictures are
joined with one encode (a section without its title page fades in over its first 8 frames), and the
two are muxed once with ``soundstage preview``. Writes ``<out>/<cut>.wav``, ``<cut>.mp4``,
``<cut>.chapters.txt`` (start time and title of each section) and ``<cut>.sections.txt``.

A ``Clip`` takes part of one pass, or a section's title page: its frames are cut hard, its sound gets
the clip's fixed gain, a short fade where it is cut, and optionally a tail that runs on under the next
part.
The whole cut's true peak is then checked again (S2).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path[:0] = [str(REPO), str(HERE)]

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from cuts import CUTS, EDGE_FADE_S, TITLE_PAGE, Clip  # noqa: E402
from kit import story  # noqa: E402
from PIL import Image  # noqa: E402

from soundstage.engine import mix, report  # noqa: E402

OUT = REPO / "out" / "showcase"
SPF = story.SAMPLES_PER_FRAME
EDGE_S = 0.2


class Part:
    """One section of a cut: its manifest, WAV and picture, and the frames the cut takes."""

    def __init__(self, entry: str | Clip, pictures: Path | None):
        self.clip = entry if isinstance(entry, Clip) else None
        self.key, _, mode = (entry.key, "", "") if self.clip else entry.partition(":")
        self.dir = OUT / self.key
        self.man = json.loads((self.dir / "section.json").read_text())
        self.wav = self.dir / f"{self.key}.wav"
        self.end = self.man["frames"][1]
        if self.clip:
            w = self.man["title_frames"] if self.clip.pass_key == TITLE_PAGE else \
                next(p["window"] for p in self.man["passes"] if p["key"] == self.clip.pass_key)
            self.first = w[0] + story.seconds_to_frames(self.clip.start)
            self.last = w[1] if self.clip.end is None else w[0] + story.seconds_to_frames(self.clip.end) - 1
            assert w[0] <= self.first <= self.last <= w[1], f"{entry}: outside its pass {w}"
        else:
            self.first = self.man["title_frames"][1] + 1 if mode == "body" and self.man["title_frames"] else 1
            self.last = self.end
        base = pictures / self.key if pictures else self.dir / "frames"
        if pictures and not base.is_dir():
            base = pictures / f"{self.key}.mp4"
        self.picture = base

    @property
    def trimmed(self) -> bool:
        """A section without its title page: it fades in (clips are cut hard)."""
        return self.first > 1 and not self.clip

    def sound(self, rate: int) -> tuple[np.ndarray, np.ndarray]:
        """The part's sound over its frames, and the tail that runs on after them."""
        x, _ = sf.read(self.wav, always_2d=True)
        a, b = (self.first - 1) * SPF, self.last * SPF
        if not self.clip:
            return x[a:b], np.zeros((0, 2))
        g = 10 ** (self.clip.gain_db / 20)
        n = int(self.clip.tail * rate)
        body, tail = x[a:b] * g, x[b:b + n] * g
        edge = int(EDGE_FADE_S * rate)
        if a > 0:
            body[:edge] *= np.sin(np.linspace(0, np.pi / 2, edge))[:, None] ** 2
        if len(tail):
            tail = tail * np.cos(np.linspace(0, np.pi / 2, len(tail)))[:, None] ** 2
        elif b < len(x):
            body[-edge:] *= np.cos(np.linspace(0, np.pi / 2, edge))[:, None] ** 2
        return body, tail

    def frame_image(self, n: int) -> np.ndarray:
        """Frame n (1-based) of the picture as greyscale."""
        if self.picture.is_dir():
            return np.asarray(Image.open(self.picture / f"{n:05d}.png").convert("L"), dtype=float)
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "f.png"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(self.picture), "-vf", f"select=eq(n\\,{n - 1})",
                            "-frames:v", "1", str(png)], check=True)
            return np.asarray(Image.open(png).convert("L"), dtype=float)

    def numbered(self) -> dict[int, Path]:
        return {int(f.stem): f for f in self.picture.glob("*.png") if f.stem.isdigit()}

    def held(self) -> int:
        """Frames missing from a frame folder (a preview rendered with a step): each holds the previous."""
        return self.last - len([n for n in self.numbered() if n <= self.last]) if self.picture.is_dir() else 0

    def picture_frames(self) -> tuple[int, tuple[int, int]]:
        if self.picture.is_dir():
            files = self.numbered()
            size = Image.open(files[min(files)]).size if files else (0, 0)
            return max(files, default=0), size
        probe = json.loads(subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
             "stream=nb_read_frames,width,height", "-of", "json", str(self.picture)], capture_output=True,
            text=True, check=True).stdout)["streams"][0]
        return int(probe["nb_read_frames"]), (int(probe["width"]), int(probe["height"]))

    def problems(self) -> list[str]:
        out = []
        man, key = self.man, self.key
        n, (w, h) = self.picture_frames()
        rw, rh = man["resolution"]
        if n != self.end:
            out.append(f"{key}: the picture has {n} frames, the manifest {self.end}")
        if w * rh != h * rw:
            out.append(f"{key}: picture {w} x {h}, not the aspect of {rw} x {rh}")
        if man["fps"] != story.FPS:
            out.append(f"{key}: {man['fps']} fps")
        if not self.wav.exists():
            return out + [f"{key}: no WAV"]
        x, rate = sf.read(self.wav, always_2d=True)
        if len(x) != self.end * SPF or rate != story.RATE:
            out.append(f"{key}: WAV {len(x)} samples at {rate} Hz, not {self.end * SPF} at {story.RATE}")
        edge = int(EDGE_S * rate)
        for label, part in (("first", x[:edge]), ("last", x[-edge:])):
            if np.abs(part).max(initial=0.0) > 10 ** (-60 / 20):
                out.append(f"{key}: the {label} 0.2 s are not silent")
        if n:
            for f in (1, self.end):
                if self.frame_image(f).max() > 2:
                    out.append(f"{key}: frame {f} is not black")
        report_path = self.dir / f"{key}.report.json"
        if not report_path.exists():
            return out + [f"{key}: no report: the sound was not rendered by the audio step"]
        rep = json.loads(report_path.read_text())
        # rendered from the manifest as it is (outro R5): same frames, gain and passes, not older
        passes = [(p["pass"], p["frames"], p["settings"]) for p in rep["passes"]]
        want = [(p["key"], p["window"], p["settings"]) for p in man["passes"]]
        if (rep["frames"] != man["frames"] or rep["gain_db"] != man["gain_db"] or passes != want
                or Path(rep["output"]) != self.wav.resolve()
                or self.wav.stat().st_mtime < (self.dir / "section.json").stat().st_mtime):
            out.append(f"{key}: the WAV was not rendered from its manifest as it is (run the audio step)")
        tp = rep["master"]["true_peak_dbtp"]
        if tp is not None and tp > -1.0:
            out.append(f"{key}: true peak {tp} dBTP")
        lufs = rep["reference"]["lufs_integrated"]
        if lufs is not None and not man.get("loudness_reported_only") and abs(lufs + 18.0) > 2.0:
            out.append(f"{key}: reference pass at {lufs} LUFS")
        return out


def chapter_time(seconds: float) -> str:
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"


def join_pictures(parts: list[Part], size: tuple[int, int], out: Path, tmp: Path) -> None:
    """One encode: each picture trimmed to the cut's frames, scaled to one size; a trimmed section
    fades in from black over its first FADE_FRAMES frames. A frame folder is read through a numbered
    sequence of links over the cut's frames, a missing frame linking to the one before it."""
    args, chains = [], []
    for i, p in enumerate(parts):
        if p.picture.is_dir():
            seq = tmp / f"{i:02d}.{p.key}"  # a section may come twice (clips)
            seq.mkdir()
            files, current = p.numbered(), None
            for k, f in enumerate(range(1, p.last + 1)):
                current = files.get(f, current)
                if f >= p.first:
                    (seq / f"{k - p.first + 2:05d}.png").symlink_to(current)
            args += ["-framerate", str(story.FPS), "-start_number", "1", "-i", str(seq / "%05d.png")]
            trim = ""
        else:
            args += ["-i", str(p.picture)]
            trim = f"trim=start_frame={p.first - 1}:end_frame={p.last},setpts=PTS-STARTPTS,"
        chain = f"[{i}:v]{trim}scale={size[0]}:{size[1]},fps={story.FPS}"
        if p.trimmed or (i == 0 and p.clip):  # a cut that opens on a clip fades in from black
            chain += f",fade=t=in:s=0:n={story.FADE_FRAMES}"
        chains.append(chain + f"[v{i}]")
    graph = ";".join(chains) + ";" + "".join(f"[v{i}]" for i in range(len(parts))) + \
        f"concat=n={len(parts)}:v=1:a=0[v]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args, "-filter_complex", graph, "-map", "[v]",
                    "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(out)], check=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("cut", choices=sorted(CUTS))
    p.add_argument("--pictures", help="folder with <key>/ (numbered PNGs) or <key>.mp4 per section "
                                      "(default: each section's preview frames)")
    p.add_argument("--out", default=str(OUT / "cuts"))
    a = p.parse_args()
    parts = [Part(e, Path(a.pictures) if a.pictures else None) for e in CUTS[a.cut]]
    problems = [m for part in parts for m in part.problems()]
    if problems:
        sys.exit("not assembled:\n  " + "\n  ".join(problems))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    rate = story.RATE
    total = sum(p.last - p.first + 1 for p in parts) * SPF
    whole = np.zeros((total + max(int(getattr(p.clip, "tail", 0.0) * rate) for p in parts), 2))
    chapters, rows, at, prev = [], [], 0, None
    for part in parts:
        body, tail = part.sound(rate)
        whole[at:at + len(body)] += body
        whole[at + len(body):at + len(body) + len(tail)] += tail
        t = at / rate
        if part.key != prev:  # a chapter per section, however many clips it gives
            chapters.append(f"{chapter_time(t)} {part.man['title']}")
        prev = part.key
        rep = json.loads((part.dir / f"{part.key}.report.json").read_text())
        m = report.metrics(body, rate) if part.clip else {"lufs_integrated": rep["reference"]["lufs_integrated"],
                                                          "true_peak_dbtp": rep["master"]["true_peak_dbtp"]}
        what = f"{part.clip.pass_key} {part.clip.start:g}-{part.clip.end or 'end'} s" if part.clip else "reference"
        rows.append(f"{part.key:12s} {len(body) / rate:7.2f} s  {what:22s} "
                    f"{m['lufs_integrated']!s:>7} LUFS  true peak {m['true_peak_dbtp']!s:>6} dBTP"
                    + (f"  gain {part.clip.gain_db:+g} dB" if part.clip and part.clip.gain_db else "")
                    + (f"  ({part.held()} frames held)" if part.held() else ""))
        at += len(body)
    whole = whole[:total]
    if parts[0].clip:  # the cut opens on a clip: its sound fades in with the picture (C5)
        n = int(story.FADE_FRAMES * SPF)
        whole[:n] *= np.sin(np.linspace(0, np.pi / 2, n))[:, None] ** 2
    t = total / rate
    wav = out / f"{a.cut}.wav"
    mix.write_wav(wav, whole, story.RATE)
    peak = report.metrics(whole, rate)["true_peak_dbtp"]
    if peak is not None and peak > -1.0:
        sys.exit(f"{a.cut}: true peak {peak} dBTP after joining (S2): lower a clip's gain")
    frames = len(whole) // SPF
    summary = {"output": str(wav.resolve()), "sample_rate": story.RATE, "fps": float(story.FPS), "frames": [1, frames]}
    wav.with_suffix(".report.json").write_text(json.dumps(summary, indent=1) + "\n")
    (out / f"{a.cut}.chapters.txt").write_text("\n".join(chapters) + "\n")
    (out / f"{a.cut}.sections.txt").write_text("\n".join(rows) + f"\n{'total':12s} {t:7.2f} s\n")

    size = max((part.picture_frames()[1] for part in parts), key=lambda s: s[0])
    with tempfile.TemporaryDirectory() as tmp:
        video = Path(tmp) / "picture.mp4"
        join_pictures(parts, size, video, Path(tmp))
        subprocess.run([str(REPO / ".venv" / "bin" / "soundstage"), "preview", str(wav), "--video", str(video),
                        "--width", "0", "-o", str(out / f"{a.cut}.mp4")], check=True)
    print("\n".join(rows))
    print(f"wrote {wav}, {out / f'{a.cut}.mp4'}: {frames} frames, {t:.2f} s")


if __name__ == "__main__":
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is not on PATH")
    main()
