"""Download PZDB minutes (2022-2025) from estero-fl.gov/pzdbminutes/ into data/raw/pzdb/."""
from __future__ import annotations

import csv
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "pzdb"
PAGE = "https://estero-fl.gov/pzdbminutes/"
MIN_YEAR, MAX_YEAR = 2022, 2025


def scrape_pdf_urls() -> list[str]:
    req = urllib.request.Request(PAGE, headers={"User-Agent": "EagleGIS/1.0"})
    html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    hrefs = re.findall(r'href="([^"]+\.pdf)"', html, re.I)
    out: list[str] = []
    for h in hrefs:
        if "cancel" in h.lower() or "cancellation" in h.lower():
            continue
        if "/minutes/" not in h.lower():
            continue
        if "pzdb" not in h.lower() and "pzd%20board" not in h.lower() and "pzd board" not in h.lower():
            continue
        url = h if h.startswith("http") else urllib.parse.urljoin(PAGE, h)
        out.append(url)
    return sorted(set(out))


def parse_year(url: str) -> int | None:
    path = urllib.parse.unquote(url).lower()
    m = re.search(r"/minutes/(\d{4})", path)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d{4})\s*pzdb", path)
    if m:
        return int(m.group(1))
    return None


def canonical_name(url: str, folder_year: int) -> str | None:
    """Build YYYYMMDD PZDB Minutes.pdf from MMDDYYYY in URL when possible."""
    path = urllib.parse.unquote(url)
    base = Path(path).name
    m = re.match(r"^(\d{2})(\d{2})(\d{4})\s+PZDB", base, re.I)
    if m:
        mm, dd, yyyy = m.group(1), m.group(2), int(m.group(3))
        # Village site sometimes typo year as 2005 in /2025 Minutes/ paths.
        if yyyy < 2015 or yyyy > 2030 or abs(yyyy - folder_year) > 1:
            yyyy = folder_year
        return f"{yyyy}{mm}{dd} PZDB Minutes.pdf"
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", path)
    if m:
        yyyy, mm, dd = int(m.group(1)), m.group(2), m.group(3)
        return f"{yyyy}{mm}{dd} PZDB Minutes.pdf"
    return None


def download(url: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 5000:
        return True
    req = urllib.request.Request(url, headers={"User-Agent": "EagleGIS/1.0"})
    try:
        data = urllib.request.urlopen(req, timeout=120).read()
        if len(data) < 5000:
            return False
        dest.write_bytes(data)
        return True
    except Exception:
        return False


def main() -> int:
    urls = scrape_pdf_urls()
    manifest_rows: list[dict[str, str]] = []
    ok = fail = skip = 0

    for url in urls:
        year = parse_year(url)
        if year is None or year < MIN_YEAR or year > MAX_YEAR:
            continue
        name = canonical_name(url, year)
        if not name:
            print(f"skip (no date parse): {url}")
            continue
        rel = OUT / str(year) / name
        manifest_rows.append({
            "meeting_year": str(year),
            "canonical_name": name,
            "source_url": url,
            "rel_path": str(rel.relative_to(ROOT)).replace("\\", "/"),
        })
        if rel.exists() and rel.stat().st_size > 5000:
            skip += 1
            continue
        if download(url, rel):
            ok += 1
            print(f"ok {name}")
        else:
            fail += 1
            print(f"fail {name}")
        time.sleep(0.4)

    manifest_path = OUT / "manifest_pilot.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["meeting_year", "canonical_name", "source_url", "rel_path"],
        )
        w.writeheader()
        w.writerows(sorted(manifest_rows, key=lambda r: r["canonical_name"]))

    print(f"\nmanifest: {len(manifest_rows)} rows -> {manifest_path}")
    print(f"downloaded={ok} skipped={skip} failed={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
