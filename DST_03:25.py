import pandas as pd
from pathlib import Path
import matplotlib.pyplot as plt
from PIL import Image


def load_dst_quicklook(file_path: str | Path, year: int, month: int) -> pd.Series:
    """Return a pandas Series with hourly quick-look Dst for the given YYYY-MM file."""
    records = []
    with open(file_path, "r") as f:
        for line in f:
            if not line.startswith("DST2"):
                continue  # skip footer / blank lines

            day = int(line[8:10])
            nums = line[16:].strip().split()
            hourly = [int(x) for x in nums[1:25]]  # drop daily mean, keep 24 hrs
            records.append([day] + hourly)

    df = pd.DataFrame(records, columns=["DAY"] + [f"{h:02d}" for h in range(24)])
    long = (
        df.melt(id_vars="DAY", var_name="HOUR", value_name="Dst")
          .astype(int)
    )
    long["Time"] = pd.to_datetime(
        {"year": year, "month": month, "day": long["DAY"], "hour": long["HOUR"]}
    )
    return long.set_index("Time")["Dst"]


# -----------------------------------------------------------------------------
#  USER‑CONFIGURABLE PARAMETERS
# -----------------------------------------------------------------------------
YEAR        = 2025
MONTH       = 3
SRC_FILE    = Path("/Users/anniepflaum/Documents/keogram_project/dst2503.for.request")
OUT_DIR     = Path("/Users/anniepflaum/Documents/keogram_project/stacked_by_month")
KEOGRAM_PNG = OUT_DIR / "stacked_keograms_202503.png"  # adjust if different

#  Fraction of the *height* that the Dst strip should occupy in width.
STRIP_WIDTH_RATIO_H = 0.2
DPI = 300  # change if memory‑limited

# Fonts & styling
TICK_FONT  = 24
LINE_WIDTH = 5.0

# -----------------------------------------------------------------------------
#  HOUSEKEEPING
# -----------------------------------------------------------------------------
OUT_DIR.mkdir(parents=True, exist_ok=True)
VERTICAL_PNG = OUT_DIR / f"dst_{YEAR}{MONTH:02d}_vertical.png"
COMBO_PNG    = OUT_DIR / f"keogram_plus_dst_{YEAR}{MONTH:02d}.png"

# -----------------------------------------------------------------------------
#  LOAD DATA & KEOGRAM
# -----------------------------------------------------------------------------
dst = load_dst_quicklook(SRC_FILE, YEAR, MONTH).sort_index()
keo = Image.open(KEOGRAM_PNG)
keo_h_px, keo_w_px = keo.height, keo.width

# -----------------------------------------------------------------------------
#  FIGURE SIZE FROM HEIGHT RATIO
# -----------------------------------------------------------------------------
strip_w_px = int(keo_h_px * STRIP_WIDTH_RATIO_H)
fig_w_in, fig_h_in = strip_w_px / DPI, keo_h_px / DPI

fig, ax = plt.subplots(figsize=(fig_w_in, fig_h_in), dpi=DPI)

# -----------------------------------------------------------------------------
#  PLOT DST STRIP
# -----------------------------------------------------------------------------
ax.plot(dst.values, dst.index, lw=LINE_WIDTH, color="royalblue")
ax.margins(y=0)
ax.invert_yaxis()
ax.set_ylim(dst.index.max(), dst.index.min())

# --- X‑axis ticks in axis ----------------------------------------------------
ax.tick_params(axis='x', labeltop=False, labelbottom=True,
               labelsize=TICK_FONT, width=1.5, length=12, direction='in', pad=-40)

# Remove axis label entirely
ax.set_xlabel("")

# Y‑axis hidden
ax.yaxis.set_visible(False)

# Guide line at 0 nT
ax.axvline(0, ls="--", lw=5, color="blue")

ax.grid(axis="x", alpha=0.25, lw=0.6)
fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

fig.savefig(VERTICAL_PNG, dpi=DPI)
plt.close(fig)
print(f"Dst strip saved → {VERTICAL_PNG}  ({strip_w_px}px × {keo_h_px}px)")

# -----------------------------------------------------------------------------
#  CONCATENATE (OPTIONAL)
# -----------------------------------------------------------------------------
strip_img = Image.open(VERTICAL_PNG)
combo = Image.new("RGB", (strip_img.width + keo_w_px, keo_h_px), (255, 255, 255))
combo.paste(strip_img, (0, 0))
combo.paste(keo, (strip_img.width, 0))
combo.save(COMBO_PNG)
print(f"Composite saved → {COMBO_PNG}")
