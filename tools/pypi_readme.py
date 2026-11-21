"""Rewrite README.md for the PyPI project page (stdlib only; run by the publish workflow).

PyPI shows the README without the repository around it, so relative links and pictures break.
This rewrites every Markdown link target that is neither absolute nor an anchor to a GitHub URL
at the released ref: pictures to ``raw.githubusercontent.com``, folders to ``tree/``, files to
``blob/``. Anchors (``#the-science``) point at the README on GitHub, since PyPI gives headings no
ids. The repository's README stays as it is; the workflow rewrites its checkout before the build.

Usage::

    python tools/pypi_readme.py --ref v0.1.0 [--in README.md] [--out README.md]
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

REPO = "Agents-Robots/soundstage"
LINK = re.compile(r"(!?)\[([^\]]*)\]\(([^)\s]+)\)")


def absolute(target: str, ref: str, picture: bool) -> str:
    """The GitHub URL of a link target in the README, at ``ref``."""
    if re.match(r"[a-z]+:", target):
        return target
    if target.startswith("#"):
        return f"https://github.com/{REPO}/blob/{ref}/README.md{target}"
    if picture:
        return f"https://raw.githubusercontent.com/{REPO}/{ref}/{target}"
    kind = "tree" if target.split("#")[0].endswith("/") else "blob"
    return f"https://github.com/{REPO}/{kind}/{ref}/{target}"


def rewrite(text: str, ref: str) -> str:
    """The README with every relative link and picture made absolute."""
    return LINK.sub(lambda m: f"{m[1]}[{m[2]}]({absolute(m[3], ref, bool(m[1]))})", text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ref", required=True, help="git tag or commit the links point at")
    parser.add_argument("--in", dest="src", default="README.md")
    parser.add_argument("--out", default=None, help="default: overwrite --in")
    args = parser.parse_args()
    text = rewrite(Path(args.src).read_text(encoding="utf-8"), args.ref)
    Path(args.out or args.src).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
