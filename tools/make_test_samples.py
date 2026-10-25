"""Generate the test samples in samples/ (run in the repo venv).

Planned output (48 kHz unless stated, float WAV, deterministic):

- ``sine_1k.wav``: 1 kHz sine, 4 s, seamless loop (integer number of periods).
- ``sine_1k_44k1.wav``: same at 44.1 kHz (resampling tests).
- ``click.wav``: single-sample impulse followed by silence, 1 s (onset and delay tests).
- ``noise_pink.wav``: pink noise, 4 s, with a crossfaded seam (filter and loudness tests).
- ``engine_hum.wav``: harmonic hum with slow modulation, 6 s loop (listening tests).
- ``beep.wav``: short 2 kHz tone burst with fades (one-shot listening tests).
- ``ambience_stereo.wav``: decorrelated stereo noise bed (bed source tests).

Usage: ``.venv/bin/python tools/make_test_samples.py [--out samples/]``.
"""
