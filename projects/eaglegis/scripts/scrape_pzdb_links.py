"""Scrape PDF links from estero-fl.gov/pzdbminutes/ for download manifest fixes."""
from __future__ import annotations

import re
import sys
import urllib.request

URL = "https://estero-fl.gov/pzdbminutes/"


def main() -> int:
    req = urllib.request.Request(URL, headers={"User-Agent": "EagleGIS/1.0"})
    html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    pdfs = sorted(set(re.findall(r'href="([^"]+\.pdf)"', html, re.I)))
    print(f"found {len(pdfs)} pdf links")
    for p in pdfs:
        if not p.startswith("http"):
            p = urllib.request.urljoin(URL, p)
        print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
