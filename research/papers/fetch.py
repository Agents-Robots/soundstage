"""Download the openly accessible papers cited in research/ into research/papers/pdf/ (gitignored).

    python3 research/papers/fetch.py [--force]

The PDFs are not in git: several are copyrighted (author or publisher copies that may be read but
not redistributed), and the repository may become public. Each entry names where the copy comes
from; sources without an open copy are listed in research/papers/README.md with their DOI only.
Stdlib only.
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

PAPERS = {
    "niemitalo2001": "http://yehar.com/blog/wp-content/uploads/2009/08/deip.pdf",
    "smith2002doppler": "https://ccrma.stanford.edu/~jos/doppler/dafx02.pdf",
    "smith2002resample": "https://ccrma.stanford.edu/~jos/resample/resample.pdf",
    "zavalishin2008tpt": "https://web.archive.org/web/2020id_/"
                         "https://www.native-instruments.com/fileadmin/redaktion_upload/pdf/KeepTopology.pdf",
    "zavalishin2020vafilter": "https://www.discodsp.net/VAFilterDesign_2.1.2.pdf",  # mirror; licence allows unmodified copies
    "brown1998": "https://escholarship.org/content/qt0cr9d23p/qt0cr9d23p.pdf",
    "pulkki1997": "https://www.audiolabs-erlangen.com/resources/aps-w23/papers/sap_Pulkki1997.pdf",
    "openal11": "https://www.openal.org/documentation/openal-1.1-specification.pdf",
    "fink2016": "https://www.hsu-hh.de/ant/wp-content/uploads/sites/699/2017/10/"
                "Fink-Holters-Z%C3%B6lzer-2016-Signal-matched-power-complementary-cross-fading-and-dry-wet-mixing.pdf",
    "itu1770": "https://www.itu.int/dms_pubrec/itu-r/rec/bs/R-REC-BS.1770-4-201510-S!!PDF-E.pdf",
    "dynamicsound2026": "https://arxiv.org/pdf/2601.15433",
    # Phase 3
    "tsingos1997": "https://graphicsinterface.org/wp-content/uploads/gi1997-2.pdf",
    "kapralos2007": "https://www.scitepress.org/Papers/2007/20758/20758.pdf",
    "valimaki2017velvet": "https://acris.aalto.fi/ws/portalfiles/portal/13412521/applsci_07_00483_v2.pdf",
    "albrecht2013distance": "https://mediatech.aalto.fi/publications/acoustics/ar/AlbrechtLokki2013Distance.pdf",
    "ebu_r128": "https://tech.ebu.ch/docs/r/r128.pdf",
    "ebu_tech3341": "https://tech.ebu.ch/docs/tech/tech3341.pdf",
    "ebu_tech3342": "https://tech.ebu.ch/docs/tech/tech3342.pdf",
    "giannoulis2012": "https://www.eecs.qmul.ac.uk/~josh/documents/2012/GiannoulisMassbergReiss-dynamicrangecompression-JAES2012.pdf",
}

OUT = Path(__file__).resolve().parent / "pdf"


def fetch(key: str, url: str, force: bool) -> str:
    target = OUT / f"{key}.pdf"
    if target.exists() and not force:
        return "present"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
    except Exception as e:  # report and continue with the others
        return f"failed: {e}"
    if not data.startswith(b"%PDF"):
        return f"failed: not a PDF ({len(data)} bytes)"
    target.write_bytes(data)
    return f"ok ({len(data) // 1024} KiB)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="download again even if present")
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    failed = 0
    for key, url in PAPERS.items():
        status = fetch(key, url, a.force)
        failed += status.startswith("failed")
        print(f"{key:24s} {status}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
