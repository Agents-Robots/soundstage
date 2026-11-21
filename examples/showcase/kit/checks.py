"""Known-answer checks of a section (repo venv): probes rendered alone, expected values computed
from the baked positions with the speed of sound, results in ``<section>/check.json``.

A section's ``check.py`` defines ``run(c: Check)`` and calls ``Check.main(run)``. The section-level
checks (silent title page, ends, peak, loudness of the reference pass: C5, S2, S3) run for every
section.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from soundstage.engine.scene import load_scene

from . import audio, measure, story

C = 343.0


@dataclass
class Result:
    name: str
    measured: object
    expected: str
    ok: bool


class Geometry:
    """Baked positions of sources and listener, and when a sound emitted at a frame arrives."""

    def __init__(self, bake_dir: Path):
        self.man = json.loads((bake_dir / "scene.json").read_text())
        z = np.load(bake_dir / "scene.npz")
        self.frames = z["frames"].astype(float)
        self.src = z["src_pos"]
        self.fwd = z["src_fwd"]
        self.lis = z["listener_matrix"][:, :3, 3]
        self.tracks = {s["id"]: s["track"] for s in self.man["sources"] if s.get("track") is not None}

    def source(self, source_id: str, frame) -> np.ndarray:
        k = self.tracks[source_id]
        return np.stack([np.interp(frame, self.frames, self.src[:, k, i]) for i in range(3)], axis=-1)

    def forward(self, source_id: str, frame) -> np.ndarray:
        k = self.tracks[source_id]
        return np.stack([np.interp(frame, self.frames, self.fwd[:, k, i]) for i in range(3)], axis=-1)

    def entry(self, source_id: str) -> dict:
        return next(s for s in self.man["sources"] if s["id"] == source_id)

    def direct_gain_db(self, source_id: str, receive_frame: float) -> float:
        """Distance law (inverse, clamped at ref_distance) and cone gain at the emission time
        (docs/spec/signal-model.md): the expected level of the direct sound before panning."""
        e = self.entry(source_id)
        ef = self.emission(source_id, receive_frame)
        to_listener = self.listener(receive_frame) - self.source(source_id, ef)
        d = float(np.linalg.norm(to_listener))
        g = min(1.0, e["ref_distance"] / d)
        fwd = self.forward(source_id, ef)
        beta = np.degrees(np.arccos(np.clip(np.dot(fwd, to_listener) / (np.linalg.norm(fwd) * d), -1, 1)))
        inner, outer, g_out = e["cone_inner_deg"] / 2, e["cone_outer_deg"] / 2, 10 ** (e["cone_outer_gain_db"] / 20)
        cone = 1.0 if beta <= inner else g_out if beta >= outer else 1 + (g_out - 1) * (beta - inner) / (outer - inner)
        return 20 * np.log10(g * cone)

    def listener(self, frame) -> np.ndarray:
        return np.stack([np.interp(frame, self.frames, self.lis[:, i]) for i in range(3)], axis=-1)

    def distance(self, source_id: str, emit_frame, receive_frame=None) -> np.ndarray:
        rf = emit_frame if receive_frame is None else receive_frame
        return np.linalg.norm(self.source(source_id, emit_frame) - self.listener(rf), axis=-1)

    def arrival(self, source_id: str, emit_frame: float) -> float:
        """Frame at which the sound emitted at ``emit_frame`` reaches the listener (fixed point)."""
        r = emit_frame
        for _ in range(30):
            r = emit_frame + self.distance(source_id, emit_frame, r) / C * story.FPS
        return float(r)

    def emission(self, source_id: str, receive_frame: float) -> float:
        """Frame at which the sound heard at ``receive_frame`` was emitted (fixed point)."""
        e = receive_frame
        for _ in range(40):
            e = receive_frame - self.distance(source_id, e, receive_frame) / C * story.FPS
        return float(e)

    def rate(self, source_id: str, receive_frame: float, h: float = 0.5) -> float:
        """Playback rate heard at ``receive_frame``: d(emission) / d(reception)."""
        return (self.emission(source_id, receive_frame + h) - self.emission(source_id, receive_frame - h)) / (2 * h)


class Check:
    def __init__(self, section_dir: Path):
        self.dir = section_dir
        self.man = audio.manifest(section_dir)
        self.key = self.man["key"]
        self.windows = {p["key"]: p["window"] for p in self.man["passes"]}
        self.geo = Geometry(section_dir / "bake") if (section_dir / "bake").exists() else None  # not ``production``
        self.results: list[Result] = []
        self._scenes: dict = {}
        self.rate = self.man["sample_rate"]

    # --- rendering --------------------------------------------------------------------------------

    def scene(self, pass_key: str, extra: dict | None = None):
        p = next(p for p in self.man["passes"] if p["key"] == pass_key)
        k = json.dumps([pass_key, extra], sort_keys=True)
        if k not in self._scenes:
            overrides = {"master_gain_db": 0.0, **p["settings"], **(extra or {})}
            bake = self.dir / (f"bake_{p['bake']}" if p.get("bake") else "bake") / "scene.json"
            self._scenes[k] = load_scene(bake, overrides)
        return self._scenes[k]

    def probe(self, pass_key: str, name: str = "*", extra: dict | None = None, stems: bool = False):
        """Render a pass's probe(s) alone over the pass's frames, at gain 0 dB."""
        first, last = self.windows[pass_key]
        return audio.render_frames(self.scene(pass_key, extra), first, last, [f"{self.key}.probe.{pass_key}.{name}"],
                                   stems=stems)

    def pass_audio(self, pass_key: str) -> np.ndarray:
        x, _ = sf.read(self.dir / "passes" / f"{self.key}.{pass_key}.wav", always_2d=True)
        return x

    def pass_report(self, pass_key: str) -> dict:
        return json.loads((self.dir / "passes" / f"{self.key}.{pass_key}.report.json").read_text())

    def stem(self, pass_key: str, group: str) -> np.ndarray:
        x, _ = sf.read(self.dir / "passes" / f"{self.key}.{pass_key}_stem_{group}.wav", always_2d=True)
        return x

    def t(self, pass_key: str, seconds: float) -> int:
        """Sample index in a pass's render of a time from its start."""
        return int(round(seconds * self.rate))

    def frame(self, pass_key: str, seconds: float) -> float:
        return self.windows[pass_key][0] + seconds * story.FPS

    # --- results ----------------------------------------------------------------------------------

    def expect(self, name: str, measured, expected: str, ok: bool) -> bool:
        self.results.append(Result(name, measured, expected, bool(ok)))
        return bool(ok)

    def near(self, name: str, measured: float, target: float, tol: float, unit: str = "", digits: int = 3) -> bool:
        return self.expect(name, f"{measured:.{digits}f} {unit}".strip(), f"{target:.{digits}f} ± {tol:g} {unit}".strip(),
                           abs(measured - target) <= tol)

    def section_checks(self) -> None:
        summary = json.loads((self.dir / f"{self.key}.report.json").read_text())
        x, _ = sf.read(self.dir / f"{self.key}.wav", always_2d=True)
        spf = story.SAMPLES_PER_FRAME
        self.expect("WAV length", len(x), f"{self.man['frames'][1] * spf} samples", len(x) == self.man["frames"][1] * spf)
        if self.man["title_frames"]:
            a, b = self.man["title_frames"]
            self.expect("title page silent", f"max {np.abs(x[(a - 1) * spf:b * spf]).max():.1e}", "0", not np.any(x[(a - 1) * spf:b * spf]))
        edge = int(0.2 * self.rate)
        for label, part in (("first 0.2 s", x[:edge]), ("last 0.2 s", x[-edge:])):
            level = measure.db(np.abs(part).max()) if np.any(part) else -999.0
            self.expect(f"{label} of the section (C5)", f"{level:.1f} dBFS", "below -60 dBFS", level < -60)
        tp = summary["master"]["true_peak_dbtp"]
        if tp is None and not np.any(x):  # a silent section (``outro``)
            self.expect("true peak (S2)", "digital silence", "at most -1 dBTP", True)
        else:
            self.expect("true peak (S2)", f"{tp} dBTP", "at most -1 dBTP", tp is not None and tp <= -1.0)
        ref = summary["reference"]
        if ref["lufs_integrated"] is not None and not self.man.get("loudness_reported_only"):
            self.near(f"loudness of the reference pass {ref['pass']} (S2)", ref["lufs_integrated"], -18.0, 2.0, "LUFS", 1)
        for r in summary["passes"]:
            tails = [w for w in r["warnings"] if "tail" in w]
            self.expect(f"{r['pass']}: no cut tail (S3)", tails or "ok", "ok", not tails)

    def report(self) -> int:
        width = max(len(r.name) for r in self.results)
        for r in self.results:
            print(f"  {'ok  ' if r.ok else 'FAIL'} {r.name:{width}s}  {r.measured!s:>24}   expected {r.expected}")
        failed = [r for r in self.results if not r.ok]
        print(f"  {len(self.results) - len(failed)}/{len(self.results)} checks passed")
        (self.dir / "check.json").write_text(json.dumps(
            [{"name": r.name, "measured": str(r.measured), "expected": r.expected, "ok": r.ok} for r in self.results],
            indent=1) + "\n")
        return 1 if failed else 0

    @staticmethod
    def main(run, key: str) -> None:
        p = argparse.ArgumentParser()
        p.add_argument("--dir", default=str(Path(__file__).resolve().parents[3] / "out" / "showcase" / key))
        a = p.parse_args()
        c = Check(Path(a.dir))
        run(c)
        c.section_checks()
        sys.exit(c.report())
