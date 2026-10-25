# 0005. Output 48 kHz 32-bit float WAV, sample 0 = first frame

- Status: Accepted
- Date: 2026-10-25
- Ticket: —

## Context

The result is placed in DaVinci Resolve next to an image sequence rendered by Blender (often on a render farm). It must
line up frame-exactly without manual nudging, at integer and fractional frame rates, and leave the
final mix (levels, limiting, music) to Fairlight.

## Decision

- WAV, 48 kHz, stereo, **32-bit float** by default; 24-bit PCM with TPDF dither as an option.
- **Sample 0 is the first frame of the shot**, and the file is exactly as long as the shot:
  `round((frame_end − frame_start + 1) · fs · fps_base / fps)` samples. Frame times use Blender's
  `fps / fps_base`, so 23.976 and 29.97 are exact.
- No normalization or limiting by default. Optional stems per group, which sum to the master.

## Alternatives considered

- **24-bit PCM default**: universal, but clips if the sum exceeds 0 dBFS before the final mix, so
  the engine would have to limit or normalize, which is Fairlight's job.
- **Muxing audio into the video**: Resolve separates them anyway; the image sequence workflow has
  no video file to mux into except for previews (offered as `soundstage preview`).
- **BWF with timecode**: would allow automatic placement by timecode, but the image sequences
  carry no matching timecode today. Possible later (roadmap Phase 4).
- **44.1 kHz**: music standard, not video; Resolve projects default to 48 kHz.
- **Ambisonics or ADM/Atmos**: stereo is the target (ADR [0007](0007-stereo-ear-model.md)).

## Consequences

- Placement in Resolve is: put the WAV at the clip's first frame.
- Files are about 23 MB per stereo minute (float32), small compared with the image sequences.
- Peaks above 0 dBFS in float files are legal; the report shows them so PCM renders or deliveries
  can be checked.
