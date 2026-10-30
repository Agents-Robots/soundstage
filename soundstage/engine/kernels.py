"""Per-sample kernels (numba) and their reference implementations.

Everything that loops over samples lives here (ADR 0002, ADR 0009): fractional-delay reads and
recursive filters with per-sample parameters. Each kernel is ``numba.njit(cache=True, nogil=True)``
so source renderers can run in threads, and has a plain numpy/Python reference (``ref_*``) written
independently, which the tests compare against. No fastmath: results must be bit-identical between
runs (NFR-2).

Read kernels take a buffer and fractional positions in buffer samples; samples outside the buffer
count as zero. Filter kernels update their ``state`` array in place, so calling them chunk by chunk
equals one call over the whole signal.

Spec: docs/spec/signal-model.md (fractional-delay read, filters).
"""

from __future__ import annotations

import functools
import math

import numba
import numpy as np

_jit = numba.njit(cache=True, nogil=True)

# Niemitalo, "Polynomial Interpolators for High-Quality Resampling of Oversampled Audio" (2001):
# optimal 2x, 6-point, 5th-order, z-form. Rows c0..c5; columns pair (y[1], y[0]), (y[2], y[-1]),
# (y[3], y[-2]); even rows use sums, odd rows differences of the pair.
OPT2X_6P5O = np.array([
    [0.40513396007145713, 0.09251794438424393, 0.00234806603570670],
    [0.28342806338906690, 0.21703277024054901, 0.01309294748731515],
    [-0.191337682540351941, 0.16187844487943592, 0.02946017143111912],
    [-0.16471626190554542, -0.00154547203542499, 0.03399271444851909],
    [0.03845798729588149, -0.05712936104242644, 0.01866750929921070],
    [0.04317950185225609, -0.01802814255926417, 0.00152170021558204],
])

OPT2X_PREEMPHASIS_TAPS = 63
"""The optimal-2x polynomial assumes its passband droop (-0.3 dB at 5 kHz, -1.2 dB at 10 kHz, -4.9 dB at
20 kHz for 48 kHz audio) is corrected by a pre-emphasis in the oversampling stage; 63 taps bring the
read error below -90 dB up to 18 kHz (research/experiments/E04-preemphasis.md)."""

SINC_ZERO_CROSSINGS = 16
SINC_TABLE_PER_CROSSING = 512
SINC_KAISER_BETA = 9.0
SINC_CUTOFF = 0.92  # of the Nyquist frequency of the output, at rate <= 1


@_jit
def _at(buf, k):
    if k < 0 or k >= buf.shape[0]:
        return 0.0
    return buf[k]


@_jit
def _optimal2x_at(buf, p, c):
    k = math.floor(p)
    z = p - k - 0.5
    ym2, ym1, y0 = _at(buf, k - 2), _at(buf, k - 1), _at(buf, k)
    y1, y2, y3 = _at(buf, k + 1), _at(buf, k + 2), _at(buf, k + 3)
    e1, o1 = y1 + y0, y1 - y0
    e2, o2 = y2 + ym1, y2 - ym1
    e3, o3 = y3 + ym2, y3 - ym2
    c0 = e1 * c[0, 0] + e2 * c[0, 1] + e3 * c[0, 2]
    c1 = o1 * c[1, 0] + o2 * c[1, 1] + o3 * c[1, 2]
    c2 = e1 * c[2, 0] + e2 * c[2, 1] + e3 * c[2, 2]
    c3 = o1 * c[3, 0] + o2 * c[3, 1] + o3 * c[3, 2]
    c4 = e1 * c[4, 0] + e2 * c[4, 1] + e3 * c[4, 2]
    c5 = o1 * c[5, 0] + o2 * c[5, 1] + o3 * c[5, 2]
    return ((((c5 * z + c4) * z + c3) * z + c2) * z + c1) * z + c0


@_jit
def _optimal2x_inside(buf, p, c):
    """``_optimal2x_at`` for positions with all six taps inside the buffer (no bounds checks)."""
    k = int(math.floor(p))
    z = p - k - 0.5
    ym2, ym1, y0, y1, y2, y3 = buf[k - 2], buf[k - 1], buf[k], buf[k + 1], buf[k + 2], buf[k + 3]
    e1, o1 = y1 + y0, y1 - y0
    e2, o2 = y2 + ym1, y2 - ym1
    e3, o3 = y3 + ym2, y3 - ym2
    c0 = e1 * c[0, 0] + e2 * c[0, 1] + e3 * c[0, 2]
    c1 = o1 * c[1, 0] + o2 * c[1, 1] + o3 * c[1, 2]
    c2 = e1 * c[2, 0] + e2 * c[2, 1] + e3 * c[2, 2]
    c3 = o1 * c[3, 0] + o2 * c[3, 1] + o3 * c[3, 2]
    c4 = e1 * c[4, 0] + e2 * c[4, 1] + e3 * c[4, 2]
    c5 = o1 * c[5, 0] + o2 * c[5, 1] + o3 * c[5, 2]
    return ((((c5 * z + c4) * z + c3) * z + c2) * z + c1) * z + c0


@_jit
def read_optimal2x(buf, pos, out):
    """6-point, 5th-order optimal-2x polynomial read of a 2x-oversampled buffer."""
    c = OPT2X_6P5O
    for i in range(pos.shape[0]):
        out[i] = _optimal2x_at(buf, pos[i], c)
    return out


@_jit
def _far_range(buf, period, offset, origin, pitch, phase, e_ctl, gl, gr, gs, lo, wts, n_bands, ctl_start, step, a,
               i0, i1, buses, send, peaks, bus, w_start, w_step):
    """Samples [i0, i1) of one far voice (see ``far_mix``)."""
    c = OPT2X_6P5O
    count = e_ctl.shape[0]
    i = i0
    while i < i1:
        k = min(max(int(math.floor((a + i - ctl_start) / step)), 0), count - 2)
        end = min(i1, ctl_start + (k + 1) * step - a)
        if end <= i:
            end = i1
        # the buses this interval touches: two bands x (open, occluded) at each end, merged
        m = 0
        for side in range(2):
            kk = k + side
            for q in range(4):
                bb = lo[kk] + (q & 1) + (n_bands if q >= 2 else 0)
                wv = wts[kk, q]
                found = -1
                for r in range(m):
                    if bus[r] == bb:
                        found = r
                if found < 0:
                    bus[m] = bb
                    w_start[m] = 0.0
                    w_step[m] = 0.0
                    found = m
                    m += 1
                if side == 0:
                    w_start[found] += wv
                else:
                    w_step[found] += wv  # end value for now
        mm = 0
        for r in range(m):
            if w_start[r] != 0.0 or w_step[r] != 0.0:
                bus[mm], w_start[mm], w_step[mm] = bus[r], w_start[r], w_step[r]
                mm += 1
        m = mm
        has_send = gs[k] != 0.0 or gs[k + 1] != 0.0
        if m == 0 and not has_send:
            i = end
            continue
        f0 = (a + i - ctl_start) / step - k
        inv = 1.0 / step
        for r in range(m):
            w_end = w_step[r]
            w_step[r] = (w_end - w_start[r]) * inv
            w_start[r] = w_start[r] + (w_end - w_start[r]) * f0
        de = (e_ctl[k + 1] - e_ctl[k]) * inv
        e = e_ctl[k] + (e_ctl[k + 1] - e_ctl[k]) * f0
        dl, dr, ds = (gl[k + 1] - gl[k]) * inv, (gr[k + 1] - gr[k]) * inv, (gs[k + 1] - gs[k]) * inv
        vl, vr, vs = gl[k] + (gl[k + 1] - gl[k]) * f0, gr[k] + (gr[k + 1] - gr[k]) * f0, gs[k] + (gs[k + 1] - gs[k]) * f0
        u = (e - origin) * pitch + phase
        du = de * pitch
        if period > 0:
            u = u - period * math.floor(u / period)
        peak = peaks[k]
        size = buf.shape[0]
        for j in range(i, end):
            if period > 0:
                x = _optimal2x_inside(buf, u + offset, c)  # the padding keeps every tap inside
            elif 2.0 <= u < size - 4.0:
                x = _optimal2x_inside(buf, u, c)
            elif -4.0 < u < size + 3.0:
                x = _optimal2x_at(buf, u, c)
            else:
                x = 0.0
            if has_send:
                send[j] += x * vs
            if m > 0:
                xl, xr = x * vl, x * vr
                for r in range(m):
                    bb = bus[r]
                    buses[bb, j, 0] += xl * w_start[r]
                    buses[bb, j, 1] += xr * w_start[r]
                    w_start[r] += w_step[r]
                peak = max(peak, abs(xl), abs(xr))
            u += du
            if period > 0:
                while u >= period:
                    u -= period
                while u < 0.0:
                    u += period
            vl += dl
            vr += dr
            vs += ds
        peaks[k] = peak
        i = end


@_jit
def far_mix(bufs, buf_start, buf_len, period, offset, origin, pitch, phase, e_ctl, gl, gr, gs, lo, wts, n_bands,
            ctl_start, step, a, block, buses, send, peaks):
    """Far-field voices added into ``buses`` (n_bus, n, 2) and ``send`` (n,) over output samples
    [a, a + n), in blocks of ``block`` samples (every voice per block, so the buses stay in cache).

    Per voice v: its buffer ``bufs[buf_start[v]: buf_start[v] + buf_len[v]]``; control values every
    ``step`` output samples from ``ctl_start`` (linear in between): emission index ``e_ctl[v]``,
    gains ``gl``, ``gr``, ``gs``, the lower distance band ``lo[v]`` and the weights ``wts[v]``
    (count, 4) of the buses lo, lo + 1 (open) and n_bands + lo, n_bands + lo + 1 (occluded).
    Buffer position at emission index e: ``u = (e - origin) * pitch + phase``; a loop
    (``period`` > 0) reads ``offset + (u mod period)`` from a buffer padded with the cycle's ends, a
    one-shot reads ``u`` directly (zero outside). ``peaks[v]`` (count,) gets the largest
    |gain * x| per interval (left or right), before the buses' filters."""
    n = buses.shape[1]
    bus = np.empty(8, np.int64)
    w_start = np.empty(8)
    w_step = np.empty(8)
    for b0 in range(0, n, block):
        b1 = min(n, b0 + block)
        for v in range(e_ctl.shape[0]):
            buf = bufs[buf_start[v]: buf_start[v] + buf_len[v]]
            _far_range(buf, period[v], offset[v], origin[v], pitch[v], phase[v], e_ctl[v], gl[v], gr[v], gs[v],
                       lo[v], wts[v], n_bands, ctl_start, step, a, b0, b1, buses, send, peaks[v], bus, w_start,
                       w_step)


@_jit
def read_hermite4(buf, pos, out):
    """4-point, 3rd-order Hermite (Catmull-Rom) read (reference quality only)."""
    for i in range(pos.shape[0]):
        p = pos[i]
        k = math.floor(p)
        x = p - k
        ym1, y0, y1, y2 = _at(buf, k - 1), _at(buf, k), _at(buf, k + 1), _at(buf, k + 2)
        c1 = 0.5 * (y1 - ym1)
        c2 = ym1 - 2.5 * y0 + 2.0 * y1 - 0.5 * y2
        c3 = 0.5 * (y2 - ym1) + 1.5 * (y0 - y1)
        out[i] = ((c3 * x + c2) * x + c1) * x + y0
    return out


@functools.lru_cache(maxsize=4)
def optimal2x_preemphasis(taps: int = OPT2X_PREEMPHASIS_TAPS) -> np.ndarray:
    """Symmetric FIR (at the 2x rate) that flattens the optimal-2x read up to 0.47 of the 1x rate.

    Least-squares fit of ``FIR(f) * H(f) = 1`` on 0-0.234 fe (fe = 2x rate), where ``H`` is the
    Fourier transform of the interpolator's continuous impulse response; above 0.266 fe (no content
    after 2x oversampling) the FIR is only kept bounded.
    """
    half = (taps - 1) // 2
    step = 1.0 / 512
    impulse = np.zeros(41)
    impulse[20] = 1.0
    t = np.arange(16.0, 24.0, step)
    h = read_optimal2x(impulse, t, np.empty(len(t)))
    t = t - 20.0

    def response(f):  # f in units of fe; real because h is symmetric
        return (h[None, :] * np.cos(2 * np.pi * np.outer(f, t))).sum(axis=1) * step

    def basis(f):
        return np.hstack([np.ones((len(f), 1)), 2 * np.cos(2 * np.pi * np.outer(f, np.arange(1, half + 1)))])

    passband, stopband = np.linspace(0, 0.234, 600), np.linspace(0.266, 0.5, 300)
    weight = 0.05
    a = np.vstack([basis(passband) * response(passband)[:, None], weight * basis(stopband)])
    b = np.concatenate([np.ones(len(passband)), np.full(len(stopband), weight / response(np.array([0.25]))[0])])
    c = np.linalg.lstsq(a, b, rcond=None)[0]
    return np.concatenate([c[:0:-1], c])


def sinc_table(zero_crossings: int = SINC_ZERO_CROSSINGS, per_crossing: int = SINC_TABLE_PER_CROSSING,
               beta: float = SINC_KAISER_BETA) -> np.ndarray:
    """Right wing of a Kaiser-windowed sinc, sampled ``per_crossing`` times per zero crossing."""
    x = np.arange(zero_crossings * per_crossing + 2) / per_crossing
    u = np.clip(x / zero_crossings, 0.0, 1.0)
    return np.sinc(x) * np.i0(beta * np.sqrt(1.0 - u * u)) / np.i0(beta)


@_jit
def read_sinc(buf, pos, rate, table, zero_crossings, per_crossing, cutoff, out):
    """Windowed-sinc read; the cutoff falls to ``cutoff / rate`` when reading faster than real time."""
    nz = float(zero_crossings)
    for i in range(pos.shape[0]):
        p = pos[i]
        s = cutoff * min(1.0, 1.0 / rate[i])
        half = nz / s
        k0 = math.ceil(p - half)
        k1 = math.floor(p + half)
        acc = 0.0
        for k in range(k0, k1 + 1):
            if k < 0 or k >= buf.shape[0]:
                continue
            x = abs(p - k) * s * per_crossing
            j = int(x)
            if j + 1 >= table.shape[0]:
                continue
            f = x - j
            acc += buf[k] * (table[j] + f * (table[j + 1] - table[j]))
        out[i] = acc * s
    return out


@_jit
def onepole_cascade(x, gains, state, out):
    """Cascade of TPT one-pole low-passes; ``gains`` (n, P) holds G = g/(1+g) per sample and pole."""
    n_poles = gains.shape[1]
    for i in range(x.shape[0]):
        v = x[i]
        for j in range(n_poles):
            u = gains[i, j] * (v - state[j])
            y = u + state[j]
            state[j] = y + u
            v = y
        out[i] = v
    return out


@_jit
def first_order(x, b0, b1, a1, state, out):
    """y[n] = b0[n] x[n] + b1[n] x[n-1] - a1 y[n-1]; ``state`` = [x[n-1], y[n-1]]."""
    x1, y1 = state[0], state[1]
    for i in range(x.shape[0]):
        y = b0[i] * x[i] + b1[i] * x1 - a1 * y1
        x1, y1 = x[i], y
        out[i] = y
    state[0], state[1] = x1, y1
    return out


@_jit
def control_linear(values, jump, start, step, a, out):
    """Linear interpolation of control values to samples a, a+1, ...; never across a jump."""
    last = values.shape[0] - 2
    for i in range(out.shape[0]):
        u = (a + i - start) / step
        k = min(max(int(math.floor(u)), 0), last)
        f = min(max(u - k, 0.0), 1.0)
        if jump[k + 1]:
            f = 1.0
        out[i] = values[k] * (1.0 - f) + values[k + 1] * f
    return out


@_jit
def control_cubic(values, jump, start, step, a, out):
    """Catmull-Rom interpolation of control values to samples; neighbours never across a jump."""
    last = values.shape[0] - 1
    for i in range(out.shape[0]):
        u = (a + i - start) / step
        k = min(max(int(math.floor(u)), 0), last - 1)
        x = min(max(u - k, 0.0), 1.0)
        y0, y1 = values[k], values[k + 1]
        if jump[k + 1]:
            out[i] = y1
            continue
        ym1 = y0 if (k == 0 or jump[k]) else values[k - 1]
        y2 = y1 if (k + 2 > last or jump[k + 2]) else values[k + 2]
        c1 = 0.5 * (y1 - ym1)
        c2 = ym1 - 2.5 * y0 + 2.0 * y1 - 0.5 * y2
        c3 = 0.5 * (y2 - ym1) + 1.5 * (y0 - y1)
        out[i] = ((c3 * x + c2) * x + c1) * x + y0
    return out


@_jit
def onepole_cascade_track(x, a, rate, times, gains, state, out):
    """TPT one-pole cascade whose gains (n_ctl, P) are given at increasing ``times`` (s) and
    interpolated linearly at the sample times (a + i) / rate."""
    n, n_poles = times.shape[0], gains.shape[1]
    j = 0
    for i in range(x.shape[0]):
        tt = (a + i) / rate
        if tt <= times[0]:
            j, f = 0, 0.0
        elif tt >= times[n - 1]:
            j, f = n - 2, 1.0
        else:
            if times[j] > tt:
                j = 0
            while times[j + 1] < tt:
                j += 1
            w = times[j + 1] - times[j]
            f = 0.0 if w <= 0 else (tt - times[j]) / w
        v = x[i]
        for p in range(n_poles):
            g = gains[j, p] + (gains[j + 1, p] - gains[j, p]) * f
            u = g * (v - state[p])
            y = u + state[p]
            state[p] = y + u
            v = y
        out[i] = v
    return out


@_jit
def rear_shelf_track(x, a, rate, times, weight, gain, state, out):
    """y = x + w (LP(x) - x) with a TPT one-pole LP (fixed ``gain``) and w interpolated at
    the sample times from ``weight`` given at increasing ``times``."""
    n = times.shape[0]
    j = 0
    s = state[0]
    for i in range(x.shape[0]):
        tt = (a + i) / rate
        if tt <= times[0]:
            w = weight[0]
        elif tt >= times[n - 1]:
            w = weight[n - 1]
        else:
            if times[j] > tt:
                j = 0
            while times[j + 1] < tt:
                j += 1
            d = times[j + 1] - times[j]
            w = weight[j] if d <= 0 else weight[j] + (weight[j + 1] - weight[j]) * (tt - times[j]) / d
        u = gain * (x[i] - s)
        y = u + s
        s = y + u
        out[i] = x[i] + w * (y - x[i])
    state[0] = s
    return out


@_jit
def follow(x, down, up, out):
    """One-pole follower with separate coefficients for falling (``down``) and rising (``up``) input."""
    y = x[0]
    for i in range(x.shape[0]):
        c = down if x[i] < y else up
        y = y + (x[i] - y) * (1.0 - c)
        out[i] = y
    return out


def warmup() -> None:
    """Compile (or load from cache) every kernel in the calling thread, before threads use them."""
    buf, pos, one = np.zeros(16), np.full(2, 8.0), np.ones(2)
    read_optimal2x(buf, pos, np.empty(2))
    far_mix(buf, np.zeros(1, np.int64), np.full(1, 16, np.int64), np.full(1, 8.0), np.full(1, 4.0), np.zeros(1),
            np.ones(1), np.zeros(1), np.zeros((1, 2)), np.ones((1, 2)), np.ones((1, 2)), np.ones((1, 2)),
            np.zeros((1, 2), np.int64), np.ones((1, 2, 4)), 2, 0, 48, 0, 1024, np.zeros((4, 2, 2)), np.zeros(2),
            np.zeros((1, 2)))
    read_hermite4(buf, pos, np.empty(2))
    read_sinc(buf, pos, one, sinc_table(2, 4), 2, 4, SINC_CUTOFF, np.empty(2))
    onepole_cascade(buf[:2], np.ones((2, 1)), np.zeros(1), np.empty(2))
    first_order(buf[:2], one, one, 0.0, np.zeros(2), np.empty(2))
    flags = np.zeros(4, dtype=np.uint8)
    control_linear(buf[:2], flags, 0, 48, 0, np.empty(2))
    control_cubic(buf[:2], flags, 0, 48, 0, np.empty(2))
    onepole_cascade_track(buf[:2], 0, 48000, np.arange(2.0), np.ones((2, 1)), np.zeros(1), np.empty(2))
    rear_shelf_track(buf[:2], 0, 48000, np.arange(2.0), one, 0.5, np.zeros(1), np.empty(2))
    follow(one, 0.5, 0.5, np.empty(2))


# ---------------------------------------------------------------- reference implementations


def _taps(buf: np.ndarray, idx: np.ndarray) -> np.ndarray:
    padded = np.concatenate([np.zeros(1), buf, np.zeros(1)])
    return padded[np.clip(idx + 1, 0, len(buf) + 1)]


def ref_read_optimal2x(buf: np.ndarray, pos: np.ndarray) -> np.ndarray:
    k = np.floor(pos).astype(np.int64)
    z = pos - k - 0.5
    y = {d: _taps(buf, k + d) for d in range(-2, 4)}
    pairs = [(y[1], y[0]), (y[2], y[-1]), (y[3], y[-2])]
    coeffs = []
    for row in range(6):
        terms = [(a + b) if row % 2 == 0 else (a - b) for a, b in pairs]
        coeffs.append(sum(c * term for c, term in zip(OPT2X_6P5O[row], terms)))
    return np.polyval(coeffs[::-1], z)


def ref_far_mix(bufs, buf_start, buf_len, period, offset, origin, pitch, phase, e_ctl, gl, gr, gs, lo, wts,
                n_bands: int, ctl_start: int, step: int, a: int, n: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``far_mix`` per output sample with numpy: control values interpolated at every sample, the
    weights summed per bus at the control points. Returns buses (2 n_bands, n, 2), send and peaks."""
    count = e_ctl.shape[1]
    buses, send, peaks = np.zeros((2 * n_bands, n, 2)), np.zeros(n), np.zeros(e_ctl.shape)
    fpos = (a + np.arange(n) - ctl_start) / step
    k = np.clip(np.floor(fpos).astype(np.int64), 0, count - 2)
    f = fpos - k
    for v in range(len(e_ctl)):
        def lerp(x):
            return x[k] + (x[k + 1] - x[k]) * f
        buf = bufs[buf_start[v]: buf_start[v] + buf_len[v]]
        u = (lerp(e_ctl[v]) - origin[v]) * pitch[v] + phase[v]
        x = ref_read_optimal2x(buf, offset[v] + np.mod(u, period[v]) if period[v] > 0 else u)
        send += x * lerp(gs[v])
        w = np.zeros((2 * n_bands, count))
        for q in range(4):
            np.add.at(w, (lo[v] + (q & 1) + (n_bands if q >= 2 else 0), np.arange(count)), wts[v][:, q])
        wb = w[:, k] + (w[:, k + 1] - w[:, k]) * f
        xl, xr = x * lerp(gl[v]), x * lerp(gr[v])
        buses[:, :, 0] += xl * wb
        buses[:, :, 1] += xr * wb
        on = (w[:, k] != 0).any(axis=0) | (w[:, k + 1] != 0).any(axis=0)
        np.maximum.at(peaks[v], k[on], np.maximum(np.abs(xl), np.abs(xr))[on])
    return buses, send, peaks


def ref_read_hermite4(buf: np.ndarray, pos: np.ndarray) -> np.ndarray:
    k = np.floor(pos).astype(np.int64)
    x = pos - k
    ym1, y0, y1, y2 = (_taps(buf, k + d) for d in (-1, 0, 1, 2))
    return (y0 + 0.5 * x * (y1 - ym1 + x * (2 * ym1 - 5 * y0 + 4 * y1 - y2 + x * (3 * (y0 - y1) + y2 - ym1))))


def ref_read_sinc(buf: np.ndarray, pos: np.ndarray, rate: np.ndarray, zero_crossings: int = SINC_ZERO_CROSSINGS,
                  beta: float = SINC_KAISER_BETA, cutoff: float = SINC_CUTOFF) -> np.ndarray:
    """Direct evaluation of the windowed sinc (no table)."""
    out = np.zeros(len(pos))
    for i, (p, r) in enumerate(zip(pos, rate)):
        s = cutoff * min(1.0, 1.0 / r)
        k = np.arange(int(np.ceil(p - zero_crossings / s)), int(np.floor(p + zero_crossings / s)) + 1)
        k = k[(k >= 0) & (k < len(buf))]
        x = (p - k) * s
        u = np.clip(np.abs(x) / zero_crossings, 0.0, 1.0)
        w = np.i0(beta * np.sqrt(1.0 - u * u)) / np.i0(beta)
        out[i] = s * np.sum(buf[k] * np.sinc(x) * w)
    return out


def ref_onepole_cascade(x: np.ndarray, gains: np.ndarray, state: np.ndarray) -> np.ndarray:
    """Same recursion written as the bilinear-transform low-pass per pole, sample by sample."""
    state = state.copy()
    out = np.empty(len(x))
    for i, v in enumerate(x):
        for j in range(gains.shape[1]):
            g = gains[i, j] / (1.0 - gains[i, j])  # back from G to g = tan(pi fc / fs)
            y = (g * v + state[j]) / (1.0 + g)
            state[j] = 2.0 * y - state[j]
            v = y
        out[i] = v
    return out


def ref_first_order(x: np.ndarray, b0: np.ndarray, b1: np.ndarray, a1: float, state: np.ndarray) -> np.ndarray:
    out = np.empty(len(x))
    xp, yp = state
    for i in range(len(x)):
        out[i] = b0[i] * x[i] + b1[i] * xp - a1 * yp
        xp, yp = x[i], out[i]
    return out
