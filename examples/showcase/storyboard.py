"""Storyboard of the feature showcase: chapters, passes, labels, timing and render settings.

The one description that both the picture (``build.py``, in Blender) and the sound (``audio.py``,
in the venv) read, so they cannot drift apart. Stdlib only.

A chapter is a title card followed by passes. A pass shows the same action again with one thing
changed; it has its own label, its own sound entries (ids ``<chapter>.<pass>.<name>``) and, where
the change is a scene setting, the settings its render uses (``soundstage render --set``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

FPS = 30
FRAME_START = 1
RESOLUTION = (1920, 1080)
MASTER_GAIN_DB = 0.0
"""One gain for every pass render; no normalization or limiter, which would even out the level
differences the passes show."""

REAR_OFF = {"rear_gain_db": 0.0, "rear_cutoff_hz": 20000.0}


@dataclass(frozen=True)
class Pass:
    key: str
    label: str
    seconds: float
    settings: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Chapter:
    key: str
    title: str
    subtitle: str
    passes: tuple[Pass, ...] = ()
    title_seconds: float = 2.5


CHAPTERS = (
    Chapter("intro", "SoundStage", "Spatial sound for Blender animations: feature showcase\nUse headphones",
            title_seconds=4.0),
    Chapter("sources", "1  Sound sources", "Loops, one-shots, pitch and non-spatial beds", (
        Pass("loop", "A loop with a start and an end, faded in and out", 6.0),
        Pass("once", "One-shots: one trigger per contact", 5.0),
        Pass("pitch", "pitch 0.5, 1 and 2: one sample at three playback rates", 5.5),
        Pass("bed", "A bed is not spatial: it stays put while the camera pans", 7.0),
    )),
    Chapter("distance", "2  Distance attenuation", "Each doubling of the distance costs 6 dB (Doppler and air absorption off here)", (
        Pass("off", "distance model: none", 8.5),
        Pass("on", "distance model: inverse, -6 dB per doubling", 8.5),
    )),
    Chapter("panning", "3  Stereo panning", "Left and right levels follow the position in the picture", (
        Pass("amplitude", "panner: amplitude (level difference only)", 7.0, {"panner": "amplitude"}),
    )),
    Chapter("screen", "4  Screen-relative panning", "The pan follows where a source appears in the picture,\n"
            "so zooming in moves the sound outwards with the image", (
        Pass("camera", "pan reference: camera direction", 7.0, {"pan_reference": "camera"}),
        Pass("screen", "pan reference: screen position, screen edge at 29° (a large screen)", 7.0,
             {"pan_reference": "screen", "screen_edge_deg": 29.0}),
    )),
    Chapter("delay", "5  Propagation delay", "Sound travels at 343 m/s: from 34, 172 and 343 m it arrives\n"
            "0.1, 0.5 and 1.0 s after the impact (distance and air damping off here)", (
        Pass("physical", "physical: heard when the wave arrives", 8.0),
        Pass("synced", "sync_to_picture: heard on the frame of the impact", 8.0),
    )),
    Chapter("doppler", "6  Doppler", "A 1 kHz tone passes at 34.3 m/s (123 km/h):\n"
            "1111 Hz while approaching, 909 Hz while receding", (
        Pass("off", "doppler 0: no pitch change", 7.0),
        Pass("on", "doppler 1: physical", 7.0),
        Pass("double", "doppler 2: exaggerated", 7.0),
    )),
    Chapter("air", "7  Air absorption", "Air damps high frequencies over distance: noise at 10, 100, 300\n"
            "and 600 m (distance attenuation off here)", (
        Pass("off", "air absorption off", 6.5),
        Pass("on", "air absorption on (20 °C, 50 % humidity)", 6.5),
    )),
    Chapter("ears", "8  Ear model: time difference and head shadow", "The far ear hears the sound later and duller.\n"
            "Listen on headphones", (
        Pass("amplitude", "level difference only", 6.5, {"panner": "amplitude"}),
        Pass("hybrid", "+ time difference and head shadow (default strength)", 6.5, {"panner": "hybrid", **REAR_OFF}),
        Pass("full", "+ time difference and head shadow (full strength)", 6.5,
             {"panner": "hybrid", "itd_scale": 1.0, "head_shadow": 1.0, **REAR_OFF}),
    )),
    Chapter("rear", "9  Rear cue", "Behind the camera a source becomes a little quieter and duller", (
        Pass("off", "rear cue off", 6.5, REAR_OFF),
        Pass("default", "rear cue: default (-2 dB, 6 kHz)", 6.5),
        Pass("strong", "rear cue: strong (-6 dB, 2 kHz)", 6.5, {"rear_gain_db": -6.0, "rear_cutoff_hz": 2000.0}),
    )),
    Chapter("cone", "10  Directivity", "A horn radiates forwards: it is louder while it faces the camera", (
        Pass("omni", "omnidirectional", 7.0),
        Pass("cone", "cone: 60° inner, 180° outer, -24 dB outside", 7.0),
    )),
    Chapter("occlusion", "11  Occlusion", "A wall between the source and the camera muffles the direct sound", (
        Pass("off", "occlusion off", 7.5),
        Pass("on", "occlusion on", 7.5),
    )),
    Chapter("reverb", "12  Reverb", "One environment per shot: early reflections and a decaying tail", (
        Pass("dry", "dry", 4.5),
        Pass("room", "reverb: room (0.4 s)", 4.5, {"reverb": "room"}),
        Pass("alley", "reverb: alley (1.5 s)", 5.5, {"reverb": "alley"}),
        Pass("hall", "reverb: concert hall (3.9 s)", 7.0, {"reverb": "concerthall"}),
        Pass("far", "concert hall: the farther away, the more reverb relative to the direct sound", 10.5,
             {"reverb": "concerthall"}),
    )),
    Chapter("cuts", "13  Camera cuts", "At a cut, level, direction and delay switch at once, without a pitch glide", (
        Pass("cuts", "two cameras, a cut every 2 s", 8.5),
    )),
    Chapter("phase", "14  Loop phase", "Eight copies of one loop: in step, or each from its own random point", (
        Pass("zero", "loop_phase 0: all in step", 5.5),
        Pass("random", "loop_phase random (default)", 5.5),
    )),
    Chapter("together", "15  All together", "Doppler, occlusion, reverb and a bed in one shot", (
        Pass("all", "default settings, reverb: alley", 16.5, {"reverb": "alley"}),
    )),
    Chapter("outro", "SoundStage", "Tag objects in Blender, bake, render: offline spatial sound", title_seconds=4.0),
)


@dataclass(frozen=True)
class Window:
    """Frames [first, last] of a title card or a pass."""

    first: int
    last: int

    def at(self, seconds: float) -> float:
        """Frame at a time from the start of the window."""
        return self.first + seconds * FPS

    @property
    def seconds(self) -> float:
        return (self.last - self.first + 1) / FPS


@dataclass(frozen=True)
class Timed:
    chapter: Chapter
    title: Window
    passes: dict[str, Window]

    @property
    def last(self) -> int:
        return max([self.title.last, *(w.last for w in self.passes.values())])


def frames(seconds: float) -> int:
    return round(seconds * FPS)


def timeline() -> dict[str, Timed]:
    """Every chapter with the frame windows of its title card and passes, in order."""
    out, frame = {}, FRAME_START
    for ch in CHAPTERS:
        title = Window(frame, frame + frames(ch.title_seconds) - 1)
        frame = title.last + 1
        passes = {}
        for p in ch.passes:
            passes[p.key] = Window(frame, frame + frames(p.seconds) - 1)
            frame = passes[p.key].last + 1
        out[ch.key] = Timed(ch, title, passes)
    return out


def frame_end() -> int:
    return list(timeline().values())[-1].last


def source_id(chapter: str, pass_key: str, name: str) -> str:
    return f"{chapter}.{pass_key}.{name}"


def solo(chapter: str, pass_key: str) -> str:
    """``--solo`` glob for the sound entries of one pass."""
    return f"{chapter}.{pass_key}.*"


if __name__ == "__main__":
    for t in timeline().values():
        print(f"{t.title.first:5d}-{t.title.last:5d}  {t.chapter.title.splitlines()[0]}")
        for key, w in t.passes.items():
            print(f"{w.first:5d}-{w.last:5d}    {key}")
    print(f"{frame_end() / FPS:.1f} s, frames {FRAME_START}-{frame_end()}")
