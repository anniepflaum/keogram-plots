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

# Helper to convert times to hours since midnight
def hours_from_times(times, date_str):
    year, month, day = date_str[:4], date_str[4:6], date_str[6:]
    base = pd.Timestamp(f'{year}-{month}-{day}')
    return np.array([(t - base).total_seconds() / 3600 for t in times])

# Process all partial keogram files
for keo_path in partial_dir.glob('*.png'):
    filename = keo_path.name
    m = re.match(r'(\d{8})__([0-9]{2})-([0-9]{2})_.*partial-keo-rgb\.png', filename)
    if not m:
        print(f"Skipping unrecognized file: {filename}")
        continue

    date_str, start_str, end_str = m.groups()
    start_hour, end_hour = int(start_str), int(end_str)

    # Load keogram image
    keo_array = np.array(Image.open(keo_path))

    # GOES Hp: load, convert, resample to 10s
    nc_goes = goes_dir / f'ops_mag-l1b-flat_g18_d{date_str}_v0-0-0.nc'
    if not nc_goes.exists():
        print(f"No GOES file for {date_str}, skipping...")
        continue
    ds_goes = Dataset(nc_goes, 'r')
    go_times = num2date(ds_goes.variables['OB_time'][:],
                        ds_goes.variables['OB_time'].units,
                        only_use_cftime_datetimes=False)
    he = ds_goes.variables['OB_mag_EPN'][:, 1]
    ds_goes.close()
    goes_df = pd.DataFrame({'time': go_times, 'he': he}).dropna()
    go_df = goes_df.set_index('time').resample('10s').mean()
    go_df['hour'] = hours_from_times(go_df.index, date_str)
    win_go = go_df[(go_df['hour'] >= start_hour) & (go_df['hour'] < end_hour)]

    # ACE Bz: load, convert, resample to 10s
    ace_pattern = f'*dscovr_s{date_str}*_pub.nc.gz'
    ace_file = next(ace_dir.glob(ace_pattern), None)
    ace_h = bz_vals = None
    if ace_file:
        try:
            with gzip.open(ace_file, 'rb') as gz, tempfile.NamedTemporaryFile(delete=False, suffix='.nc') as tmp:
                tmp.write(gz.read())
                tmp_path = tmp.name
            ds_ace = Dataset(tmp_path, 'r')
            ace_times = num2date(ds_ace.variables['time'][:],
                                 ds_ace.variables['time'].units,
                                 only_use_cftime_datetimes=False)
            bz = ds_ace.variables['bz_gse'][:]
            ds_ace.close()
            os.remove(tmp_path)
            ace_df = pd.DataFrame({'time': pd.to_datetime(ace_times), 'bz': bz}).dropna()
            ace_df = ace_df.set_index('time').resample('10s').mean()
            ace_df['hour'] = hours_from_times(ace_df.index, date_str)
            win_ace = ace_df[(ace_df['hour'] >= start_hour) & (ace_df['hour'] < end_hour)]
            ace_h, bz_vals = win_ace['hour'].values, win_ace['bz'].values
        except Exception as e:
            print(f"Failed ACE for {date_str}: {e}")

    # Plotting
    fig, ax1 = plt.subplots(figsize=(10, 5))
    ax1.imshow(keo_array, aspect='auto', extent=[start_hour, end_hour, 0, 1])
    ax1.set_xlim(start_hour, end_hour)
    ax1.set_ylim(0, 1)
    ax1.axis('off')
    xt = np.arange(start_hour, end_hour + 0.01, 0.25)
    ax1.set_xticks(xt)
    ax1.set_xticklabels([f"{int(h):02d}:{int((h%1)*60):02d}" for h in xt])
    ax1.set_xlabel('Time (UTC)')

    ax2 = ax1.twinx()
    ax2.plot(win_go['hour'], win_go['he'], color='orange', linewidth=2, label='GOES Hp')
    ax2.set_ylabel('Hp (nT)', color='orange')
    ax2.tick_params(axis='y', labelcolor='orange')
    ax2.set_xlim(start_hour, end_hour)
    go_min, go_max = np.nanmin(he), np.nanmax(he)
    ax2.set_ylim(min(0, go_min), max(130, go_max))

    if ace_h is not None and len(bz_vals) > 0:
        ax3 = ax1.twinx()
        ax3.spines['right'].set_position(('outward', 60))
        ax3.plot(ace_h, bz_vals, color='darkblue', linewidth=1.5, label='ACE Bz')
        ax3.set_ylabel('Bz GSE (nT)', color='darkblue')
        ax3.tick_params(axis='y', labelcolor='darkblue')
        ax3.set_xlim(start_hour, end_hour)
        ac_min, ac_max = ace_df['bz'].min(), ace_df['bz'].max()
        ax3.set_ylim(min(-15, ac_min), max(15, ac_max))
        ax3.axhline(0, linestyle='--', linewidth=1, color='darkblue')

    plt.title(f'{date_str} {start_str}-{end_str} UTC')
    plt.tight_layout()
    out_file = save_dir / f'{date_str}_{start_str}-{end_str}_overlaid_partial_plot.png'
    plt.savefig(out_file, dpi=300)
    plt.close()
    print(f"Saved {out_file}")
