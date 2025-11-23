import os
import re
from PIL import Image
import numpy as np
from collections import defaultdict

# Paths
input_dir = '/Users/anniepflaum/Documents/keogram_project/partial_keograms'
output_dir = '/Users/anniepflaum/Documents/keogram_project/partial_keograms'
os.makedirs(output_dir, exist_ok=True)

# Group partial keograms by date
keogram_groups = defaultdict(list)

for fname in os.listdir(input_dir):
    if not fname.endswith('.png'):
        continue

    match = re.match(r'(\d{8})_(\d{2})_pfrr_asi3_rgb-keogram\.png', fname)
    if not match:
        print(f"Skipping unrecognized file: {fname}")
        continue

    date_str, hour_str = match.groups()
    keogram_groups[date_str].append((int(hour_str), fname))

# Combine per day
for date_str, files in keogram_groups.items():
    files.sort()  # Sort by hour
    slices = []

    for hour, fname in files:
        img_path = os.path.join(input_dir, fname)
        img = Image.open(img_path).convert('RGB')
        slices.append(np.array(img))

    # Check all images have same height
    heights = {img.shape[0] for img in slices}
    if len(heights) > 1:
        print(f"Warning: Image heights differ for {date_str}")
    
    full_keogram = np.hstack(slices)
    combined_image = Image.fromarray(full_keogram)

    out_fname = f"{date_str}__pfrr_asi3_partial-keo-rgb.png"
    out_path = os.path.join(output_dir, out_fname)
    combined_image.save(out_path)

    print(f"Saved partial keogram for {date_str}: {out_path}")
