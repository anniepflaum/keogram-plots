#!/usr/bin/env python3
"""
Download aurora keogram PNGs from:
  https://optics.gi.alaska.edu/amisr_archive/Processed_data/aurorax/stream2/

Directory pattern (from user’s spec):
  /YYYY/MM/DD/<station>/
  file: YYYYMMDD__pfrr_asi3_full-keo-rgb.png

Defaults:
  station = pfrr_amisr01
  camera  = asi3

Usage:
  python3 download_keograms.py 2025-11-17 2025-11-19 \
      --out ~/Documents/keogram_project/full_keograms

  # custom station/camera if needed:
  python3 download_keograms.py 2025-11-17 2025-11-17 \
      --station pfrr_amisr01 --camera asi3
"""

import argparse
import datetime as dt
import os
import shutil
import subprocess
from typing import Tuple
import requests

BASE = ("https://optics.gi.alaska.edu/amisr_archive/Processed_data/aurorax/stream2/")
UA = {"User-Agent": "keogram-downloader/1.0 (+github.com/yourname)"}

def daterange(d0: dt.date, d1: dt.date):
    d = d0
    while d <= d1:
        yield d
        d += dt.timedelta(days=1)

def build_url(day: dt.date, station: str, camera: str) -> Tuple[str, str]:
    """Return (remote_url, filename) for the given date/station/camera."""
    y = f"{day.year:04d}"
    m = f"{day:%m}"
    d = f"{day:%d}"
    ymd = day.strftime("%Y%m%d")

    # Filename uses the *site* (prefix before first underscore) + camera (e.g., pfrr_asi3)
    site = station.split("_", 1)[0]
    fname = f"{ymd}__{site}_{camera}_full-keo-rgb.png"

    url = f"{BASE}{y}/{m}/{d}/{station}/{fname}"
    return url, fname

def smart_fetch(url: str, dst_path: str):
    """Prefer wget/curl (resume support), else Python requests."""
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)

    if shutil.which("wget"):
        # -c resume, -nv quieter
        print(f"[wget] {url}")
        res = subprocess.run(["wget", "-nv", "-c", "-O", dst_path, url])
        if res.returncode != 0:
            raise RuntimeError(f"wget failed ({res.returncode})")
        return

    if shutil.which("curl"):
        print(f"[curl] {url}")
        res = subprocess.run(["curl", "-L", "-C", "-", "-o", dst_path, url])
        if res.returncode != 0:
            raise RuntimeError(f"curl failed ({res.returncode})")
        return

    # Fallback: requests (no resume)
    print(f"[py  ] {url}")
    with requests.get(url, stream=True, timeout=120, headers=UA) as r:
        if r.status_code == 404:
            raise FileNotFoundError("404 Not Found")
        r.raise_for_status()
        with open(dst_path, "wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk)

def main():
    p = argparse.ArgumentParser(description="Download aurora keogram PNGs by date range.")
    p.add_argument("start", nargs="?", help="Start date (YYYY-MM-DD, UTC)")
    p.add_argument("end", nargs="?", help="End date inclusive (YYYY-MM-DD, UTC)")
    p.add_argument("--station", default="pfrr_amisr01", help="Station folder name (default: pfrr_amisr01)")
    p.add_argument("--camera", default="asi3", help="Camera code in filename (default: asi3)")
    p.add_argument("--out", default="/Users/anniepflaum/Documents/keogram_project/full_keograms", help="Local output root directory")
    p.add_argument("--skip-existing", action="store_true", help="Skip if destination file already exists")
    p.add_argument("--dry-run", action="store_true", help="List URLs without downloading")
    args = p.parse_args()

    if not args.start:
        args.start = input("Start date (YYYYMMDD): ").strip()
    if not args.end:
        args.end = input("End date inclusive (YYYYMMDD): ").strip()

    start = dt.date.fromisoformat(args.start)
    end   = dt.date.fromisoformat(args.end)
    if end < start:
        raise SystemExit("End date must be >= start date")

    to_get = []
    for day in daterange(start, end):
        url, fname = build_url(day, args.station, args.camera)
        # mirror YYYY/MM/DD locally; also include station folder for clarity
        outdir = os.path.join(args.out, f"{day.year:04d}", f"{day:%m}")
        dst = os.path.join(outdir, fname)
        to_get.append((day, url, dst))

    if args.dry_run:
        for day, url, dst in to_get:
            print(f"{day} -> {url}")
        return

    ok = 0
    miss = 0
    err = 0

    for day, url, dst in to_get:
        if args.skip_existing and os.path.exists(dst):
            print(f"[skip] {dst}")
            ok += 1
            continue
        try:
            smart_fetch(url, dst)
            print(f"[done] {dst}")
            ok += 1
        except FileNotFoundError:
            print(f"[404 ] {url}")
            miss += 1
        except Exception as e:
            print(f"[fail] {url}  ({e})")
            err += 1

    print(f"\nSummary: downloaded={ok} missing={miss} errors={err}")

if __name__ == "__main__":
    main()
