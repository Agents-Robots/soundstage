"""Storyboard of ``production`` (README.md): two scenes from the author's Blender animations with the
sound soundstage rendered for them: the race across the swamp, whole; the drone flight around a party
terrace in the city of flying cars, with its music and neon signs."""

from kit.story import Pass, Section, TitlePage

SECTION = Section(
    key="production",
    title="In production",
    title_page=TitlePage(
        title="In production",
        claim="Scenes from two Blender animations, with the sound soundstage rendered for them.",
        code="soundstage render bake/scene.json -o mix.wav",
        listen="six racers crossing a swamp at 612 km/h; music and neon signs around a tower in a city of flying cars.",
    ),
    passes=(
        Pass("race", 1233, "Six racers at 612 km/h, half the speed of sound", "from an animation: the swamp, 11 shots"),
        Pass("metropolis", 810, "Over 2000 flying cars, music on the terraces", "from an animation: 2200 sources"),
    ),
    reference="metropolis",
)
ANIM_FPS = {"race": 30000 / 1001, "metropolis": 30.0}
"""The race runs at 29.97 fps: its 1233 frames are shown at 30 fps and its sound is resampled by
1000/1001 to match (41.143 s become 41.102 s, 1.7 cents higher)."""
GAIN_DB = {"race": 4.0, "metropolis": 2.5}
"""Fixed gains per scene; no normalization. The race's stems sit under the animation's score in its
mix."""
RACE_LIMIT_DBTP = -1.0
"""The race's two flybys stand 10 dB over the rest of the scene; the animation's mix holds them with
its master limiter, the excerpt with soundstage's (``mix.true_peak_limiter``), as the metropolis
render does with ``--limit -1``."""
FADE_S = 0.25
"""Fades at the scenes' cuts: the animations' sound runs on through them."""
END_FADE_S = 1.0
TEXT_S = 9.0
"""Every text of a scene shows in its first seconds only: the scenes build to their ends."""
TEXT_FADE = 12
RACE_CALLOUT = "Passing at 612 km/h, a racer's whine falls to a third"
RENDER_CLAIM_S = 60
METRO_CALLOUT = "27 s of sound, rendered in under a minute on 16 cores"
CALLOUTS = {"race": (RACE_CALLOUT, 1.5, TEXT_S), "metropolis": (METRO_CALLOUT, 1.5, TEXT_S)}
"""Text, and its window in seconds from the scene's start."""

# --- the animations' files ------------------------------------------------------------------------------
# Paths inside each animation's project folder; the folders themselves are machine-specific and named
# in sources.local.toml next to this file (gitignored): [projects] race = "...", metropolis = "...".

RACE_RENDERS = ("out/hq/frames/hq*_swamp_{}/*", "tmp/flamenco/hq*_swamp_{}/*")
"""Where the race's frames are, per render pass of its cut (``{}``), one folder per render named by its
date; each shot is taken from the newest render that has all of its frames."""
RACE_FRAME = "{:06d}.jpg"
RACE_CUT = "data/cut_swamp.json"
"""The animation's cut of the scene: per shot the camera, its length in beats and, where it does not
go on from the shot before, its first race frame."""
RACE_BPM = 140
RACE_SHOTS = (
    # camera, render pass, first race frame, frames (RACE_CUT of 2026-11-14)
    ("a2a_right", 0, 3480, 193),
    ("pan_swamp", 1, 3652, 51),
    ("flyby_swamp", 0, 3719, 128),
    ("a2a_right", 0, 3847, 116),
    ("a2a_front", 0, 3963, 129),
    ("flyby_omega", 0, 4092, 192),
    ("tail_rig", 0, 4284, 90),
    ("a2a_rear", 0, 4374, 129),
    ("between", 0, 4503, 77),
    ("close_left", 0, 4580, 64),
    ("below", 0, 4644, 64),
)
"""The swamp scene shot by shot, as the animation cuts it (``RACE_CUT``): 96 beats at ``RACE_BPM``."""
RACE_MIX = ("out/audio/mix/film_full", 164.5714286)
"""The animation's mix (``<name>.wav``, ``<name>_stem_*.wav``, ``<name>_curves.npz``,
``<name>.recipe.json``) and the scene's start in its time line, in seconds."""
RACE_STEMS = ("engines", "bed")
"""The stems soundstage rendered: the racers (engines, whine, sub) and the air and water. The score,
the radio voices, the cheering recordings and the whooshes are the animation's, not soundstage's."""
SPEECH_DUCK_DB = 4.0
"""The animation's mix steps the engines and the air back by this while the radio speaks; without the
voices that step is undone (``steps.race_sound``)."""
METRO_FRAMES = ("flamenco/scifi_city_drone/merged_2026-10-30/{:06d}.png", 361)
"""Frame file pattern and the animation's frame shown as the pass's first frame (12 s into the drone
flight)."""
RENDERS = {
    # soundstage renders from the animation's own bake, run in its project folder
    "metropolis": [("audio/bake/drone/scene.json", ["--frames", "361-1170", "--set", "master_gain_db=-5",
                                                    "--limit", "-1"])],
}
"""The metropolis render is the animation's own (master gain, limiter at -1 dBTP), music included."""
