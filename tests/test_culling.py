"""Culling (FR-68): the budget rule, the dry-signal energy, and culled renders against full ones."""

import numpy as np
import pytest

from soundstage.engine import render, signals
from soundstage.levels import skip_mask

from conftest import RATE

OFF = {"cull_db": None}


def error_db(ref: np.ndarray, out: np.ndarray, window: int | None = None) -> float:
    """Error energy against the reference, overall or in the worst window (dB)."""
    e = np.square(ref - out).sum(axis=1)
    r = np.square(ref).sum(axis=1)
    if window is None:
        return 10 * np.log10(e.sum() / r.sum())
    n = len(e) // window
    return 10 * np.log10(np.max(e[:n * window].reshape(n, window).sum(1) / r[:n * window].reshape(n, window).sum(1)))


@pytest.fixture
def noise(wav):
    return wav("noise.wav", 0.3 * np.random.default_rng(3).standard_normal(RATE * 3))


def test_rule_skips_the_quietest_within_the_budget():
    # total 103, budget -20 dB: 1.03 may go; ties are broken by order
    assert skip_mask(np.array([100.0, 1, 1, 1, 0]), ["g"] * 5, -20.0).tolist() == [False, True, False, False, True]


def test_rule_budget_is_per_group_and_beds_count_but_stay():
    e = np.array([100.0, 0.5, 1e-6, 0.5])
    groups = ["a", "a", "b", "a"]
    assert skip_mask(e, groups, -20.0).tolist() == [False, True, False, True]  # b alone keeps its source
    assert skip_mask(e, groups, -20.0, cullable=[True, False, True, True]).tolist() == [False, False, False, True]
    assert skip_mask(np.zeros((2, 3)), ["a", "a"], -40.0).all()  # silence: nothing to render


def test_dry_energy_matches_the_window(wav):
    x = np.random.default_rng(1).standard_normal(10007) * np.linspace(0, 2, 10007)
    a = np.arange(0, 100000, 480)
    for mode, start, end in (("loop", 1234, 90000), ("once", [300, 25000], None)):
        p = {"mode": mode, "fade_in": 0.0, "fade_out": 0.0, "loop_crossfade": 0.0, "loop_phase": "random"}
        g = signals.DryGenerator(x, p, RATE, start, end, "s")
        w = g.window(0, 100480)
        exact = np.array([np.sum(w[i:i + 480] ** 2) for i in a])
        assert g.energy(a, a + 480).sum() == pytest.approx(exact.sum(), rel=1e-4)
        assert np.max(np.abs(g.energy(a, a + 480) - exact)) < 0.05 * exact.max()


def test_culled_render_stays_within_the_budget(make_scene, noise):
    rng = np.random.default_rng(5)
    sources = [{"sample": noise, "ref_distance": 2.0}] + [{"sample": noise} for _ in range(20)]
    pos = [[0, 3, 0]] + [[x, y, 0] for x, y in rng.uniform(40, 200, (20, 2))]
    ref = render.render(make_scene(sources, pos, frame_end=600, settings=OFF)).audio
    for budget, share in ((-40.0, 1.0), (-20.0, 0.5)):
        result = render.render(make_scene(sources, pos, frame_end=600, settings={"cull_db": budget}))
        assert result.culling["rendered_share"] < share
        assert error_db(ref, result.audio) < budget
        assert error_db(ref, result.audio, window=int(0.4 * RATE)) < budget + 1.0


def test_quiet_group_keeps_its_own_budget(make_scene, noise):
    sources = [{"sample": noise, "group": "near"}, {"sample": noise, "group": "far", "gain_db": -60}]
    pos = [[0, 2, 0], [0, 50, 0]]
    result = render.render(make_scene(sources, pos, frame_end=300, settings={"cull_db": -20.0}, ), stems=True)
    ref = render.render(make_scene(sources, pos, frame_end=300, settings=OFF), stems=True)
    assert result.culling["skipped_entirely"] == 0
    assert np.array_equal(result.stems["far"], ref.stems["far"])


def test_resumed_voice_matches_the_full_render(make_scene, noise, click):
    # the one-shot is silent (skipped) for its first chunks, then resumes with a warm-up
    sources = [{"sample": noise}, {"sample": click, "mode": "once", "frame": [250, 400], "gain_db": -6}]
    pos = [[0, 30, 0], [5, 5, 0]]
    on = render.render(make_scene(sources, pos, frame_end=600))
    off = render.render(make_scene(sources, pos, frame_end=600, settings=OFF))
    assert on.culling["rendered_share"] < 1.0
    assert np.max(np.abs(on.audio - off.audio)) < 1e-9


def test_far_sources_are_skipped_before_setup(make_scene, noise):
    sources = [{"sample": noise}] + [{"sample": noise, "id": f"far{i}"} for i in range(3)]
    pos = [[0, 2, 0], [0, 8000, 0], [8000, 0, 0], [-8000, 100, 0]]  # each about -72 dB
    result = render.render(make_scene(sources, pos, frame_end=300))
    assert result.culling["skipped_before_setup"] == 3
    far = [s for s in result.sources if s["id"].startswith("far")]
    assert all(s["culled_s"] == pytest.approx(10.0) and s["audible_frames"] == 0 for s in far)
    assert not any("never audible" in w for w in result.warnings)


def test_one_shot_voices_skip_their_silent_chunks(make_scene, click):
    # doppler 0.5 renders one voice per trigger over the whole shot; culling skips where each is silent
    frames = [30 * k + 1 for k in range(19)]
    sources = [{"sample": click, "mode": "once", "frame": frames, "doppler": 0.5}]
    on = render.render(make_scene(sources, [[0, 20, 0]], frame_end=600))
    off = render.render(make_scene(sources, [[0, 20, 0]], frame_end=600, settings=OFF))
    assert on.culling["rendered_share"] < 0.25
    assert np.max(np.abs(on.audio - off.audio)) < 1e-9


def test_culling_off_reports_nothing(make_scene, noise):
    result = render.render(make_scene([{"sample": noise}], [[0, 5, 0]], settings=OFF))
    assert result.culling is None and "culled_s" not in result.sources[0]


def test_estimate_includes_the_filters(make_scene, noise, monkeypatch):
    # white noise far away (air absorption), behind (rear cue) and at the side (head shadow): the
    # filters remove several dB, which the estimate per block must follow
    from soundstage.engine import cull

    captured = {}
    plan = cull.plan

    def capture(power, groups, spatial, grid, spans, n_chunks, budget_db):
        captured.update(power=power, grid=grid, spans=spans)
        return plan(power, groups, spatial, grid, spans, n_chunks, budget_db)

    monkeypatch.setattr(cull, "plan", capture)
    for pos in ([0, 300, 0], [0, -20, 0], [8, 1, 0]):
        out = render.render(make_scene([{"sample": noise, "mode": "loop"}], [pos], frame_end=150)).audio
        est = cull.block_energy(captured["power"], captured["grid"], captured["spans"])[0]
        n0 = captured["spans"][0][0]
        got = np.array([np.square(out[a - n0:b - n0]).sum() for a, b, _ in captured["spans"]])
        assert np.max(np.abs(10 * np.log10(est[1:-1] / got[1:-1]))) < 1.0
