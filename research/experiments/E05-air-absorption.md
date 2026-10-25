# E05: air absorption (ISO 9613-1) and its filter

**Questions.** Is the ISO 9613-1 implementation right? Which filter realizes it well enough, and is
the fitted table smooth over distance?

## 1. ISO 9613-1 against ISO 9613-2 Table 2

Output of `e05_air_absorption.py` at the exact band centres (63.1 … 7943 Hz), dB/km (table values
in brackets):

| Climate | 63 Hz | 125 Hz | 250 Hz | 500 Hz | 1 kHz | 2 kHz | 4 kHz | 8 kHz |
|---|---|---|---|---|---|---|---|---|
| 10 °C, 70 % | 0.1 (0.1) | 0.4 (0.4) | 1.0 (1) | 1.9 (1.9) | 3.7 (3.7) | 9.7 (9.7) | 32.8 (32.8) | 116.9 (117) |
| 20 °C, 70 % | 0.1 (0.1) | 0.3 (0.3) | 1.1 (1.1) | 2.8 (2.8) | 5.0 (5) | 9.0 (9) | 22.9 (22.9) | 76.6 (76.6) |
| 30 °C, 70 % | 0.1 (0.1) | 0.3 (0.3) | 1.0 (1) | 3.1 (3.1) | 7.4 (7.4) | 12.7 (12.7) | 23.1 (23.1) | 59.3 (59.3) |
| 15 °C, 20 % | 0.3 (0.3) | 0.6 (0.6) | 1.2 (1.2) | 2.7 (2.7) | 8.2 (8.2) | 28.2 (28.2) | 88.8 (88.8) | 201.8 (202) |
| 15 °C, 50 % | 0.1 (0.1) | 0.5 (0.5) | 1.2 (1.2) | 2.2 (2.2) | 4.2 (4.2) | 10.8 (10.8) | 36.2 (36.2) | 128.6 (129) |
| 15 °C, 80 % | 0.1 (0.1) | 0.3 (0.3) | 1.1 (1.1) | 2.4 (2.4) | 4.2 (4.1) | 8.3 (8.3) | 23.7 (23.7) | 82.8 (82.8) |

Every value matches to the table's rounding (4.2 against 4.1 lies on the rounding boundary). At the
nominal frequencies (4000, 8000 Hz) the formula gives up to 1.2 % more, which is the frequency
difference, not an error.

## 2. Filter realization

Largest error against ISO (20 °C, 50 % RH, 100 Hz–20 kHz) where the loss is below 20 dB, at the
96 kHz emission rate:

| Distance | Spec one-pole | Fit, 1 pole | 2 poles | 3 poles | 4 poles | Engine table (4) | Engine: min. loss above 20 dB region |
|---|---|---|---|---|---|---|---|
| 10 m | 0.2 | 0.04 | 0.03 | 0.03 | 0.03 | 0.04 | – |
| 30 m | 6.1 | 3.92 | 1.34 | 0.13 | 0.10 | 0.09 | – |
| 100 m | 10.8 | 7.21 | 4.21 | 2.73 | 1.85 | 1.89 | 18.5 |
| 300 m | 11.2 | 6.91 | 4.06 | 2.67 | 1.84 | 1.90 | 18.3 |
| 1 km | 11.9 | 5.40 | 3.11 | 2.60 | 2.40 | 2.49 | 17.7 |
| 3 km | 13.4 | 2.60 | 1.31 | 1.20 | 1.16 | 1.05 | 18.8 |

("Spec one-pole": the original spec's one-pole at the 3 dB point of `0.1 dB/m · (f/8 kHz)²`.)

![air absorption](../figures/e05_air_absorption.png)

## 3. Smoothness

Largest response change between neighbouring distances 0.46 % apart, where the loss is below
20 dB: 0.37 dB (at 7 km, 520 Hz). Individual cutoffs may jump where the fit changes how it uses its
poles, but the response does not.

## Conclusion

The implementation is correct; four one-poles fitted per distance stay within about 2.5 dB of ISO
wherever the sound is less than 20 dB down and keep attenuating beyond; the table is smooth. The
original model was off by 6–13 dB from 30 m on ([air absorption](../models/air-absorption.md)).

## Reproduce

```bash
.venv/bin/python research/experiments/scripts/e05_air_absorption.py
```
