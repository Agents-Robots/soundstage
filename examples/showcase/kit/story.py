"""Storyboard of a section: title page, passes, frame windows, source ids (stdlib only).

Every section's ``section.py`` builds one ``Section``. Picture (``build.py`` in Blender) and sound
(``kit.audio`` in the venv) both take the frame ranges from it (rule C4), so they cannot drift
apart. ``manifest()`` is what the build writes to ``section.json`` (rule C8).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

FPS = 30
RATE = 48000
SAMPLES_PER_FRAME = RATE // FPS
RESOLUTION = (1920, 1080)
TITLE_FRAMES = 90
FADE_FRAMES = 8
REPO_URL = ""
"""Where the project is, for the end card (``outro``); empty while the repository is not public."""


@dataclass(frozen=True)
class TitlePage:
    """Texts of the title page (sections/README.md, "Title page")."""

    title: str
    claim: str
    code: str
    listen: str
    headphones: bool = False


@dataclass(frozen=True)
class Pass:
    """One run of the action with one setting.

    ``frames`` is the length in frames; ``settings`` are scene-setting overrides of its render;
    ``chip`` is ``"WITHOUT"``, ``"WITH"`` or empty; ``setting`` is the text under the label.
    """

    key: str
    frames: int
    label: str
    setting: str = ""
    chip: str = ""
    settings: dict = field(default_factory=dict)
    bake: str = ""


@dataclass(frozen=True)
class Window:
    """Frames [first, last] of a title page or a pass."""

    first: int
    last: int

    def at(self, seconds: float) -> float:
        """Frame at a time from the start of the window (fractional frames allowed)."""
        return self.first + seconds * FPS

    @property
    def frames(self) -> int:
        return self.last - self.first + 1

    @property
    def seconds(self) -> float:
        return self.frames / FPS


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    passes: tuple[Pass, ...]
    title_page: TitlePage | None = None
    title_frames: int = TITLE_FRAMES
    gain_db: float = 0.0
    reverb: str | None = None
    reference: str = ""
    """Pass whose loudness is the section's level (S2); default: the last pass."""
    loudness_reported_only: bool = False
    """S2 for single loud impacts: the true-peak limit wins, the loudness is reported, not checked."""
    bakes: dict = field(default_factory=dict)
    """Bake variants by name: bake-time scene settings (``listener`` ...) of another bake of the same
    .blend into ``bake_<name>/``, and optionally ``frames`` ("A-B"). A pass renders from one by naming
    it in ``Pass.bake``; a check may read others."""

    @property
    def title_window(self) -> Window | None:
        return Window(1, self.title_frames) if self.title_frames else None

    @property
    def windows(self) -> dict[str, Window]:
        out, frame = {}, self.title_frames + 1
        for p in self.passes:
            out[p.key] = Window(frame, frame + p.frames - 1)
            frame += p.frames
        return out

    @property
    def frame_end(self) -> int:
        return self.title_frames + sum(p.frames for p in self.passes)

    def window(self, pass_key: str) -> Window:
        return self.windows[pass_key]

    def source_id(self, pass_key: str, name: str) -> str:
        return f"{self.key}.{pass_key}.{name}"

    def probe_id(self, pass_key: str, name: str) -> str:
        return f"{self.key}.probe.{pass_key}.{name}"

    def solo(self, pass_key: str) -> str:
        """``--solo`` pattern for the sound entries of one pass."""
        return f"{self.key}.{pass_key}.*"

    def probe_solo(self, pass_key: str, name: str = "*") -> str:
        return f"{self.key}.probe.{pass_key}.{name}"

    def manifest(self) -> dict:
        """The content of ``section.json``."""
        return {
            "key": self.key,
            "title": self.title,
            "fps": FPS,
            "sample_rate": RATE,
            "resolution": list(RESOLUTION),
            "frames": [1, self.frame_end],
            "title_frames": [1, self.title_frames] if self.title_frames else None,
            "title_page": asdict(self.title_page) if self.title_page else None,
            "gain_db": self.gain_db,
            "reverb": self.reverb,
            "reference": self.reference or self.passes[-1].key,
            "loudness_reported_only": self.loudness_reported_only,
            "bakes": self.bakes,
            "passes": [{**asdict(p), "window": [self.window(p.key).first, self.window(p.key).last]}
                       for p in self.passes],
        }


def seconds_to_frames(seconds: float) -> int:
    frames = round(seconds * FPS)
    if abs(frames - seconds * FPS) > 1e-6:
        raise ValueError(f"{seconds} s is not a whole number of frames at {FPS} fps")
    return frames
