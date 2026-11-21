"""Make the pictures of the project page in site/img/ (run in the repo venv).

- Feature stills: one frame of a showcase section each (``out/showcase/<key>/<key>.blend``, built
  by ``examples/showcase``), rendered at 1920×1080 with Cycles on the CPU (about 20 s each) and
  scaled to 1280×720.
- ``plot.webp``: the debug plot of the flyby example (README, "Try it"), by default
  ``out/flyby/mix.plot.png``.
- Pictures from films: their frames live outside this repository, so they are passed by path with
  ``--film NAME=PATH``. ``hero-city`` also gives ``og.jpg``, the picture of link previews.

Usage::

    .venv/bin/python tools/make_site_images.py [--only doppler,plot] [--stills DIR] [--plot PNG]
        [--film hero-city=FRAME] [--film terrace=FRAME] [--film race=FRAME]

``--stills DIR`` keeps the rendered PNGs in DIR and reuses the ones found there.
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

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


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--only", default="", help="comma-separated pictures (default: all stills and the plot)")
    p.add_argument("--stills", type=Path, help="folder for the rendered PNGs (default: a temporary one)")
    p.add_argument("--plot", type=Path, default=REPO / "out" / "flyby" / "mix.plot.png", help="the flyby example's debug plot")
    p.add_argument("--film", action="append", default=[], metavar="NAME=PATH",
                   help=f"a film frame; names: {', '.join(FILM_WIDTH)}")
    a = p.parse_args()
    films = dict(f.split("=", 1) for f in a.film)
    if unknown := set(films) - set(FILM_WIDTH):
        p.error(f"unknown film picture: {', '.join(sorted(unknown))}")
    only = set(a.only.split(",")) if a.only else set(STILLS) | {"plot"}
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
        im = save_webp(Path(path), name, FILM_WIDTH[name])
        if name == "hero-city":  # link previews: 1200×630, cut from the middle
            h = round(im.height * 1200 / im.width)
            og = im.resize((1200, h), Image.LANCZOS) if h >= 630 else im.resize((round(im.width * 630 / im.height), 630), Image.LANCZOS)
            left, top = (og.width - 1200) // 2, (og.height - 630) // 2
            og.crop((left, top, left + 1200, top + 630)).save(IMG / "og.jpg", quality=85, optimize=True)
            print(f"site/img/og.jpg  1200×630  {(IMG / 'og.jpg').stat().st_size / 1024:.0f} kB")


if __name__ == "__main__":
    main()
