# E17: where a source at the frame edge is heard, against the lens

**Question.** With `pan_reference = "camera"` (the only mode before this experiment) the engine pans from the direction of a
source relative to the camera ("ears at the camera") and ignores the lens. Where does a source at
the edge of the frame end up in the stereo image for different focal lengths, and how does that
compare with where the viewer sees the edge of the frame on a screen? And does the screen-relative
mode fix it?

## Setup

`e17_lens_and_pan.py`: a 36 mm sensor (Blender's default), a static 1 kHz source 20 m away at the
right edge of the frame (azimuth = half the horizontal field of view), the `amplitude` panner with
the default `sine` law, air absorption off. The R/L level difference is measured on the render; the
phantom image angle it gives on loudspeakers at ±30° (ITU-R BS.775, SMPTE RP 173) follows from the
tangent law, `tan φ = tan 30° · (g_R − g_L)/(g_R + g_L)` ([panning](../models/panning.md)).

The viewer sees the edge of a 16:9 screen at 16.5° from 3 picture heights (the HD reference
position of SMPTE RP 173; BS.775 gives about 33° for the full width of an HDTV screen) and at 30.7°
from 1.5 picture heights (a UHD viewing distance).

## Results

| lens (36 mm sensor) | horizontal field of view | frame edge: azimuth | R/L level (dB) | heard at (±30° speakers) |
|---|---|---|---|---|
| 14 mm | 104.3° | 52.1° | 15.5 | 22.4° |
| 24 mm | 73.7° | 36.9° | 9.8 | 16.4° |
| 35 mm | 54.4° | 27.2° | 6.9 | 12.2° |
| 50 mm | 39.6° | 19.8° | 4.9 | 8.9° |
| 85 mm | 23.9° | 12.0° | 2.9 | 5.4° |
| 135 mm | 15.2° | 7.6° | 1.8 | 3.4° |
| 200 mm | 10.3° | 5.1° | 1.2 | 2.3° |
| 400 mm | 5.2° | 2.6° | 0.6 | 1.2° |

The frame edge is heard where an HD viewer sees it (16.5°) only with a 24 mm lens. With the default
50 mm lens it is heard at 9°, about half way; with a 200 mm lens everything in the frame is heard
within 2.3° of the centre. At 1.5 picture heights the screen edge (30.7°) is at the loudspeakers
themselves, which the engine reaches only for sources at 90°.

## Interpretation

- Two mappings compress the image. The lens maps the frame onto the screen (`x = tan θ / tan(FOV/2)`),
  which the sound does not follow. And the pan law maps the full half circle (±90°) onto the
  loudspeaker base (±30°), so every direction is heard at roughly a third to a half of its angle.
- Audio-visual offsets of about 10–20° are still fused by viewers (ventriloquism; untrained
  listeners tolerate more than trained ones, [survey](../survey.md#camera-lens-and-sound-direction)).
  On a TV at 3 picture heights the offsets here (up to 14° at 200 mm) are within or at that limit;
  on a large screen, or with long lenses and sources at the frame edge, they are not.
- Distance, delay, Doppler and occlusion do not depend on the lens: a zoom changes the picture,
  not where the camera is. Only the direction used for panning is in question.

## Screen-relative panning

The answer from film mixing and MPEG-H ([survey](../survey.md#camera-lens-and-sound-direction)) is
implemented as `pan_reference = "screen"`, now the default ([spec](../../docs/spec/signal-model.md#panning)): the
bake records the frame edges, and the lateral sine is remapped so that the image coordinate `u` of
a source is heard at `atan(u · tan screen_edge_deg)`. The same renders with the default
`screen_edge_deg` of 16.5°, for a source at the frame edge, half way to it (`u = 0.5`, target
8.4°) and off-screen at 60°:

| lens | frame edge heard at | half way heard at | 60° (off-screen) heard at | 60°, camera mode |
|---|---|---|---|---|
| 14 mm | 16.5° | 8.4° | 19.0° | 25.0° |
| 24 mm | 16.5° | 8.4° | 22.0° | 25.0° |
| 35 mm | 16.5° | 8.4° | 23.1° | 25.0° |
| 50 mm | 16.5° | 8.4° | 23.8° | 25.0° |
| 85 mm | 16.5° | 8.4° | 24.4° | 25.0° |
| 135 mm | 16.5° | 8.4° | 24.7° | 25.0° |
| 200 mm | 16.5° | 8.4° | 24.8° | 25.0° |
| 400 mm | 16.5° | 8.4° | 25.0° | 25.0° |

The frame is heard at the same width whatever the lens; off-screen sources keep about the place
they have in camera mode, compressed a little with wide lenses, where the frame takes more of the
front.

## Reproduce

```bash
.venv/bin/python research/experiments/scripts/e17_lens_and_pan.py
```
