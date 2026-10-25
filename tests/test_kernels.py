"""numba kernels against their reference implementations, chunking, and interpolation accuracy."""

import numpy as np
import pytest

from soundstage.engine import kernels as k

rng = np.random.default_rng(7)


def test_optimal2x_and_hermite_match_references():
    buf = rng.standard_normal(400)
    pos = rng.uniform(-5, 405, 2000)  # includes reads past both ends (zeros outside)
    assert np.allclose(k.read_optimal2x(buf, pos, np.empty(len(pos))), k.ref_read_optimal2x(buf, pos), atol=1e-12)
    assert np.allclose(k.read_hermite4(buf, pos, np.empty(len(pos))), k.ref_read_hermite4(buf, pos), atol=1e-12)


def test_hermite_passes_through_samples():
    buf = rng.standard_normal(50)
    pos = np.arange(2, 48, dtype=float)
    assert np.allclose(k.read_hermite4(buf, pos, np.empty(len(pos))), buf[2:48])


def test_sinc_matches_direct_evaluation():
    buf = rng.standard_normal(300)
    pos = rng.uniform(40, 260, 200)
    rate = rng.uniform(0.5, 3.0, 200)
    table = k.sinc_table()
    got = k.read_sinc(buf, pos, rate, table, k.SINC_ZERO_CROSSINGS, k.SINC_TABLE_PER_CROSSING, k.SINC_CUTOFF,
                      np.empty(len(pos)))
    assert np.allclose(got, k.ref_read_sinc(buf, pos, rate), atol=2e-5)


def _sine_read_error_db(read, fs, f, oversample, prefilter=None):
    """RMS error (dB re. signal) reading a sine at fractional positions with a varying rate."""
    fe = fs * oversample
    n = np.arange(int(0.2 * fe))
    buf = np.sin(2 * np.pi * f * n / fe)
    if prefilter is not None:
        buf = np.convolve(buf, prefilter, mode="same")
    t_out = 0.05 + np.arange(int(0.1 * fs)) / fs * (1 + 0.05 * np.sin(np.arange(int(0.1 * fs)) / 300))
    pos = t_out * fe
    y = read(buf, pos)
    err = y - np.sin(2 * np.pi * f * t_out)
    return 20 * np.log10(np.sqrt(np.mean(err ** 2)) / np.sqrt(0.5))


@pytest.mark.parametrize("f", [1000, 10000, 18000])
def test_optimal2x_with_preemphasis_reads_oversampled_input_accurately(f):
    pre = k.optimal2x_preemphasis()
    assert len(pre) == k.OPT2X_PREEMPHASIS_TAPS and np.allclose(pre, pre[::-1])
    opt = _sine_read_error_db(lambda b, p: k.read_optimal2x(b, p, np.empty(len(p))), 48000, f, 2, pre)
    assert opt < -85, opt


def test_hermite_on_plain_input_is_poor_at_high_frequencies():
    her = _sine_read_error_db(lambda b, p: k.read_hermite4(b, p, np.empty(len(p))), 48000, 10000, 1)
    assert her > -30, her  # why the standard path oversamples (research/experiments/E03-interpolators.md)


def test_sinc_lowers_cutoff_when_reading_fast():
    fs = 48000
    n = np.arange(fs)
    buf = np.sin(2 * np.pi * 18000 * n / fs)  # 18 kHz: read at rate 2 it would alias to 12 kHz
    pos = 2000 + np.arange(4000) * 2.0
    table = k.sinc_table()
    fast = k.read_sinc(buf, pos, np.full(len(pos), 2.0), table, k.SINC_ZERO_CROSSINGS, k.SINC_TABLE_PER_CROSSING,
                       k.SINC_CUTOFF, np.empty(len(pos)))
    slow = k.read_sinc(buf, 2000 + np.arange(4000) * 1.0, np.ones(4000), table, k.SINC_ZERO_CROSSINGS,
                       k.SINC_TABLE_PER_CROSSING, k.SINC_CUTOFF, np.empty(4000))
    assert np.sqrt(np.mean(fast ** 2)) < 1e-3  # suppressed, not aliased
    assert np.sqrt(np.mean(slow ** 2)) == pytest.approx(np.sqrt(0.5), rel=0.01)  # passband at rate 1


def test_onepole_cascade_matches_reference_and_chunks():
    x = rng.standard_normal(1000)
    gains = rng.uniform(0.05, 0.95, (1000, 3))
    whole = k.onepole_cascade(x, gains, np.zeros(3), np.empty(1000))
    assert np.allclose(whole, k.ref_onepole_cascade(x, gains, np.zeros(3)), atol=1e-12)
    state = np.zeros(3)
    parts = [k.onepole_cascade(x[a:b], gains[a:b], state, np.empty(b - a)) for a, b in ((0, 333), (333, 1000))]
    assert np.array_equal(np.concatenate(parts), whole)


def test_onepole_gain_one_passes_signal():
    x = rng.standard_normal(100)
    assert np.allclose(k.onepole_cascade(x, np.ones((100, 2)), np.zeros(2), np.empty(100)), x)


def test_first_order_matches_reference_and_chunks():
    x = rng.standard_normal(500)
    b0, b1 = rng.uniform(0.5, 1.5, 500), rng.uniform(-0.5, 0.5, 500)
    whole = k.first_order(x, b0, b1, -0.6, np.zeros(2), np.empty(500))
    assert np.allclose(whole, k.ref_first_order(x, b0, b1, -0.6, np.zeros(2)), atol=1e-12)
    state = np.zeros(2)
    parts = [k.first_order(x[a:b], b0[a:b], b1[a:b], -0.6, state, np.empty(b - a)) for a, b in ((0, 100), (100, 500))]
    assert np.array_equal(np.concatenate(parts), whole)
