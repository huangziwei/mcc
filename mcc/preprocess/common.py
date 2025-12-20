from __future__ import annotations

import re
from pathlib import Path
from typing import Tuple

from PIL import Image

_PAGE_RE = re.compile(r"^page-(\d+)\.(?:png|jpe?g|tif|tiff)$", re.IGNORECASE)


def resolve_page_range(page_count: int, start_page: int, end_page: int | None) -> Tuple[int, int]:
    if page_count < 1:
        raise SystemExit("PDF has no pages.")
    if start_page < 1:
        raise SystemExit("start-page must be >= 1.")
    if start_page > page_count:
        raise SystemExit(f"start-page {start_page} exceeds page count {page_count}.")
    if end_page is None:
        end_page = page_count
    elif end_page < start_page:
        raise SystemExit("end-page must be >= start-page.")
    elif end_page > page_count:
        raise SystemExit(f"end-page {end_page} exceeds page count {page_count}.")
    return start_page - 1, end_page - 1


def list_page_images(in_dir: Path) -> list[Tuple[int, Path]]:
    if not in_dir.exists():
        raise SystemExit(f"Input directory not found: {in_dir}")
    items: list[Tuple[int, Path]] = []
    for path in in_dir.iterdir():
        if not path.is_file():
            continue
        match = _PAGE_RE.match(path.name)
        if not match:
            continue
        items.append((int(match.group(1)), path))
    items.sort(key=lambda item: item[0])
    return items


def compute_otsu_threshold(hist: list[int]) -> int:
    total = sum(hist)
    if total == 0:
        return 128
    sum_total = sum(i * hist[i] for i in range(256))
    sum_b = 0.0
    weight_b = 0.0
    max_var = -1.0
    threshold = 128

    for i in range(256):
        weight_b += hist[i]
        if weight_b == 0:
            continue
        weight_f = total - weight_b
        if weight_f == 0:
            break
        sum_b += i * hist[i]
        mean_b = sum_b / weight_b
        mean_f = (sum_total - sum_b) / weight_f
        var_between = weight_b * weight_f * (mean_b - mean_f) ** 2
        if var_between > max_var:
            max_var = var_between
            threshold = i

    return threshold


def estimate_ink_threshold(hist: list[int]) -> int:
    total = sum(hist)
    if total == 0:
        return 128

    otsu = compute_otsu_threshold(hist)
    peak_range = range(200, 256)
    peak_idx = max(peak_range, key=lambda i: hist[i])
    peak_ratio = hist[peak_idx] / total

    if peak_ratio >= 0.05:
        threshold = max(otsu, peak_idx - 12)
    else:
        threshold = otsu

    return max(120, min(245, threshold))


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    pct = max(0.0, min(1.0, pct))
    sorted_vals = sorted(values)
    idx = int(round((len(sorted_vals) - 1) * pct))
    return sorted_vals[idx]


def smooth_densities(values: list[float], window: int) -> list[float]:
    if window <= 1:
        return values[:]
    half = window // 2
    prefix = [0.0]
    for v in values:
        prefix.append(prefix[-1] + v)
    out: list[float] = []
    count = len(values)
    for i in range(count):
        lo = max(0, i - half)
        hi = min(count, i + half + 1)
        out.append((prefix[hi] - prefix[lo]) / (hi - lo))
    return out


def find_content_rows(
    mask: Image.Image,
    analysis_width: int,
    row_threshold: float,
    row_window: int,
    min_run: int,
) -> Tuple[int, int] | None:
    w, h = mask.size
    analysis_width = max(1, min(analysis_width, w))
    analysis_height = max(1, int(h * analysis_width / w))
    mask_small = mask.resize((analysis_width, analysis_height), resample=Image.NEAREST)

    data = mask_small.tobytes()
    row_densities: list[float] = []
    for y in range(analysis_height):
        row = data[y * analysis_width : (y + 1) * analysis_width]
        ink = row.count(255)
        row_densities.append(ink / analysis_width)

    smoothed = smooth_densities(row_densities, row_window)
    p50 = percentile(smoothed, 0.5)
    p90 = percentile(smoothed, 0.9)
    dynamic_threshold = max(row_threshold, p50 + (p90 - p50) * 0.35)
    min_run = max(min_run, int(analysis_height * 0.1))
    best_start = None
    best_end = None
    best_len = 0
    current_start = None

    for i, density in enumerate(smoothed):
        if density >= dynamic_threshold:
            if current_start is None:
                current_start = i
            continue
        if current_start is not None:
            run_len = i - current_start
            if run_len >= min_run and run_len > best_len:
                best_start, best_end, best_len = current_start, i - 1, run_len
            current_start = None

    if current_start is not None:
        run_len = analysis_height - current_start
        if run_len >= min_run and run_len > best_len:
            best_start, best_end = current_start, analysis_height - 1

    if best_start is None or best_end is None:
        return None
    return best_start, best_end


def build_ink_mask(img: Image.Image, threshold: int | None, max_threshold: int) -> Image.Image:
    gray = img.convert("L")
    if threshold is None:
        threshold = estimate_ink_threshold(gray.histogram())
    threshold = min(threshold, max_threshold)
    threshold = max(90, min(250, threshold))
    return gray.point(lambda p: 255 if p < threshold else 0, mode="L")


def detect_horizontal_rule(
    mask: Image.Image,
    min_density: float,
    min_y_ratio: float,
    max_y_ratio: float,
) -> int | None:
    w, h = mask.size
    analysis_w = min(1200, w)
    analysis_h = max(1, int(h * analysis_w / w))
    small = mask.resize((analysis_w, analysis_h), resample=Image.NEAREST)
    data = small.tobytes()
    row_densities = []
    for y in range(analysis_h):
        row = data[y * analysis_w : (y + 1) * analysis_w]
        row_densities.append(row.count(255) / analysis_w)

    candidates = [i for i, d in enumerate(row_densities) if d >= min_density]
    if not candidates:
        return None

    segments = []
    start = prev = candidates[0]
    for idx in candidates[1:]:
        if idx == prev + 1:
            prev = idx
            continue
        segments.append((start, prev))
        start = prev = idx
    segments.append((start, prev))

    min_y = int(analysis_h * min_y_ratio)
    max_y = int(analysis_h * max_y_ratio)
    for s, e in segments:
        if s >= min_y and s <= max_y:
            return int((e + 1) * (h / analysis_h))

    s, e = segments[0]
    return int((e + 1) * (h / analysis_h))


def detect_row_centers(
    mask: Image.Image,
    top: int,
    analysis_width: int,
    left_ratio: float,
    smooth_window: int,
    threshold_factor: float,
    min_run: int,
    row_threshold: float,
) -> Tuple[list[int], float]:
    w, h = mask.size
    crop = mask.crop((0, top, w, h))
    analysis_width = max(1, min(analysis_width, crop.width))
    analysis_height = max(1, int(crop.height * analysis_width / crop.width))
    small = crop.resize((analysis_width, analysis_height), resample=Image.NEAREST)
    data = small.tobytes()
    strip_w = max(1, int(analysis_width * left_ratio))

    row_densities: list[float] = []
    for y in range(analysis_height):
        row = data[y * analysis_width : (y + 1) * analysis_width]
        row = row[:strip_w]
        row_densities.append(row.count(255) / strip_w)

    smooth_window = max(1, smooth_window)
    if smooth_window % 2 == 0:
        smooth_window += 1
    smoothed = smooth_densities(row_densities, smooth_window)
    q50 = percentile(smoothed, 0.5)
    q90 = percentile(smoothed, 0.9)
    threshold = max(row_threshold, q50 + (q90 - q50) * threshold_factor)

    min_run = max(min_run, max(2, int(analysis_height * 0.004)))
    indices = [i for i, d in enumerate(smoothed) if d >= threshold]
    clusters = []
    if indices:
        start = prev = indices[0]
        for idx in indices[1:]:
            if idx == prev + 1:
                prev = idx
                continue
            clusters.append((start, prev))
            start = prev = idx
        clusters.append((start, prev))

    centers = [(s + e) // 2 for s, e in clusters if (e - s + 1) >= min_run]
    spacings = [centers[i + 1] - centers[i] for i in range(len(centers) - 1)]
    spacing = sorted(spacings)[len(spacings) // 2] if spacings else 20
    scale = crop.height / analysis_height
    centers_px = [int(c * scale) for c in centers]
    return centers_px, spacing * scale

