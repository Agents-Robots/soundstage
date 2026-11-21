"""Make the pictures of the project page in site/img/ (run in the repo venv).

- Feature stills: one frame of a showcase section each (``out/showcase/<key>/<key>.blend``, built
  by ``examples/showcase``), rendered at 1920×1080 with Cycles on the CPU (about 20 s each) and
  scaled to 1280×720.
- ``plot.webp``: the debug plot of the flyby example (README, "Try it"), by default
  ``out/flyby/mix.plot.png``.
- Pictures from films: their frames live outside this repository, so they are passed by path with
  ``--film NAME=PATH``.
- The title picture ``hero-city`` shows where the sound sources of its frame are: ``--hero-bake DIR``
  is the bake of the same shot (``scene.json`` and ``scene.npz``), whose sources are projected into
  the frame through the baked camera. Cars that are heard directly become dots in the picture; the
  sources of ``HERO_LABELS`` become the speaker symbols, as HTML over the picture (written into
  ``site/index.html`` between the ``sources`` markers) and drawn into ``hero-city-labelled.webp``
  (README) and ``og.jpg`` (link previews).
- The charts of the page's science section: ``tools/make_site_figures.py``.

Usage::

    .venv/bin/python tools/make_site_images.py [--only doppler,plot | --only none] [--stills DIR] [--plot PNG]
        [--film hero-city=FRAME --hero-bake DIR [--hero-frame N]]
        [--film terrace=FRAME] [--film race=FRAME]

``--stills DIR`` keeps the rendered PNGs in DIR and reuses the ones found there.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from html import escape
from pathlib import Path

import numpy as np
from matplotlib import font_manager
from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[1]
IMG = REPO / "site" / "img"
SHOWCASE = REPO / "out" / "showcase"
FRAMES_SCRIPT = REPO / "examples" / "showcase" / "kit" / "blender" / "frames.py"

STILLS = {  # picture: (showcase section, frame of the section)
    "distance": ("distance", 766),
    "screen": ("screen", 689),
    "doppler": ("doppler", 223),
    "delay": ("delay", 211),
    "occlusion": ("occlusion", 492),
    "reverb": ("reverb", 832),
    "directivity": ("directivity", 549),
    "around": ("around", 190),
    "cuts": ("cuts", 624),
    "city": ("city", 842),
}
FILM_WIDTH = {"hero-city": 2048, "terrace": 1600, "race": 1600}
QUALITY = 82

PAGE = REPO / "site" / "index.html"
SOURCES_BLOCK = re.compile(r"(<!-- sources:begin[^>]*-->).*?(\n *<!-- sources:end -->)", re.S)
HERO_LABELS = (  # source id (or a group, at its sources' median place), label, side of the label, on phones too
    ("neon:sg_blade1", "Neon sign", "right", True),
    ("car:tr_c012_008", "Flying car", "right", False),
    ("chat:tc_wall0016_451", "Terrace crowd", "right", False),
    ("crowd:tc_wall0010_712", "Rooftop party", "right", False),
    ("cars", "{n} flying cars", "right", True),
    ("crowd:st_king_party", "Party: crowd and music", "left", True),
    ("holo:hs_panel1", "Sign", "right", False),
    ("holo:sg_holo1", "Hologram sign", "left", True),
    ("music:st_guardian_party", "Music", "right", False),
    ("fan:fg_fan1", "Fan", "right", False),
)
HEARD = 0.5
"""Baked visibility (mean of the bands) above which a source counts as heard directly."""
ACCENT, INK, PANEL, CAR = (245, 165, 36), (243, 240, 234), (11, 14, 19), (190, 226, 255)


def render_still(key: str, frame: int, out_dir: Path) -> Path:
    """Render one frame of a section's .blend unless ``out_dir`` already has it."""
    png = out_dir / key / f"{frame:05d}.png"
    if not png.exists():
        blend = SHOWCASE / key / f"{key}.blend"
        if not blend.exists():
            raise SystemExit(f"{blend} is missing: build the showcase section first (examples/showcase/README.md)")
        subprocess.run(
            ["blender", "-b", str(blend), "--factory-startup", "-y", "--python", str(FRAMES_SCRIPT), "--",
             "--out", str(png.parent), "--frames", str(frame), "--percent", "100", "--samples", "48"],
            check=True, stdout=subprocess.DEVNULL)
    return png


def save_webp(src: Path, name: str, width: int, lossless: bool = False) -> Image.Image:
    """Write ``site/img/<name>.webp`` at most ``width`` wide and return the scaled picture."""
    im = Image.open(src).convert("RGB")
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    out = IMG / f"{name}.webp"
    im.save(out, "WEBP", quality=QUALITY, method=6, lossless=lossless)
    print(f"{out.relative_to(REPO)}  {im.width}×{im.height}  {out.stat().st_size / 1024:.0f} kB")
    return im


@dataclass
class Mark:
    """A baked source in the picture: place as a share of width and height, distance, visibility."""

    id: str
    group: str
    u: float
    v: float
    distance_m: float
    visibility: float


def project_sources(bake_dir: Path, frame: float, aspect: float) -> list[Mark]:
    """The spatial sources of a bake that lie inside the camera's frame at ``frame``.

    ``listener_frame`` holds the frame's left and right edges as x / -z in camera space
    (docs/spec/scene-format.md); the pixels are square, so the same scale applies upwards."""
    man = json.loads((bake_dir / "scene.json").read_text())
    z = np.load(bake_dir / "scene.npz")
    i = int(np.argmin(np.abs(z["frames"] - frame)))
    to_camera = np.linalg.inv(z["listener_matrix"][i])
    left, right = z["listener_frame"][i]
    positions = z["src_pos"][i]
    visibility = z["src_visibility"][int(np.argmin(np.abs(z["vis_frames"] - frame)))].mean(axis=1)
    marks = []
    for s in man["sources"]:
        if s["track"] is None:  # not spatial: beds
            continue
        x, y, depth = (to_camera @ np.append(positions[s["track"]], 1.0))[:3]
        if depth > -0.5:  # behind the camera
            continue
        u = (x / -depth - left) / (right - left)
        v = 0.5 - (y / -depth) / (right - left) * aspect
        if 0 <= u <= 1 and 0 <= v <= 1:
            marks.append(Mark(s["id"], s["group"], float(u), float(v), float(np.linalg.norm([x, y, depth])),
                              float(visibility[s["track"]])))
    return marks


def hero_labels(marks: list[Mark]) -> list[tuple[Mark, str, str, str, bool]]:
    """(mark, label, distance text, side, on phones) per entry of ``HERO_LABELS``."""
    by_id = {m.id: m for m in marks}
    out = []
    for key, label, side, phone in HERO_LABELS:
        if key in by_id:
            m = by_id[key]
            out.append((m, label, f"{m.distance_m:.0f}\u00a0m", side, phone))
        else:  # a group: at the median place of its members in view
            group = [m for m in marks if m.group == key]
            if not group:
                raise SystemExit(f"hero: no source or group {key!r} in the frame")
            m = Mark(key, key, float(np.median([g.u for g in group])), float(np.median([g.v for g in group])), 0.0, 1.0)
            out.append((m, label.format(n=len(group)), "", side, phone))
    return out


def draw_dots(im: Image.Image, marks: list[Mark], labelled: set[str]) -> Image.Image:
    """Dots for the cars heard directly and rings for the other sources that carry no label."""
    k = 3  # drawn larger and scaled down: PIL does not smooth edges
    layer = Image.new("RGBA", (im.width * k, im.height * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for m in marks:
        if m.visibility <= HEARD or m.id in labelled:
            continue
        x, y = m.u * layer.width, m.v * layer.height
        if m.group == "cars":
            r = 2.4 * k
            d.ellipse((x - r, y - r, x + r, y + r), fill=(*CAR, 215))
        else:
            r = 6.5 * k
            d.ellipse((x - r, y - r, x + r, y + r), outline=(*ACCENT, 240), width=2 * k)
    return Image.alpha_composite(im.convert("RGBA"), layer.resize(im.size, Image.LANCZOS)).convert("RGB")


def draw_speaker(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float) -> None:
    """The page's speaker symbol (``#spk`` in site/index.html, 24 units wide) in a disc of radius r."""
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=ACCENT)
    u = 2 * r / 34  # the symbol's 24 units inside the disc
    at = lambda x, y: (cx + (x - 12.5) * u, cy + (y - 12) * u)  # noqa: E731
    d.polygon([at(4, 9.5), at(7.5, 9.5), at(12, 6), at(12, 18), at(7.5, 14.5), at(4, 14.5)], fill=PANEL)
    for radius, half in ((3.6, 55), (7.0, 50)):
        (x0, y0), (x1, y1) = at(13.2 - radius, 12 - radius), at(13.2 + radius, 12 + radius)
        d.arc((x0, y0, x1, y1), -half, half, fill=PANEL, width=max(1, round(1.9 * u)))


def draw_labels(im: Image.Image, labels: list[tuple[Mark, str, str, str, bool]]) -> Image.Image:
    """The picture with the speaker symbols and their labels drawn in (README, link previews)."""
    k = 2
    scale = im.width / 2048 * k
    layer = Image.new("RGBA", (im.width * k, im.height * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    font = ImageFont.truetype(font_manager.findfont("DejaVu Sans"), round(29 * scale))
    r, pad = 21 * scale, 14 * scale
    for m, label, distance, side, _ in labels:
        text = f"{label} \u00b7 {distance}" if distance else label
        x, y = m.u * layer.width, m.v * layer.height
        width = d.textlength(text, font=font)
        a, b = (x - r, x + r + pad + width + 1.4 * pad) if side == "right" else (x - r - pad - width - 1.4 * pad, x + r)
        d.rounded_rectangle((a - 3 * scale, y - r - 3 * scale, b + 3 * scale, y + r + 3 * scale), radius=r + 3 * scale,
                            fill=(*PANEL, 205), outline=(*ACCENT, 150), width=max(1, round(1.2 * scale)))
        d.text((x + r + pad if side == "right" else a + 1.4 * pad, y), text, font=font, fill=INK, anchor="lm")
        draw_speaker(d, x, y, r)
    return Image.alpha_composite(im.convert("RGBA"), layer.resize(im.size, Image.LANCZOS)).convert("RGB")


def sources_html(labels: list[tuple[Mark, str, str, str, bool]]) -> str:
    """The list of speaker symbols laid over the title picture."""
    rows = []
    for m, label, distance, side, phone in labels:
        classes = " ".join(c for c in ("l" if side == "left" else "", "" if phone else "wide-only") if c)
        rows.append(f'      <li{f" class={chr(34)}{classes}{chr(34)}" if classes else ""} '
                    f'style="left:{100 * m.u:.2f}%;top:{100 * m.v:.2f}%">'
                    '<svg class="spk" viewBox="0 0 24 24" aria-hidden="true"><use href="#spk"/></svg>'
                    f'<span>{escape(label)}{f"<i> &middot; {distance.replace(chr(160), "&nbsp;")}</i>" if distance else ""}</span></li>')
    return "\n".join(rows)


def og_image(labelled: Image.Image) -> None:
    """``og.jpg`` (1200×630): the whole labelled picture above the name on the page's background."""
    og = Image.new("RGB", (1200, 630), (18, 22, 29))
    top = labelled.resize((1200, round(labelled.height * 1200 / labelled.width)), Image.LANCZOS)
    og.paste(top, (0, 0))
    d = ImageDraw.Draw(og)
    y = top.height + (630 - top.height) / 2
    bold = ImageFont.truetype(font_manager.findfont("DejaVu Sans:bold"), 46)
    plain = ImageFont.truetype(font_manager.findfont("DejaVu Sans"), 25)
    d.text((40, y), "SoundStage", font=bold, fill=INK, anchor="lm")
    d.text((40 + d.textlength("SoundStage", font=bold) + 28, y + 4), "Spatial sound, computed from your Blender scene",
           font=plain, fill=(197, 200, 204), anchor="lm")
    og.save(IMG / "og.jpg", quality=86, optimize=True)
    print(f"site/img/og.jpg  1200×630  {(IMG / 'og.jpg').stat().st_size / 1024:.0f} kB")


def hero(frame_png: Path, bake_dir: Path, frame: float) -> None:
    """Title picture with its sources: ``hero-city.webp`` (dots), the labels on the page,
    ``hero-city-labelled.webp`` and ``og.jpg``."""
    im = Image.open(frame_png).convert("RGB")
    if im.width > FILM_WIDTH["hero-city"]:
        im = im.resize((FILM_WIDTH["hero-city"], round(im.height * FILM_WIDTH["hero-city"] / im.width)), Image.LANCZOS)
    marks = project_sources(bake_dir, frame, im.width / im.height)
    labels = hero_labels(marks)
    dotted = draw_dots(im, marks, {m.id for m, *_ in labels})
    labelled = draw_labels(dotted, labels)
    for name, picture in (("hero-city", dotted), ("hero-city-labelled", labelled)):
        out = IMG / f"{name}.webp"
        picture.save(out, "WEBP", quality=QUALITY, method=6)
        print(f"{out.relative_to(REPO)}  {picture.width}×{picture.height}  {out.stat().st_size / 1024:.0f} kB")
    og_image(labelled)
    page = PAGE.read_text()
    if not SOURCES_BLOCK.search(page):
        raise SystemExit(f"{PAGE.relative_to(REPO)}: the sources:begin / sources:end markers are missing")
    PAGE.write_text(SOURCES_BLOCK.sub(lambda g: g.group(1) + "\n" + sources_html(labels) + g.group(2), page))
    groups: dict[str, list[Mark]] = {}
    for m in marks:
        groups.setdefault(m.group, []).append(m)
    print(f"frame {frame:g}: {len(marks)} sources in the picture, {sum(m.visibility > HEARD for m in marks)} heard directly")
    for g, ms in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        print(f"  {g:12s} {len(ms):5d} in the picture, {sum(m.visibility > HEARD for m in ms):5d} heard directly")
    for m, label, distance, *_ in labels:
        print(f"  label {label!r:28} {m.id:28s} {100 * m.u:5.1f} % {100 * m.v:5.1f} %  {distance}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--only", default="", help="comma-separated pictures, or none (default: all stills and the plot)")
    p.add_argument("--stills", type=Path, help="folder for the rendered PNGs (default: a temporary one)")
    p.add_argument("--plot", type=Path, default=REPO / "out" / "flyby" / "mix.plot.png", help="the flyby example's debug plot")
    p.add_argument("--film", action="append", default=[], metavar="NAME=PATH",
                   help=f"a film frame; names: {', '.join(FILM_WIDTH)}")
    p.add_argument("--hero-bake", type=Path, help="bake folder of the hero-city shot: draws its sound sources")
    p.add_argument("--hero-frame", type=float, help="frame of the hero-city picture (default: the number in its file name)")
    a = p.parse_args()
    films = dict(f.split("=", 1) for f in a.film)
    if unknown := set(films) - set(FILM_WIDTH):
        p.error(f"unknown film picture: {', '.join(sorted(unknown))}")
    only = set(a.only.split(",")) - {"none"} if a.only else set(STILLS) | {"plot"}
    if unknown := only - set(STILLS) - {"plot"}:
        p.error(f"unknown picture: {', '.join(sorted(unknown))}")
    IMG.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        stills = a.stills or Path(tmp)
        for name, (key, frame) in STILLS.items():
            if name in only:
                save_webp(render_still(key, frame, stills), name, 1280)
    if "plot" in only:
        if not a.plot.exists():
            raise SystemExit(f"{a.plot} is missing: run the commands of the README's \"Try it\" first")
        save_webp(a.plot, "plot", 960, lossless=True)
    for name, path in films.items():
        if name == "hero-city":
            if not a.hero_bake:
                p.error("--film hero-city needs --hero-bake, the bake of the same shot")
            frame = a.hero_frame if a.hero_frame is not None else float(re.sub(r"\D", "", Path(path).stem))
            hero(Path(path), a.hero_bake, frame)
        else:
            save_webp(Path(path), name, FILM_WIDTH[name])


if __name__ == "__main__":
    main()
