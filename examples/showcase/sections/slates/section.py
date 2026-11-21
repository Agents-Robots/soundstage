"""Storyboard of ``slates`` (README.md): text cards on black for the trailer, silent. Each card is a
pass; a cut takes the cards it needs."""

from kit.story import Pass, Section

SECTION = Section(
    key="slates",
    title="Slates",
    title_frames=0,
    passes=(
        Pass("not_recorded", 66, ""),
        Pass("title", 75, ""),
        Pass("thousands", 66, ""),
    ),
    loudness_reported_only=True,
)
CARDS = {
    # pass: lines (text, cap height, colour, bold); the first line's baseline at ``top``
    "not_recorded": ([("This sound was not recorded.", 0.06, "text", True)], 0.53),
    "title": ([("SoundStage", 0.11, "text", True), ("Spatial sound, computed from your Blender scenes", 0.036,
                                                     "muted", False)], 0.50),
    "thousands": ([("Ten thousand cars.", 0.06, "text", True), ("Twenty thousand sources.", 0.06, "accent", True)],
                  0.47),
}
LINE_GAP = 1.9
"""Baseline to baseline, in cap heights of the line below."""
FADE = 6
"""Each card fades in from black and out to black over this many frames."""
