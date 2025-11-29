#!/usr/bin/env python3
"""
Scrape utHH/ hours from a day's directory, prompt for a window (show first/last only),
download each hour's keogram PNG, and stitch them horizontally.

Example hour path:
  https://optics.gi.alaska.edu/amisr_archive/Processed_data/aurorax/stream2/
    YYYY/MM/DD/pfrr_amisr01/utHH/YYYYMMDD_HH_pfrr_asi3_rgb-keogram.png
"""

import argparse, datetime as dt, os, re, sys
from typing import List, Optional, Tuple

import requests
from PIL import Image

import shutil, subprocess  # add these if not already present

BASE = "https://optics.gi.alaska.edu/amisr_archive/Processed_data/aurorax/stream2/"
DEFAULT_OUT = "/Users/anniepflaum/Documents/keogram_project/partial_keograms"
UA = {"User-Agent": "keogram-hourly-downloader/2.1 (+mac)"}
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/120.0.0.0 Safari/537.36")

# ---------- URL + scrape helpers ----------

def ymd_parts(day: dt.date):
    return f"{day.year:04d}", f"{day:%m}", f"{day:%d}", day.strftime("%Y%m%d")

def station_day_url(day: dt.date, station: str) -> str:
    y, m, d, _ = ymd_parts(day)
    return f"{BASE}{y}/{m}/{d}/{station}/"

def hour_dir(hh: int) -> str:
    return f"ut{hh:02d}/"  # directories are two-digit

def list_index(url: str, verbose: bool = False) -> list[str]:
    """
    Return link targets from a directory index. Tries requests first; if that
    fails or returns unexpected HTML, falls back to curl (which we know works).
    Robust to quoted/unquoted href and any case.
    """
    html = ""
    # Try requests first
    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": BROWSER_UA})
        if verbose:
            print(f"[index-requests] {r.status_code} {url}")
        if r.status_code == 200:
            html = r.text
    except Exception as e:
        if verbose:
            print(f"[index-requests] error {e}")

    # If requests didn’t get us anything usable, try curl
    if (not html or "href" not in html.lower()) and shutil.which("curl"):
        if verbose:
            print(f"[index-curl] {url}")
        try:
            res = subprocess.run(
                ["curl", "-sL", "-A", BROWSER_UA, url],
                check=False, capture_output=True, text=True
            )
            html = res.stdout or ""
        except Exception as e:
            if verbose:
                print(f"[index-curl] error {e}")

    if verbose:
        print(f"[index-html] len={len(html)} from {url}")

    if not html:
        return []

    # Extract href= with or without quotes (any case)
    hrefs = re.findall(
        r'href\s*=\s*(?:"([^"]+)"|\'([^\']+)\'|([^\s>]+))',
        html, flags=re.IGNORECASE
    )
    out = []
    for a, b, c in hrefs:
        h = (a or b or c).strip()
        if h.startswith("./"):
            h = h[2:]
        out.append(h)
    return out

def scrape_hours(day: dt.date, station: str, verbose: bool = False) -> list[int]:
    base = station_day_url(day, station)
    hrefs = list_index(base, verbose=verbose)
    hours = []
    for h in hrefs:
        h = h.strip("/")
        # match .../ut01/ or ut01/ or ut1/ (end of path)
        m = re.search(r'(?:^|/)ut(\d{1,2})(?:/)?$', h, flags=re.IGNORECASE)
        if m:
            hh = int(m.group(1))
            if 0 <= hh <= 24:
                hours.append(hh)
    hours = sorted(set(hours))
    if verbose:
        print(f"[scraped hours] {(' '.join(f'{x:02d}' for x in hours)) if hours else '(none)'}")
    return hours

def pick_hour_filename(day: dt.date, hour: int, station: str, camera: str) -> Optional[str]:
    """
    Scrape the hour directory and return the RGB composite:
      YYYYMMDD_HH_<site>_<camera>_rgb-keogram.png
    e.g., 20251125_01_pfrr_asi3_rgb-keogram.png
    """
    y, m, d, ymd = ymd_parts(day)
    site = station.split("_", 1)[0]  # 'pfrr' from 'pfrr_amisr01'
    hdir = station_day_url(day, station) + hour_dir(hour)
    hrefs = [h.strip("/") for h in list_index(hdir)]
    if not hrefs:
        return None

    # 1) Exact expected filename (fast path)
    exact = f"{ymd}_{hour:02d}_{site}_{camera}_rgb-keogram.png"
    if exact in hrefs:
        return exact

    # 2) Case-insensitive regex that *requires* "_rgb-keogram.png" at the end,
    #    and includes date, hour, site, and camera in order.
    pat = re.compile(
        rf"^{ymd}_(?:{hour:02d}|{hour})_{re.escape(site)}_{re.escape(camera)}_rgb-keogram\.png$",
        re.IGNORECASE,
    )
    for name in sorted(hrefs):
        if pat.match(name):
            return name

    # No RGB composite found for this hour
    return None

# ---------- download + stitch ----------

def download(url: str, dest: str) -> bool:
    os.makedirs(os.path.dirname(dest), exist_ok=True)

    # 1) Prefer curl (uses macOS keychain; handles redirects; retry a bit)
    if shutil.which("curl"):
        res = subprocess.run(
            ["curl", "-L", "-A", BROWSER_UA, "--retry", "3", "--fail", "-o", dest, url]
        )
        if res.returncode == 0:
            return True

    # 2) Fallback to wget if present
    if shutil.which("wget"):
        # -U sets UA; -O writes to path; -nv = quiet-ish
        res = subprocess.run(["wget", "-nv", "-U", BROWSER_UA, "-O", dest, url])
        if res.returncode == 0:
            return True

    # 3) Last resort: Python requests (after you run the certificate install)
    with requests.get(url, stream=True, timeout=180,
                      headers={"User-Agent": BROWSER_UA}) as r:
        if r.status_code != 200:
            return False
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk)
    return True

def concat_horizontal(paths: List[str], out_path: str) -> None:
    imgs = [Image.open(p).convert("RGB") for p in paths]
    hmin = min(im.height for im in imgs)
    if len({im.height for im in imgs}) > 1:
        fixed = []
        for im in imgs:
            if im.height != hmin:
                nw = int(im.width * (hmin / im.height))
                im = im.resize((nw, hmin), Image.BICUBIC)
            fixed.append(im)
        imgs = fixed
    total_w = sum(im.width for im in imgs)
    canvas = Image.new("RGB", (total_w, imgs[0].height), (0, 0, 0))
    x = 0
    for im in imgs:
        canvas.paste(im, (x, 0))
        x += im.width
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    canvas.save(out_path, "PNG")

# ---------- CLI + prompts ----------

def parse_args():
    p = argparse.ArgumentParser(description="Scrape utHH/ hours, download chosen window, stitch horizontally.")
    p.add_argument("date", nargs="?", help="Date (YYYY-MM-DD, UTC)")
    p.add_argument("--station", default="pfrr_amisr01", help="Station folder (default: pfrr_amisr01)")
    p.add_argument("--camera", default="asi3", help="Camera code (default: asi3)")
    p.add_argument("--out", default=DEFAULT_OUT, help=f"Output root (default: {DEFAULT_OUT})")
    p.add_argument("--keep-segments", action="store_true", help="Keep individual hour PNGs")
    p.add_argument("--dry-run", action="store_true", help="List URLs without downloading")
    p.add_argument("--verbose", action="store_true", help="Print scraped hours and picked files")
    return p.parse_args()

def prompt_first_last(avail: List[int], date: dt.date) -> Tuple[int, int]:
    first, last = avail[0], avail[-1]
    print(f"Available hour window for {date.isoformat()} (UTC): {first:02d}–{last:02d}")
    ds, de = f"{first:02d}", f"{last:02d}"
    s = input(f"Start hour: ").strip() or ds
    e = input(f"End hour: ").strip() or de
    try:
        hs, he = int(s), int(e) - 1
    except ValueError:
        print("Enter hours like 00, 01, …, 23.", file=sys.stderr); sys.exit(3)
    if he < hs:
        print("End hour must be >= start hour.", file=sys.stderr); sys.exit(3)
    if hs not in avail or he not in avail:
        print("Chosen hours must be within the scraped availability.", file=sys.stderr); sys.exit(3)
    return hs, he

def main():
    args = parse_args()
    if not args.date:
        args.date = input("Date (YYYYMMDD): ").strip()
    try:
        day = dt.date.fromisoformat(args.date)
    except Exception:
        print("Invalid date. Use YYYYMMDD.", file=sys.stderr)
        sys.exit(1)

    day_url = station_day_url(day, args.station)
    if args.verbose:
        print(f"[day-url] {day_url}")

    # 1) SCRAPE the day directory to discover hours
    avail = scrape_hours(day, args.station)
    if args.verbose:
        print(f"[scraped hours] {(' '.join(f'{h:02d}' for h in avail)) if avail else '(none)'}")

    if not avail:
        print("No utHH/ folders found in the day directory.", file=sys.stderr)
        sys.exit(2)

    # 2) Prompt (show only first/last)
    hs, he = prompt_first_last(avail, day)

    # 3) For chosen window, scrape each hour dir to get the actual filename
    y, m, _, ymd = ymd_parts(day)
    out_month = os.path.join(args.out, y, m)
    targets: List[Tuple[int, str, str]] = []
    for hh in [h for h in avail if hs <= h <= he]:
        fname = pick_hour_filename(day, hh, args.station, args.camera)
        if not fname:
            if args.verbose:
                print(f"[miss] no keogram PNG found in {station_day_url(day, args.station)+hour_dir(hh)}")
            continue
        url = station_day_url(day, args.station) + hour_dir(hh) + fname
        dest = os.path.join(out_month, fname)
        targets.append((hh, url, dest))
        if args.verbose:
            print(f"[file] {hh:02d} -> {url}")

    if args.dry_run:
        for hh, url, _ in targets:
            print(f"{hh:02d} -> {url}")
        return

    if not targets:
        print("No hourly files to download in the selected window.", file=sys.stderr)
        sys.exit(2)

    # 4) Download
    got = []
    for _, url, dest in targets:
        ok = download(url, dest)
        if ok:
            print(f"[OK ] {dest}")
            got.append(dest)
        else:
            print(f"[404] {url}")

    if not got:
        print("No segments downloaded; nothing to stitch.", file=sys.stderr)
        sys.exit(2)

    # 5) Stitch
    site = args.station.split("_", 1)[0]
    stitched = os.path.join(out_month, f"{ymd}_{hs:02d}-{(he + 1):02d}_{site}_{args.camera}_rgb-keogram_concat.png")
    try:
        concat_horizontal(got, stitched)
        print(f"\n[STITCHED] {stitched}")
    except Exception as e:
        print(f"\n[ERR] stitching failed: {e}", file=sys.stderr)
        sys.exit(3)

    # 6) Cleanup
    if not args.keep_segments:
        for p in got:
            try: os.remove(p)
            except Exception: pass
        print("[CLEAN] removed individual hour segments (kept stitched image).")

if __name__ == "__main__":
    main()
