#!/usr/bin/env python3
import os, re, requests, shutil, subprocess, gzip, tempfile, sys
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from netCDF4 import Dataset, num2date
from PIL import Image

# ---- Config ----
FULL_KEO_DIR     = Path('/Users/anniepflaum/Documents/keogram_project/full_keograms')
PARTIAL_KEO_DIR  = Path('/Users/anniepflaum/Documents/keogram_project/partial_keograms')
GOES_DIR         = Path('/Users/anniepflaum/Documents/keogram_project/GOES_data')
DSCOVR_DIR       = Path('/Users/anniepflaum/Documents/keogram_project/DSCOVR_data')
OUT_FULL_ROOT    = Path('/Users/anniepflaum/Documents/keogram_project/overlaid_full')
OUT_PARTIAL_ROOT = Path('/Users/anniepflaum/Documents/keogram_project/overlaid_partial')
for p in (OUT_FULL_ROOT, OUT_PARTIAL_ROOT):
    p.mkdir(parents=True, exist_ok=True)

AMISR_URL = 'https://optics.gi.alaska.edu/amisr_archive/Processed_data/aurorax/stream2/{year}/{month}/{day}/pfrr_amisr01/'
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/120.0.0.0 Safari/537.36")

# ---- Helpers ----
def _parse_date_any(s: str) -> datetime:
    s = s.strip()
    if re.fullmatch(r"\d{8}", s):
        return datetime.strptime(s, "%Y%m%d")
    return datetime.strptime(s, "%Y-%m-%d")

def hours_from_partial_name(p: Path):
    """
    Parse _HH-HH_ from partial keogram filename and return (start, end_exclusive).
    e.g., _01-17_ -> (1, 18)
    """
    m = re.search(r'_(\d{1,2})-(\d{1,2})_', p.name)
    if not m:
        raise ValueError(f"Cannot parse hour window from: {p.name}")
    h0, h1 = int(m.group(1)), int(m.group(2))
    return h0, h1

def list_index(url: str) -> str:
    html = ""
    try:
        r = requests.get(url, headers={"User-Agent": BROWSER_UA}, timeout=30)
        if r.status_code == 200:
            html = r.text
    except Exception:
        pass
    if (not html or "href" not in (html.lower() if html else "")) and shutil.which("curl"):
        res = subprocess.run(["curl", "-sL", "-A", BROWSER_UA, url],
                             check=False, capture_output=True, text=True)
        if res.returncode == 0:
            html = res.stdout or ""
    return html

def scrape_time_bounds(year: str, month: str, day: str):
    """
    Return (first_hour, last_hour_exclusive) by scraping utHH/ folders.
    """
    url = AMISR_URL.format(year=year, month=month, day=day)
    html = list_index(url)
    if not html:
        raise RuntimeError("Could not fetch AMISR directory listing.")
    soup = BeautifulSoup(html, "html.parser")
    hours = []
    for a in soup.find_all("a"):
        href = (a.get("href") or "").strip("/")
        m = re.fullmatch(r"ut(\d{1,2})/?", href, flags=re.IGNORECASE)
        if m:
            hh = int(m.group(1))
            if 0 <= hh <= 24:
                hours.append(hh)
    if not hours:
        raise RuntimeError("No utHH/ folders found on the AMISR day page.")
    hours = sorted(set(hours))
    return hours[0], hours[-1] + 1

def open_goes_series(goes_path: Path, year: str, month: str, day: str):
    ds = Dataset(goes_path, "r")
    if 'OB_time' not in ds.variables:
        ds.close()
        raise KeyError("GOES missing OB_time")
    if 'OB_mag_EPN' not in ds.variables:
        ds.close()
        raise KeyError("GOES missing OB_mag_EPN")
    t = num2date(ds.variables['OB_time'][:], ds.variables['OB_time'].units)
    hours = np.array([
        (np.datetime64(tt) - np.datetime64(f'{year}-{month}-{day}T00:00'))
        .astype('timedelta64[s]').astype(float) / 3600 for tt in t
    ])
    hp = ds.variables['OB_mag_EPN'][:, 1]  # Hp
    ds.close()
    return hours, hp

def open_dscovr_series(dsc_path: Path, year: str, month: str, day: str):
    with gzip.open(dsc_path, 'rb') as gz, tempfile.NamedTemporaryFile(delete=False, suffix='.nc') as tmp:
        shutil.copyfileobj(gz, tmp)
        tmp_name = tmp.name
    try:
        ds = Dataset(tmp_name, "r")
        if 'time' not in ds.variables or 'bz_gse' not in ds.variables:
            ds.close()
            raise KeyError("DSCOVR missing time or bz_gse")
        t = num2date(ds.variables['time'][:], ds.variables['time'].units,
                     only_use_cftime_datetimes=False)
        bz = ds.variables['bz_gse'][:]
        ds.close()
    finally:
        try: os.remove(tmp_name)
        except Exception: pass
    df = (pd.DataFrame({'time': pd.to_datetime(t), 'bz': bz})
            .dropna()
            .set_index('time')
            .resample('1min').mean())
    df['hour'] = (df.index - pd.Timestamp(f'{year}-{month}-{day}')).total_seconds()/3600
    return df

def find_file(root: Path, year: str, month: str, pattern: str):
    """Try YYYY/MM first, then rglob as fallback. Returns Path|None."""
    sub = root / year / month
    m = next(sub.glob(pattern), None)
    if m: return m
    return next(root.rglob(pattern), None)

# ---- Core ----
def process_date(date_str: str, mode: str):
    # date bits
    year, month, day = date_str[:4], date_str[4:6], date_str[6:]

    if mode == "partial":
        keo_root = PARTIAL_KEO_DIR
        out_root = OUT_PARTIAL_ROOT
        # Find the partial keogram file (stitched)
        keo_file = find_file(keo_root, year, month, f"*{date_str}*keogram*png")
        if not keo_file:
            print(f"[MISS] partial keogram not found for {date_str}")
            return
        # Hours from filename
        first_h, last_h = hours_from_partial_name(keo_file)

        # Load image (already stitched for the window)
        keo = np.array(Image.open(keo_file))

    else:  # full
        keo_root = FULL_KEO_DIR
        out_root = OUT_FULL_ROOT
        # Find the full keogram file
        # Prefer names containing 'full-keo'
        keo_file = find_file(keo_root, year, month, f"*{date_str}*full*keo*png") \
                   or find_file(keo_root, year, month, f"*{date_str}*keo*png")
        if not keo_file:
            print(f"[MISS] full keogram not found for {date_str}")
            return
        # Hours by scraping AMISR day page
        try:
            first_h, last_h = scrape_time_bounds(year, month, day)
            last_h = last_h
        except Exception as e:
            print(f"[MISS] could not scrape time range for {date_str}: {e}")
            return

        # Load and physically crop image to [first_h, last_h)
        img = np.array(Image.open(keo_file))
        W = img.shape[1]
        x0 = int(W * (first_h / 24.0))
        x1 = int(W * (last_h  / 24.0))
        x0 = max(0, min(W, x0))
        x1 = max(0, min(W, x1))
        if x1 <= x0:  # safety
            x1 = min(W, x0 + 1)
        keo = img[:, x0:x1]    

    # Find GOES & DSCOVR
    goes_file   = find_file(GOES_DIR, year, month,   f"*d{date_str}_v*.nc")
    dscovr_file = find_file(DSCOVR_DIR, year, month, f"*dscovr_s{year}{month}{day}*pub.nc.gz") \
                  or find_file(DSCOVR_DIR, year, month, f"*dscovr_s{year}{month}{day}*pub.nc")
    if not (goes_file and dscovr_file):
        print(f"[MISS] data missing for {date_str}  GOES:{bool(goes_file)}  DSCOVR:{bool(dscovr_file)}")
        return

    # Load and crop series to [first_h, last_h)
    try:
        gh, hp = open_goes_series(goes_file, year, month, day)
    except Exception as e:
        print(f"[MISS] GOES read failed for {date_str}: {e}")
        return
    gmask = (gh >= first_h) & (gh < last_h)
    gh, hp = gh[gmask], hp[gmask]

    try:
        df = open_dscovr_series(dscovr_file, year, month, day)
    except Exception as e:
        print(f"[MISS] DSCOVR read failed for {date_str}: {e}")
        return
    df = df[(df['hour'] >= first_h) & (df['hour'] < last_h)]

    # ---- Plot ----
    fig, ax1 = plt.subplots(figsize=(12, 6))
    # Map keogram to the same hour window
    ax1.imshow(keo, aspect='auto', extent=[first_h, last_h, 0, 1])
    ax1.set_xlim(first_h, last_h)
    ax1.set_ylim(0, 1)
    ax1.tick_params(left=False, labelleft=False)
    ax1.spines['left'].set_visible(False)
    ax1.set_xticks(np.arange(first_h, last_h + 1))
    ax1.set_xlabel('Time (Hours UTC)')

    # GOES Hp
    ax2 = ax1.twinx()
    if gh.size:
        ax2.plot(gh, hp, color="#f28e2b")  # GOES in orange
        go_min, go_max = np.nanmin(hp), np.nanmax(hp)
        ax2.set_ylim(min(0, go_min), max(130, go_max))
    ax2.set_ylabel('Hp (nT)')
    ax2.set_xlim(first_h, last_h)

    # DSCOVR Bz
    ax3 = ax1.twinx()
    ax3.spines['right'].set_position(('outward', 60))
    if not df.empty:
        ax3.plot(df['hour'], df['bz'], linewidth=1.5, color="#1f77b4")  # DSCOVR in blue
        bz_min, bz_max = df['bz'].min(), df['bz'].max()
        ax3.set_ylim(min(-15, bz_min), max(15, bz_max))
    ax3.set_ylabel('Bz GSE (nT)')
    ax3.set_xlim(first_h, last_h)
    ax3.axhline(0, linestyle='--', linewidth=1, alpha=0.7)

    plt.title(f'GOES-18 Hp and DSCOVR Bz over Keogram: {date_str}')
    plt.tight_layout()

    # Save
    out_root = OUT_PARTIAL_ROOT if mode == "partial" else OUT_FULL_ROOT
    out_dir  = out_root / year / month
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{date_str}_overlaid_plot.png"
    plt.savefig(out_file, dpi=300)
    plt.close()
    print(f"[SAVED] {out_file}")

# ---- CLI ----
if __name__ == "__main__":
    mode_in = input("Keogram type ('full'/'f' or 'partial'/'p'): ").strip().lower()
    if mode_in not in ("full", "partial", "f", "p"):
        print("Please enter 'full' or 'partial'.", file=sys.stderr)
        sys.exit(1)
    mode = "full" if mode_in.startswith("f") else "partial"

    start_in = input("Start date (YYYY-MM-DD or YYYYMMDD): ").strip()
    end_in   = input("End date   (YYYY-MM-DD or YYYYMMDD): ").strip()

    try:
        d0 = _parse_date_any(start_in)
        d1 = _parse_date_any(end_in)
    except Exception as e:
        print(f"[ERR] Bad date format: {e}", file=sys.stderr)
        sys.exit(1)
    if d1 < d0:
        print("[ERR] End date must be >= start date.", file=sys.stderr)
        sys.exit(1)

    cur = d0
    while cur <= d1:
        process_date(cur.strftime("%Y%m%d"), mode)
        cur += timedelta(days=1)
