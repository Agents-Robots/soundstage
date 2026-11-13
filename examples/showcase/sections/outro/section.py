"""Storyboard of ``outro`` (README.md): the end card, silent."""

from kit.story import Pass, Section

SECTION = Section(
    key="outro",
    title="End card",
    title_frames=0,
    passes=(Pass("card", 240, ""),),
    loudness_reported_only=True,
)
TAGLINE = "Offline spatial sound for Blender animations"
STEPS = (
    ("tag", 'tag.add_sound(car, "engine.wav")'),
    ("bake", "soundstage bake scene.blend --out bake/"),
    ("render", "soundstage render bake/scene.json -o mix.wav"),
)
STATEMENT = "Every sound in this video was rendered by soundstage from the Blender scenes shown."
ALSO = ("Stems per group", "loudness normalization", "true-peak limiter", "solo and mute",
        "reverb presets and impulse responses")
SEPARATOR = " · "
NO_RECORDINGS = "All sounds synthesized"


def credits(sources_toml: str) -> str:
    """The credits line from the text of sounds/sources.toml: the recordings' authors in order of first
    appearance (R3)."""
    import tomllib
    authors = []
    for r in tomllib.loads(sources_toml).get("recording", []):
        if r["author"] not in authors:
            authors.append(r["author"])
    if not authors:
        return NO_RECORDINGS
    return "Recorded sounds: " + ", ".join(authors) + "; all other sounds synthesized"
