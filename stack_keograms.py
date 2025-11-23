#!/usr/bin/env python3
"""
Script to stack keogram images vertically by date, resizing each image to a 10:1 aspect ratio
and grouping outputs by month.

This script looks for files named like YYYYMMDD__pfrr_asi3_full-keo-rgb.png in a given folder,
sorts them into monthly groups based on the YYYYMM prefix, resizes each image (width = 10×height),
and concatenates each month’s images into its own tall image named stacked_keograms_YYYYMM.png.
"""
import os
import glob
import re
from PIL import Image, ImageDraw

def stack_keograms_by_month(folder_path,
                             pattern="*__pfrr_asi3_full-keo-rgb.png",
                             output_dir=None):
    # Determine files
    search_pattern = os.path.join(folder_path, pattern)
    file_paths = sorted(glob.glob(search_pattern))
    if not file_paths:
        print(f"No files found for pattern {search_pattern}")
        return

    # Group by year-month (YYYYMM)
    groups = {}
    for fp in file_paths:
        fname = os.path.basename(fp)
        m = re.match(r"(\d{4})(\d{2})\d{2}__.*\.png$", fname)
        if not m:
            continue
        ym = f"{m.group(1)}{m.group(2)}"
        groups.setdefault(ym, []).append(fp)

    # Prepare output directory
    if output_dir is None:
        output_dir = folder_path
    os.makedirs(output_dir, exist_ok=True)

    # Process each month
    for ym in sorted(groups.keys()):
        fps = sorted(groups[ym])
        images = []
        for fp in fps:
            im = Image.open(fp)
            h = im.height
            new_w = 10 * h  # enforce 10:1 aspect
            im = im.resize((new_w, h), Image.LANCZOS)
            images.append(im)

        # Compute stacked canvas size
        widths, heights = zip(*(im.size for im in images))
        max_width = max(widths)
        total_height = sum(heights)

        # Create blank canvas and paste images
        stacked = Image.new('RGB', (max_width, total_height))
        y_offset = 0
        for im in images:
            if im.width < max_width:
                padded = Image.new('RGB', (max_width, im.height), (0, 0, 0))
                padded.paste(im, (0, 0))
                im = padded
            stacked.paste(im, (0, y_offset))
            y_offset += im.height

        # Draw vertical UTC reference lines at 6 and 12 hours on top of images
        draw = ImageDraw.Draw(stacked)
        for hour in (6, 12):
            x = int(max_width * (hour / 24.0))
            draw.line((x, 0, x, total_height), fill='white', width=10)

        out_path = os.path.join(output_dir, f"stacked_keograms_{ym}.png")
        stacked.save(out_path)
        print(f"Saved stacked image for {ym} to {out_path}")

if __name__ == '__main__':
    keo_folder = '/Users/anniepflaum/Documents/keogram_project/full_keograms'
    out_dir = '/Users/anniepflaum/Documents/keogram_project/stacked_by_month'
    stack_keograms_by_month(keo_folder, output_dir=out_dir)
