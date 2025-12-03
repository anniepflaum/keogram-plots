#!/usr/bin/env python3
import os
import glob
import re
from datetime import datetime

import numpy as np
from PIL import Image

# <<< CHANGE THIS IF NEEDED >>>
BASE_DIR = "/Users/anniepflaum/Documents/keogram_project/all_sky/pkr_png_20251103_02/PNG/2025/20251103/02"

# Map wavelengths to RGB channels
WAVES_TO_RGB = {
    "0630": "R",  # red
    "0558": "G",  # green
    "0428": "B",  # blue
}

# seconds within which we consider frames "close enough" to be a triplet
TIME_TOLERANCE_SECONDS = 20


def parse_files(base_dir):
    """
    Parse all PNGs in base_dir into a dict:
      {wave: [(datetime, path), ...]} sorted by time.
    """
    pattern = os.path.join(base_dir, "*.png")
    files = glob.glob(pattern)

    regex = re.compile(r"PFRR_(\d{8})_(\d{6})_(\d{4})\.png$", re.IGNORECASE)

    by_wave = {}

    for f in files:
        name = os.path.basename(f)
        m = regex.match(name)
        if not m:
            continue
        datestr, timestr, wave = m.groups()
        # only keep waves we care about
        if wave not in WAVES_TO_RGB:
            continue

        dt = datetime.strptime(datestr + timestr, "%Y%m%d%H%M%S")
        by_wave.setdefault(wave, []).append((dt, f))

    # sort by time
    for wave in by_wave:
        by_wave[wave].sort(key=lambda x: x[0])

    return by_wave


def find_nearest(target_time, records):
    """
    Given a target datetime and a sorted list of (time, path),
    return (dt, path, |Δt|) for the nearest record, or None if list empty.
    """
    if not records:
        return None

    # linear scan is fine for now
    best = None
    best_dt = None
    best_path = None
    best_diff = None

    for dt, path in records:
        diff = abs((dt - target_time).total_seconds())
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_dt = dt
            best_path = path

    return best_dt, best_path, best_diff


def normalize(img_array):
    """
    Simple per-channel normalization: scale to [0,1].
    """
    img = img_array.astype(float)
    vmin = np.nanmin(img)
    vmax = np.nanmax(img)
    if vmax <= vmin:
        return np.zeros_like(img)
    return (img - vmin) / (vmax - vmin)


def main():
    base_dir = os.path.expanduser(BASE_DIR)

    by_wave = parse_files(base_dir)
    print("Waves found:")
    for wave, recs in by_wave.items():
        print(f"  {wave}: {len(recs)} frames")

    # require all three waves to exist
    required_waves = set(WAVES_TO_RGB.keys())
    if not required_waves.issubset(by_wave.keys()):
        print("Not all required wavelengths are present in this directory.")
        return

    # Use 0558 as the reference sequence (green)
    center_wave = "0558"
    center_records = by_wave[center_wave]

    if not center_records:
        print("No frames for center wavelength 0558.")
        return

    # Just take the first 0558 frame
    center_time, center_path = center_records[0]
    print(f"\nCenter frame (0558): {center_path} at {center_time}")

    # Find nearest 0428 and 0630 to this time
    triplet_paths = {center_wave: center_path}

    for wave in ("0428", "0630"):
        dt, path, diff = find_nearest(center_time, by_wave[wave])
        if dt is None:
            print(f"No frames for wave {wave}.")
            return
        print(f"Nearest {wave}: {path} at {dt} (Δt = {diff:.1f} s)")
        if diff > TIME_TOLERANCE_SECONDS:
            print(f"Δt for wave {wave} is > {TIME_TOLERANCE_SECONDS} s; "
                  f"not building a triplet.")
            return
        triplet_paths[wave] = path

    # Load and normalize each channel
    channels = {}
    shape = None

    for wave, path in triplet_paths.items():
        im = Image.open(path).convert("L")
        arr = np.array(im)
        arr_norm = normalize(arr)
        channels[wave] = arr_norm
        if shape is None:
            shape = arr_norm.shape
        elif arr_norm.shape != shape:
            raise ValueError(f"Shape mismatch for wave {wave}: "
                             f"{arr_norm.shape} vs {shape}")

    H, W = shape
    rgb = np.zeros((H, W, 3), dtype=float)

    for wave, arr in channels.items():
        ch = WAVES_TO_RGB[wave]
        if ch == "R":
            rgb[..., 0] = arr
        elif ch == "G":
            rgb[..., 1] = arr
        elif ch == "B":
            rgb[..., 2] = arr

    rgb_uint8 = (np.clip(rgb, 0, 1) * 255).astype(np.uint8)
    out_img = Image.fromarray(rgb_uint8, mode="RGB")

    # Build a representative name using the center time
    stem = center_time.strftime("PFRR_%Y%m%d_%H%M%S")
    out_name = f"{stem}_RGB_composite.png"
    out_path = os.path.join(base_dir, out_name)
    out_img.save(out_path)

    print(f"\nSaved composite frame to:\n  {out_path}")


if __name__ == "__main__":
    main()
