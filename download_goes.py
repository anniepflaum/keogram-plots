#!/usr/bin/env python3
# goes18_mag_l1b_flat_downloader_v2.py
# Download GOES-18 MAG L1b "flat" daily files given a date range.
# Directory structure is YYYY/MM/ with one .nc per day (no daily subfolders).

import argparse
import datetime as dt
import os
import re
import shutil
import subprocess
from urllib.parse import urljoin

import requests

BASE = ("https://data.ngdc.noaa.gov/platforms/solar-space-observing-satellites/"
        "goes/goes18/l1b/mag-l1b-flat/")

# Accept .nc or .nc.gz just in case
FILE_SUFFIX_REGEX = r"\.nc(\.gz)?$"

def month_url(day: dt.date) -> str:
    return f"{BASE}{day.year:04d}/{day:%m}/"

def list_hrefs(index_html: str):
    # Pull all href targets from Apache-style listing
    return re.findall(r'href="([^"?#]+)"', index_html, flags=re.IGNORECASE)

def find_files_for_day(index_html: str, day: dt.date):
    ymd = day.strftime("%Y%m%d")
    # Typical name: ops_mag-l1b-flat_g18_dYYYYMMDD_v0-0-0.nc
    pat = re.compile(rf"^ops_mag-l1b-flat_g18_d{ymd}_.+{FILE_SUFFIX_REGEX}$")
    return [h for h in list_hrefs(index_html)
            if not h.endswith('/') and pat.match(h)]

def smart_fetch(url: str, outdir: str) -> str:
    """Download using wget (preferred), else curl, else Python requests."""
    os.makedirs(outdir, exist_ok=True)
    dst = os.path.join(outdir, os.path.basename(url))

    if shutil.which("wget"):
        # -c resume, -N timestamping, -nv quiet-ish
        subprocess.run(["wget", "-nv", "-c", "-N", "-P", outdir, url], check=True)
        return dst
    if shutil.which("curl"):
        subprocess.run(["curl", "-L", "-C", "-", "-o", dst, url], check=True)
        return dst

    # Pure Python fallback
    with requests.get(url, stream=True, timeout=180) as r:
        r.raise_for_status()
        with open(dst, "wb") as f:
            for chunk in r.iterated_content(1024 * 1024) if hasattr(r, "iterated_content") else r.iter_content(1024*1024):
                if chunk:
                    f.write(chunk)
    return dst

def daterange(d0: dt.date, d1: dt.date):
    d = d0
    while d <= d1:
        yield d
        d += dt.timedelta(days=1)

def main():
    ap = argparse.ArgumentParser(description="Download GOES-18 MAG L1b flat files by date range.")
    ap.add_argument("start", help="YYYY-MM-DD (UTC)")
    ap.add_argument("end", help="YYYY-MM-DD (UTC), inclusive")
    ap.add_argument("--out", default="/Users/anniepflaum/Documents/keogram_project/GOES_data",
                    help="Output root directory (default: GOES_data)")
    ap.add_argument("--dry-run", action="store_true", help="List what would download, then exit")
    args = ap.parse_args()

    start = dt.date.fromisoformat(args.start)
    end   = dt.date.fromisoformat(args.end)
    if end < start:
        raise SystemExit("End date must be >= start date")

    # Group requested days by month so we fetch each month index once
    days = list(daterange(start, end))
    months = {}
    for day in days:
        key = (day.year, day.month)
        months.setdefault(key, []).append(day)

    discovered = []
    for (yy, mm), month_days in months.items():
        idx = f"{BASE}{yy:04d}/{mm:02d}/"
        try:
            r = requests.get(idx, timeout=60)
            if r.status_code != 200:
                print(f"! {idx} -> HTTP {r.status_code}")
                continue
            html = r.text
            for day in month_days:
                files = find_files_for_day(html, day)
                if not files:
                    print(f"  {day} -> no file found in {idx}")
                    continue
                for fname in files:
                    discovered.append((day, idx, fname))
        except Exception as e:
            print(f"! error fetching {idx}: {e}")

    if not discovered:
        print("No files matched the requested range.")
        return

    print(f"Found {len(discovered)} file(s).")
    if args.dry_run:
        for day, idx, fname in discovered:
            print(f"{day}  {urljoin(idx, fname)}")
        return

    downloaded = 0
    for day, idx, fname in discovered:
        url = urljoin(idx, fname)
        outdir = os.path.join(args.out, f"{day.year:04d}", f"{day:%m}")
        try:
            local = smart_fetch(url, outdir)
            print(f"downloaded  {local}")
            downloaded += 1
        except Exception as e:
            print(f"! failed     {url}  ({e})")

    print(f"Done. Downloaded: {downloaded}/{len(discovered)}")

if __name__ == "__main__":
    main()
