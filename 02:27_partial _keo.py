import os
import re
import matplotlib.pyplot as plt
import numpy as np
from netCDF4 import Dataset, num2date
from PIL import Image
import gzip
import tempfile
import pandas as pd
from pathlib import Path

# Directories
partial_dir = Path('/Users/anniepflaum/Documents/keogram_project/partial_keograms')
goes_dir    = Path('/Users/anniepflaum/Documents/keogram_project/GOES_18_data')
ace_dir     = Path('/Users/anniepflaum/Documents/keogram_project/ACE_data')
save_dir    = Path('/Users/anniepflaum/Documents/keogram_project/overlaid_partial_plots')
save_dir.mkdir(parents=True, exist_ok=True)

# Fixed date and time window
date_str = '20250227'
start_hour, end_hour = 8, 12

# Helper: convert times to hours since midnight
base = pd.Timestamp(f'{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}')
def hours_from_times(times):
    return np.array([(t - base).total_seconds() / 3600 for t in times])

# Find matching partial keograms for the date
pattern = re.compile(rf'{date_str}__([0-9]{{2}})-([0-9]{{2}})_.*partial-keo-rgb\.png')
for keo_path in partial_dir.glob(f'{date_str}__*.png'):
    m = pattern.match(keo_path.name)
    if not m:
        continue

    # Load image
    keo_array = np.array(Image.open(keo_path))

    # GOES Hp data
    nc_goes = goes_dir / f'ops_mag-l1b-flat_g18_d{date_str}_v0-0-0.nc'
    if not nc_goes.exists():
        print(f'No GOES file for {date_str}')
        continue
    ds_goes = Dataset(nc_goes, 'r')
    go_times = num2date(ds_goes.variables['OB_time'][:],
                        ds_goes.variables['OB_time'].units,
                        only_use_cftime_datetimes=False)
    he = ds_goes.variables['OB_mag_EPN'][:, 1]
    ds_goes.close()
    goes_df = pd.DataFrame({'time': go_times, 'he': he}).dropna()
    go_df = goes_df.set_index('time').resample('10s').mean()
    go_df['hour'] = hours_from_times(go_df.index)
    win_go = go_df[(go_df['hour'] >= start_hour) & (go_df['hour'] < end_hour)]

    # ACE Bz data
    ace_pattern = f'*dscovr_s{date_str}*_pub.nc.gz'
    ace_file = next(ace_dir.glob(ace_pattern), None)
    ace_h = bz_vals = None
    if ace_file:
        with gzip.open(ace_file, 'rb') as gz, tempfile.NamedTemporaryFile(delete=False, suffix='.nc') as tmp:
            tmp.write(gz.read()); tmp_path = tmp.name
        ds_ace = Dataset(tmp_path, 'r')
        ace_times = num2date(ds_ace.variables['time'][:],
                             ds_ace.variables['time'].units,
                             only_use_cftime_datetimes=False)
        bz = ds_ace.variables['bz_gse'][:]
        ds_ace.close(); os.remove(tmp_path)
        ace_df = pd.DataFrame({'time': ace_times, 'bz': bz}).dropna()
        ace_df = ace_df.set_index('time').resample('10s').mean()
        ace_df['hour'] = hours_from_times(ace_df.index)
        win_ace = ace_df[(ace_df['hour'] >= start_hour) & (ace_df['hour'] < end_hour)]
        ace_h, bz_vals = win_ace['hour'].values, win_ace['bz'].values

    # Plotting
    fig, ax1 = plt.subplots(figsize=(10, 5))
    ax1.imshow(keo_array, aspect='auto', extent=[start_hour, end_hour, 0, 1])
    ax1.set_xlim(start_hour, end_hour); ax1.set_ylim(0, 1)
    # hide only left/right y-axis; keep x-axis visible
    ax1.spines['left'].set_visible(False)
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)
    ax1.tick_params(axis='y', left=False, labelleft=False)
    # ticks every 30 minutes (0.5 hours)
    xt = np.arange(start_hour, end_hour + 1e-6, 0.5)
    ax1.set_xticks(xt)
    ax1.set_xticklabels([f"{int(h):02d}:{int((h%1)*60):02d}" for h in xt])
    ax1.set_xlabel('Time (UTC)')

    # GOES overlay
    ax2 = ax1.twinx()
    ax2.plot(win_go['hour'], win_go['he'], color='orange', linewidth=2)
    ax2.set_ylabel("Northward component of Earth's magnetic field, Hp (nT)", color='orange'); ax2.tick_params(axis='y', labelcolor='orange')
    ax2.set_xlim(start_hour, end_hour)

    # ACE overlay
    if ace_h is not None and len(bz_vals) > 0:
        ax3 = ax1.twinx(); ax3.spines['right'].set_position(('outward', 60))
        ax3.plot(ace_h, bz_vals, color='darkblue', linewidth=1.5)
        ax3.set_ylabel('Northward component of solar wind, Bz (nT)', color='darkblue'); ax3.tick_params(axis='y', labelcolor='darkblue')
        ax3.set_xlim(start_hour, end_hour); ax3.set_ylim(-15, 15)
        ax3.axhline(0, linestyle='--', linewidth=1, color='darkblue')

    plt.title(f'Keogram, magnetic field, and solar wind for 02/27/25')
    plt.tight_layout()
    out_file = save_dir / f'{date_str}_{start_hour:02d}-{end_hour:02d}_overlaid_partial_plot.png'
    plt.savefig(out_file, dpi=300); plt.close()
    print(f'Saved {out_file}')
