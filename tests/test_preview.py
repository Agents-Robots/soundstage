"""Preview mux: picture and mix aligned by frame number (needs ffmpeg)."""

import json
import shutil
import subprocess
from fractions import Fraction

import numpy as np
import pytest
import soundfile as sf
from matplotlib.image import imsave

from soundstage import preview as pv
from soundstage.cli import main

from conftest import RATE

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not on PATH")
TOLERANCE = 48  # samples (1 ms): AAC smears the burst onset slightly


def frames(directory, numbers, prefix="", digits=6, ext="png"):
    directory.mkdir(parents=True, exist_ok=True)
    for n in numbers:
        img = np.full((48, 64, 3), (n % 10) / 10)
        imsave(directory / f"{prefix}{n:0{digits}d}.{ext}", img)
    return directory


def mix(path, fps, first_frame, n_frames, bursts, report=True):
    """A stereo WAV with 30 ms 1 kHz bursts starting exactly at the given frames."""
    fps = Fraction(fps).limit_denominator(1001)
    x = np.zeros((round(n_frames * RATE / fps), 2))
    t = np.arange(int(0.03 * RATE))
    for f in bursts:
        k = round((f - first_frame) * RATE / fps)
        x[k:k + len(t)] = 0.5 * np.sin(2 * np.pi * 1000 * t / RATE)[:, None]
    sf.write(path, x, RATE, subtype="FLOAT")
    if report:
        path.with_suffix(".report.json").write_text(json.dumps(
            {"frames": [first_frame, first_frame + n_frames - 1], "fps": float(fps)}))
    return path


def decoded(mp4):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp4), "-f", "f32le", "-ac", "2", "-ar", str(RATE), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2)


def bursts_at(audio):
    """Start samples of the bursts (envelope above half the peak, after at least 0.1 s of quiet)."""
    loud = np.abs(audio).max(axis=1) > 0.5 * np.abs(audio).max()
    idx = np.nonzero(loud)[0]
    return [int(i) for j, i in enumerate(idx) if j == 0 or i - idx[j - 1] > RATE // 10]


def probe(mp4):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                          "stream=nb_read_packets,r_frame_rate", "-of", "json", str(mp4)],
                         capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    return int(s["nb_read_packets"]), Fraction(s["r_frame_rate"])


def test_sequence_with_gap_starting_after_the_mix(tmp_path):
    numbers = [n for n in range(5, 41) if not 20 <= n <= 24]
    seq = frames(tmp_path / "seq", numbers)
    wav = mix(tmp_path / "mix.wav", 25, 1, 50, bursts=[10, 30])
    res = pv.preview(wav, tmp_path / "p.mp4", frames=seq)
    assert res.picture_frames == (5, 40) and res.held_frames == 5
    assert res.audio_offset_samples == 4 * RATE // 25
    n, rate = probe(tmp_path / "p.mp4")
    assert n == 36 and rate == 25
    audio = decoded(tmp_path / "p.mp4")
    assert 0 <= len(audio) - 36 * RATE // 25 < 1024  # AAC pads to whole 1024-sample frames
    got = bursts_at(audio)
    expected = [(f - 5) * RATE // 25 for f in (10, 30)]
    assert len(got) == 2 and all(abs(g - e) <= TOLERANCE for g, e in zip(got, expected)), (got, expected)


def test_sequence_starting_before_the_mix_ntsc_rate(tmp_path):
    fps = 30000 / 1001
    seq = frames(tmp_path / "seq", range(1, 61), prefix="frame_", digits=4)
    wav = mix(tmp_path / "mix.wav", fps, 10, 50, bursts=[12, 50])
    res = pv.preview(wav, tmp_path / "p.mp4", frames=tmp_path / "seq" / "frame_")
    assert res.fps == Fraction(30000, 1001) and res.audio_offset_samples < 0
    n, rate = probe(tmp_path / "p.mp4")
    assert n == 60 and rate == Fraction(30000, 1001)
    got = bursts_at(decoded(tmp_path / "p.mp4"))
    expected = [round((f - 1) * RATE * Fraction(1001, 30000)) for f in (12, 50)]
    assert len(got) == 2 and all(abs(g - e) <= TOLERANCE for g, e in zip(got, expected)), (got, expected)


def test_video_input_with_start_frame(tmp_path):
    seq = frames(tmp_path / "seq", range(101, 151))
    plain = mix(tmp_path / "silent.wav", 24, 101, 50, bursts=[], report=False)
    pv.preview(plain, tmp_path / "video.mp4", frames=seq, fps=24, start_frame=101, width=0)
    wav = mix(tmp_path / "mix.wav", 24, 91, 80, bursts=[120])
    res = pv.preview(wav, tmp_path / "p.mp4", video=tmp_path / "video.mp4", video_start_frame=101, width=0)
    assert res.picture_frames == (101, 150)
    got = bursts_at(decoded(tmp_path / "p.mp4"))
    assert len(got) == 1 and abs(got[0] - 19 * RATE // 24) <= TOLERANCE, got


def test_find_sequence_picks_the_main_set_and_honours_a_prefix(tmp_path):
    seq = frames(tmp_path / "seq", range(1, 11))
    frames(seq, range(1, 3), prefix="thumb_")
    (seq / "notes.txt").write_text("x")
    assert [n for n, _ in pv.find_sequence(seq)] == list(range(1, 11))
    assert [n for n, _ in pv.find_sequence(seq / "thumb_")] == [1, 2]
    with pytest.raises(pv.PreviewError):
        pv.find_sequence(seq / "missing_")


def test_timing_needs_a_report_or_explicit_values(tmp_path):
    wav = mix(tmp_path / "mix.wav", 25, 1, 10, bursts=[], report=False)
    with pytest.raises(pv.PreviewError, match="--start-frame"):
        pv.mix_timing(wav, None, None)
    assert pv.mix_timing(wav, 7, 29.97002997) == (7, Fraction(30000, 1001))


def test_cli_default_output_name(tmp_path):
    seq = frames(tmp_path / "seq", range(1, 11))
    wav = mix(tmp_path / "shot.wav", 25, 1, 10, bursts=[])
    assert main(["preview", str(wav), "--frames", str(seq), "--width", "32"]) == 0
    assert (tmp_path / "shot_preview.mp4").is_file()
