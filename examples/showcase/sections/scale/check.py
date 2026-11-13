"""Known answers of ``scale`` (README.md): the sources the instances give, the loop phases of the
queue (pink-noise probes in the same instances: correlated copies against independent ones), and the
motorway's far field and culling against a render with both off.

    .venv/bin/python examples/showcase/sections/scale/check.py [--dir out/showcase/scale]
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parents[1]), str(HERE)]

import numpy as np  # noqa: E402
import pyloudnorm  # noqa: E402
from kit import audio, measure  # noqa: E402
from kit.checks import Check  # noqa: E402
from section import QUEUE, QUEUE_END_S  # noqa: E402

OCTAVES = (125, 250, 500, 1000, 2000, 4000, 8000)
SPAN_S = (0.5, QUEUE_END_S - 0.2)


def octaves_db(x: np.ndarray, rate: int) -> np.ndarray:
    m = measure.mono(x)
    return np.array([measure.band_db(m, rate, f / 2 ** 0.5, f * 2 ** 0.5) for f in OCTAVES])


def correlation(a: np.ndarray, b: np.ndarray, rate: int, window_s: float = 0.4, max_lag_s: float = 0.03) -> float:
    """Mean over windows of the largest normalised cross-correlation within +-max_lag_s: the copies'
    delay drifts slowly as the camera walks (0.2 ms over the pass), so each window finds its own lag."""
    w, m = int(window_s * rate), int(max_lag_s * rate)
    out = []
    for s in range(0, len(a) - w, w):
        u, v = a[s:s + w] - a[s:s + w].mean(), b[s:s + w] - b[s:s + w].mean()
        cc = np.fft.irfft(np.fft.rfft(u, 2 * w) * np.conj(np.fft.rfft(v, 2 * w)))
        out.append(np.max(np.concatenate([cc[:m + 1], cc[-m:]])) / np.sqrt(np.sum(u ** 2) * np.sum(v ** 2)))
    return float(np.mean(out))


def short_term_lufs(x: np.ndarray, rate: int, window_s: float = 3.0, hop_s: float = 0.5) -> np.ndarray:
    meter = pyloudnorm.Meter(rate)
    w, h = int(window_s * rate), int(hop_s * rate)
    return np.array([meter.integrated_loudness(x[a:a + w]) for a in range(0, len(x) - w, h)])


def run(c: Check) -> None:
    rate = c.rate
    man = json.loads((c.dir / "bake" / "scene.json").read_text())
    ids = [s["id"] for s in man["sources"]]
    counts = {k: sum(1 for i in ids if i.startswith(f"scale.{k}.")) for k in ("same", "random", "motorway")}
    c.expect("sources in the bake (same, random, motorway)", f"{counts['same']}, {counts['random']}, {counts['motorway']}",
             "40, 40, 600", (counts["same"], counts["random"], counts["motorway"]) == (40, 40, 600))
    dropped = [w for w in man["warnings"] if "instances of tagged object" in w]
    c.expect("bake: no instances dropped (instance_limit=0)", dropped or "none", "none", not dropped)
    default = json.loads((c.dir / "bake_default_limit" / "scene.json").read_text())
    kept = sum(1 for s in default["sources"] if s["id"].startswith("scale.same."))
    warned = any("scale.queue_same.engine" in w for w in default["warnings"])
    c.expect("with the default instance_limit (32): the queue's cars kept, and a warning", f"{kept}, warned {warned}",
             "32, warned True", kept == 32 and warned)

    # the queue: every probe alone, then all together
    a, b = c.t("same", SPAN_S[0]), c.t("same", SPAN_S[1])
    singles = {}
    for k in ("same", "random"):
        singles[k] = [c.probe(k, f"q{i:02d}/*").audio[a:b] for i in range(QUEUE)]
    for k, want, ok in (("same", "at least 0.9", lambda r: r >= 0.9), ("random", "at most 0.2", lambda r: r <= 0.2)):
        r = correlation(singles[k][2][:, 0], singles[k][3][:, 0], rate)
        c.expect(f"{k}: probes of cars 3 and 4 (left channel), correlation at the best lag, 0.4 s windows",
                 f"{r:.3f}", want, ok(r))
    for k in ("same", "random"):
        together = c.probe(k).audio[a:b]
        powers = sum(10 ** (octaves_db(x, rate) / 10) for x in singles[k])
        dev = octaves_db(together, rate) - 10 * np.log10(powers)
        worst = float(dev[np.argmax(np.abs(dev))])
        if k == "random":
            c.expect("random: all 40 probes together against the sum of their powers, every octave",
                     f"max {worst:+.2f} dB", "within 1 dB", abs(worst) <= 1.0)
        else:  # the comb's notches lie 57 Hz apart and more: an octave averages them out
            c.expect("same: all 40 probes together against the sum of their powers, per octave (reported)",
                     " ".join(f"{d:+.1f}" for d in dev) + " dB", "reported", True)

    # the motorway: far field and culling against a render with both off
    first, last = c.windows["motorway"]
    mix = c.pass_audio("motorway")
    full = audio.render_frames(c.scene("motorway", {"master_gain_db": c.man["gain_db"], "detail_voices": None,
                                                    "cull_db": None}), first, last, ["scale.motorway.*"]).audio
    meter = pyloudnorm.Meter(rate)
    d = meter.integrated_loudness(mix) - meter.integrated_loudness(full)
    c.near("motorway: integrated loudness against detail_voices=null, cull_db=null", d, 0.0, 0.3, "LU", 2)
    st = short_term_lufs(mix, rate) - short_term_lufs(full, rate)
    c.expect("motorway: short-term loudness (3 s) against the same, every 0.5 s", f"max {np.max(np.abs(st)):.2f} LU",
             "within 1.0 LU", np.max(np.abs(st)) <= 1.0)
    rep = c.pass_report("motorway")
    far, cull = rep.get("far_field") or {}, rep.get("culling") or {}
    c.expect("motorway: sources in the far field", f"{far.get('far_sources')} of {len(rep['sources'])}",
             "above zero", (far.get("far_sources") or 0) > 0)
    culled = sum(s.get("culled_s") or 0.0 for s in rep["sources"])
    c.expect("motorway: seconds culled, all sources (reported)",
             f"{culled:.1f} s; skipped entirely {cull.get('skipped_entirely')}", "reported", True)
    rates = [r for s in rep["sources"] for r in (s.get("rate") or [])]
    c.expect("motorway: playback rates", f"{min(rates):.3f} to {max(rates):.3f}", "within 0.85 to 1.15",
             0.85 <= min(rates) and max(rates) <= 1.15)
    clamps = [w for w in rep["warnings"] if "clamp" in w]
    c.expect("motorway: no playback-rate clamp warning", clamps or "none", "none", not clamps)
    row = next(r for r in json.loads((c.dir / "scale.report.json").read_text())["passes"] if r["pass"] == "motorway")
    c.expect("motorway: render time, peak memory (reported)", f"{row['render_seconds']} s, {row['peak_rss_mb']} MB",
             "reported", True)


if __name__ == "__main__":
    Check.main(run, "scale")
