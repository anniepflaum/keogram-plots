#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime, timezone, date
from collections import deque
import re

import cv2
import pytesseract
from PIL import Image

# --- Adjust this to your video path ---
VIDEO_PATH = Path(
    "/Users/anniepflaum/Documents/keogram_project/all_sky_vids/PKR_DASC_20251103_rgb_512.mp4"
)

# Full datetime pattern like "2025/11/03 ... 02:12:26"
DATETIME_REGEX = re.compile(
    r"(\d{4})[/-](\d{2})[/-](\d{2}).*?(\d{2}):(\d{2}):(\d{2})",
    re.S,  # DOTALL so it can cross newlines
)

# Time-only pattern like "16:55:36"
TIME_REGEX = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})"
)


def parse_timestamp_from_text(text: str, label: str, fallback_date: date | None):
    """
    Try to parse a full 'YYYY/MM/DD ... HH:MM:SS' first.
    If that fails and fallback_date is provided, try 'HH:MM:SS' and
    combine with fallback_date.
    """
    text = text.strip()
    print(f"OCR text ({label}):", repr(text))

    # 1) full datetime
    m = DATETIME_REGEX.search(text)
    if m:
        year, month, day, hh, mm, ss = map(int, m.groups())
        return datetime(year, month, day, hh, mm, ss, tzinfo=timezone.utc)

    # 2) time-only, if we know the date already
    if fallback_date is not None:
        mt = TIME_REGEX.search(text)
        if mt:
            hh, mm, ss = map(int, mt.groups())
            return datetime(
                fallback_date.year,
                fallback_date.month,
                fallback_date.day,
                hh, mm, ss,
                tzinfo=timezone.utc,
            )

    return None


def extract_timestamp_from_frame(frame, label: str = "", fallback_date: date | None = None):
    """
    Try full-frame OCR first; if that fails for datetime, fall back to
    time-only using fallback_date.
    Then, if still no luck, try bottom-left ROI and repeat.
    """
    h, w = frame.shape[:2]

    # --- full frame OCR ---
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    pil_full = Image.fromarray(rgb)
    text_full = pytesseract.image_to_string(pil_full)
    dt = parse_timestamp_from_text(text_full, label + " full", fallback_date)
    if dt is not None:
        return dt

    # --- bottom-left ROI fallback ---
    left_frac = 0.02
    right_frac = 0.55
    top_frac = 0.82
    bottom_frac = 0.98

    x0 = int(left_frac * w)
    x1 = int(right_frac * w)
    y0 = int(top_frac * h)
    y1 = int(bottom_frac * h)

    crop = frame[y0:y1, x0:x1]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    pil_crop = Image.fromarray(thresh)
    text_crop = pytesseract.image_to_string(pil_crop)
    dt = parse_timestamp_from_text(text_crop, label + " crop", fallback_date)
    return dt


def date_from_filename(path: Path) -> date | None:
    """
    Extract YYYYMMDD from something like PKR_DASC_20251103_rgb_512.mp4
    """
    m = re.search(r"(\d{4})(\d{2})(\d{2})", path.name)
    if not m:
        return None
    y, mth, d = map(int, m.groups())
    return date(y, mth, d)


def main():
    if not VIDEO_PATH.exists():
        raise FileNotFoundError(VIDEO_PATH)

    cap = cv2.VideoCapture(str(VIDEO_PATH))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video {VIDEO_PATH}")

    first_frame = None
    tail_frames = deque(maxlen=80)  # last ~80 frames

    n = 0
    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            break
        n += 1

        if first_frame is None:
            first_frame = frame.copy()

        tail_frames.append(frame.copy())

        if n % 500 == 0:
            print(f"Read {n} frames...")

    cap.release()
    print(f"Total frames successfully read: {n}")

    # --- start timestamp from first frame ---
    ts_start = None
    if first_frame is not None:
        ts_start = extract_timestamp_from_frame(first_frame, label="start", fallback_date=None)

    # Determine fallback date for the end:
    # prefer the date from ts_start; if that fails, use filename.
    fallback_date = ts_start.date() if ts_start else date_from_filename(VIDEO_PATH)

    # --- end timestamp: search backwards through tail_frames ---
    ts_end = None
    for idx, f in enumerate(reversed(tail_frames)):
        label = f"end_tail[{idx}]"
        ts = extract_timestamp_from_frame(f, label=label, fallback_date=fallback_date)
        if ts is not None:
            ts_end = ts
            break

    print("\n=== Results ===")
    print("Start timestamp:", ts_start)
    print("End   timestamp:", ts_end)

    if ts_start and ts_end:
        duration = (ts_end - ts_start).total_seconds()
        print(f"Estimated duration from timestamps: {duration:.1f} s")


if __name__ == "__main__":
    main()
