from __future__ import annotations

from itertools import combinations
from pathlib import Path
from statistics import median
from typing import Iterable, Sequence

from PIL import Image
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from .common import (
    build_ink_mask,
    detect_horizontal_rule,
    detect_row_centers,
    list_page_images,
    percentile,
    resolve_page_range,
    smooth_densities,
)

try:
    RESAMPLE_BOX = Image.Resampling.BOX
except AttributeError:  # Pillow < 9
    RESAMPLE_BOX = Image.BOX


def pick_best_lines(centers: Sequence[int], width: int, count: int = 4) -> list[int]:
    if len(centers) < count:
        return []
    centers = sorted(centers)
    best_score = None
    best_combo: Sequence[int] | None = None
    for combo in combinations(centers, count):
        spacings = [combo[i + 1] - combo[i] for i in range(count - 1)]
        if min(spacings) <= 0:
            continue
        spacing = sorted(spacings)[len(spacings) // 2]
        left = combo[0] - spacing
        right = combo[-1] + spacing
        penalty = 0.0
        if left < 0:
            penalty += abs(left)
        if right > width:
            penalty += abs(right - width)
        mean = sum(spacings) / len(spacings)
        variance = sum((s - mean) ** 2 for s in spacings) / len(spacings)
        score = variance + penalty * 2.0
        if best_score is None or score < best_score:
            best_score = score
            best_combo = combo
    return list(best_combo) if best_combo else []


def pick_stable_start(centers: Sequence[int], spacing: float, min_len: int, tol: float) -> int:
    if not centers:
        return 0
    if len(centers) < min_len:
        return centers[0]
    lo = spacing * (1.0 - tol)
    hi = spacing * (1.0 + tol)
    for i in range(len(centers) - min_len + 1):
        ok = True
        for j in range(i, i + min_len - 1):
            delta = centers[j + 1] - centers[j]
            if delta < lo or delta > hi:
                ok = False
                break
        if ok:
            return centers[i]
    return centers[0]


def measure_center_densities(
    mask: Image.Image,
    centers: Sequence[int],
    analysis_width: int,
    window: int = 2,
) -> list[float]:
    if not centers:
        return []
    w, h = mask.size
    analysis_width = max(1, min(analysis_width, w))
    analysis_height = max(1, int(h * analysis_width / w))
    small = mask.resize((analysis_width, analysis_height), resample=Image.NEAREST)
    data = small.tobytes()
    row_sums: list[int] = []
    for y in range(analysis_height):
        row = data[y * analysis_width : (y + 1) * analysis_width]
        row_sums.append(row.count(255))

    scale = analysis_height / h
    densities: list[float] = []
    for center in centers:
        y = int(center * scale)
        lo = max(0, y - window)
        hi = min(analysis_height, y + window + 1)
        total = sum(row_sums[lo:hi])
        densities.append(total / (analysis_width * (hi - lo)))
    return densities


def detect_horizontal_trim(
    mask: Image.Image,
    analysis_width: int,
    smooth_window: int,
    threshold_factor: float,
    min_run: int,
    pad: int,
    margin_left_ratio: float,
    margin_right_ratio: float,
    max_trim_left_ratio: float,
    max_trim_right_ratio: float,
) -> tuple[int, int]:
    w, h = mask.size
    if w == 0 or h == 0:
        return 0, w
    analysis_width = max(1, min(analysis_width, w))
    analysis_height = max(1, int(h * analysis_width / w))
    small = mask.resize((analysis_width, analysis_height), resample=RESAMPLE_BOX).convert("L")
    data = small.tobytes()

    col_coverage: list[float] = []
    for x in range(analysis_width):
        col = data[x::analysis_width]
        col_coverage.append(sum(1 for v in col if v) / analysis_height)

    smooth_window = max(1, smooth_window)
    if smooth_window % 2 == 0:
        smooth_window += 1
    smoothed = smooth_densities(col_coverage, smooth_window)
    q50 = percentile(smoothed, 0.5)
    threshold = max(0.002, q50 * threshold_factor)

    min_run = max(min_run, 2)
    left = None
    run = 0
    for i, d in enumerate(smoothed):
        if d >= threshold:
            run += 1
            if run >= min_run:
                left = i - min_run + 1
                break
        else:
            run = 0

    right = None
    run = 0
    for i in range(len(smoothed) - 1, -1, -1):
        if smoothed[i] >= threshold:
            run += 1
            if run >= min_run:
                right = i + min_run - 1
                break
        else:
            run = 0

    if left is None or right is None or right <= left:
        return 0, w

    scale = w / analysis_width
    margin_left = max(pad, int(round(w * margin_left_ratio)))
    margin_right = max(pad, int(round(w * margin_right_ratio)))
    left_px = max(0, int(left * scale) - margin_left)
    right_px = min(w, int((right + 1) * scale) + margin_right)
    if max_trim_left_ratio > 0:
        max_trim_left = int(round(w * max_trim_left_ratio))
        left_px = min(left_px, max_trim_left)
    if max_trim_right_ratio > 0:
        max_trim_right = int(round(w * max_trim_right_ratio))
        right_px = max(right_px, w - max_trim_right)
    if right_px <= left_px:
        return 0, w
    return left_px, right_px


def detect_headerless_top(
    mask: Image.Image,
    analysis_width: int,
    row_window: int,
    row_threshold: float,
    min_run: int,
    header_density_factor: float,
) -> int:
    centers, spacing = detect_row_centers(
        mask=mask,
        top=0,
        analysis_width=analysis_width,
        left_ratio=0.9,
        smooth_window=row_window,
        threshold_factor=0.5,
        min_run=min_run,
        row_threshold=row_threshold,
    )
    if not centers:
        return 0
    densities = measure_center_densities(mask, centers, analysis_width=analysis_width)
    if not densities:
        return 0
    density_median = median(densities)
    threshold = density_median * header_density_factor
    filtered = [c for c, d in zip(centers, densities) if d <= threshold]
    if not filtered:
        filtered = list(centers)
    start_center = pick_stable_start(filtered, spacing, min_len=6, tol=0.35)
    return max(0, int(start_center - spacing * 0.6))


def detect_line_candidates_runlength(
    mask: Image.Image,
    top: int,
    bottom: int,
    analysis_width: int,
    run_quantile: float,
    band: int,
    max_line_width: int,
    gap_allow: int,
    min_run_ratio: float,
    merge_dist_ratio: float,
    ink_threshold: int,
) -> list[int]:
    w, h = mask.size
    crop = mask.crop((0, top, w, bottom))
    analysis_width = max(1, min(analysis_width, crop.width))
    analysis_height = max(1, int(crop.height * analysis_width / crop.width))
    small = crop.resize((analysis_width, analysis_height), resample=RESAMPLE_BOX).convert("L")
    data = small.tobytes()

    run = [0] * analysis_width
    gap = [0] * analysis_width
    best = [0] * analysis_width

    for y in range(analysis_height):
        row = data[y * analysis_width : (y + 1) * analysis_width]
        prefix = [0] * (analysis_width + 1)
        running = 0
        for i, b in enumerate(row):
            if b > ink_threshold:
                running += 1
            prefix[i + 1] = running
        for x in range(analysis_width):
            lo = max(0, x - band)
            hi = min(analysis_width - 1, x + band)
            ink = (prefix[hi + 1] - prefix[lo]) > 0
            if ink:
                run[x] += 1
                gap[x] = 0
            else:
                if run[x] > 0 and gap[x] < gap_allow:
                    gap[x] += 1
                    run[x] += 1
                else:
                    if run[x] > best[x]:
                        best[x] = run[x]
                    run[x] = 0
                    gap[x] = 0

    for x in range(analysis_width):
        if run[x] > best[x]:
            best[x] = run[x]

    vals = sorted(best)
    if not vals:
        return []
    idx = int(round((len(vals) - 1) * run_quantile))
    qthr = vals[idx]
    abs_thr = int(min_run_ratio * analysis_height)
    threshold = max(qthr, abs_thr)

    candidates = [i for i, r in enumerate(best) if r >= threshold]
    if not candidates:
        k = min(40, analysis_width)
        candidates = sorted(range(analysis_width), key=lambda i: best[i], reverse=True)[:k]
        candidates.sort()

    segments = []
    start = prev = candidates[0]
    for pos in candidates[1:]:
        if pos == prev + 1:
            prev = pos
            continue
        segments.append((start, prev))
        start = prev = pos
    segments.append((start, prev))

    max_line_width = max(1, max_line_width + band * 2)
    narrow = [(s, e) for s, e in segments if (e - s + 1) <= max_line_width]
    centers = [(s + e) // 2 for s, e in narrow]
    merge_dist = max(2, int(round(merge_dist_ratio * analysis_width)))
    merged: list[int] = []
    for c in centers:
        if not merged:
            merged.append(c)
            continue
        if c - merged[-1] <= merge_dist:
            merged[-1] = (merged[-1] + c) // 2
        else:
            merged.append(c)
    scale = crop.width / analysis_width
    return [int(round(c * scale)) for c in merged]


def detect_separator_lines(
    mask: Image.Image,
    top: int,
    bottom: int,
    analysis_width: int,
    quantiles: Iterable[float],
    max_line_width: int,
    page_width: int,
) -> list[int]:
    for q in quantiles:
        centers = detect_line_candidates_runlength(
            mask=mask,
            top=top,
            bottom=bottom,
            analysis_width=analysis_width,
            run_quantile=q,
            band=2,
            max_line_width=max_line_width,
            gap_allow=2,
            min_run_ratio=0.3,
            merge_dist_ratio=0.006,
            ink_threshold=10,
        )
        if len(centers) < 4:
            continue
        picked = pick_best_lines(centers, page_width, count=4)
        if picked:
            return picked
    return []


def detect_bottom(
    mask: Image.Image,
    top: int,
    analysis_width: int,
    smooth_window: int,
    threshold_factor: float,
    min_run: int,
) -> int:
    w, h = mask.size
    crop = mask.crop((0, top, w, h))
    analysis_width = max(1, min(analysis_width, crop.width))
    analysis_height = max(1, int(crop.height * analysis_width / crop.width))
    small = crop.resize((analysis_width, analysis_height), resample=Image.NEAREST)
    data = small.tobytes()

    row_densities: list[float] = []
    for y in range(analysis_height):
        row = data[y * analysis_width : (y + 1) * analysis_width]
        row_densities.append(row.count(255) / analysis_width)

    smooth_window = max(1, smooth_window)
    if smooth_window % 2 == 0:
        smooth_window += 1
    smoothed = smooth_densities(row_densities, smooth_window)
    vals = sorted(smoothed)
    q50 = vals[int(0.5 * (len(vals) - 1))]
    q90 = vals[int(0.9 * (len(vals) - 1))]
    threshold = q50 + (q90 - q50) * threshold_factor

    run = 0
    end_idx = None
    for i in range(analysis_height - 1, -1, -1):
        if smoothed[i] >= threshold:
            run += 1
            if run >= min_run:
                end_idx = i + min_run - 1
                break
        else:
            run = 0

    if end_idx is None:
        end_idx = analysis_height - 1
    scale = crop.height / analysis_height
    return int((end_idx + 1) * scale)


def detect_horizontal_rule_runlength(
    mask: Image.Image,
    analysis_width: int,
    min_y_ratio: float,
    max_y_ratio: float,
    band: int,
    gap_allow: int,
    min_run_ratio: float,
    ink_threshold: int,
) -> int | None:
    w, h = mask.size
    if w == 0 or h == 0:
        return None
    analysis_width = max(1, min(analysis_width, w))
    analysis_height = max(1, int(h * analysis_width / w))
    small = mask.resize((analysis_width, analysis_height), resample=RESAMPLE_BOX).convert("L")
    data = small.tobytes()

    start_y = max(0, int(analysis_height * min_y_ratio))
    end_y = min(analysis_height, int(analysis_height * max_y_ratio))
    if end_y <= start_y:
        return None

    best_ratio = 0.0
    best_y = None
    for y in range(start_y, end_y):
        run = 0
        gap = 0
        best = 0
        y0 = max(0, y - band)
        y1 = min(analysis_height - 1, y + band)
        for x in range(analysis_width):
            ink = False
            offset = x
            for yy in range(y0, y1 + 1):
                if data[yy * analysis_width + offset] > ink_threshold:
                    ink = True
                    break
            if ink:
                run += 1
                gap = 0
            else:
                if run > 0 and gap < gap_allow:
                    gap += 1
                    run += 1
                else:
                    if run > best:
                        best = run
                    run = 0
                    gap = 0
        if run > best:
            best = run
        ratio = best / analysis_width
        if ratio > best_ratio:
            best_ratio = ratio
            best_y = y

    if best_y is None or best_ratio < min_run_ratio:
        return None
    scale = h / analysis_height
    return int((best_y + 1) * scale)


def validate_separator_lines(
    lines: Sequence[int],
    width: int,
    min_edge_ratio: float,
    min_spacing_ratio: float,
    spacing_ratio_range: tuple[float, float] | None = None,
) -> float | None:
    if len(lines) != 4:
        return None
    lines = sorted(lines)
    left_edge = width * min_edge_ratio
    right_edge = width * (1.0 - min_edge_ratio)
    if lines[0] < left_edge or lines[-1] > right_edge:
        return None
    spacings = [lines[i + 1] - lines[i] for i in range(len(lines) - 1)]
    if min(spacings) <= 0:
        return None
    ratio = min(spacings) / max(spacings)
    if ratio < min_spacing_ratio:
        return None
    spacing = sorted(spacings)[len(spacings) // 2]
    spacing_ratio = spacing / width
    if spacing_ratio_range is not None:
        min_ratio, max_ratio = spacing_ratio_range
        if spacing_ratio < min_ratio or spacing_ratio > max_ratio:
            return None
    return spacing_ratio


def compute_column_bounds(
    mask: Image.Image,
    top: int,
    bottom: int,
    analysis_width: int,
    pad: int,
    quantiles: Iterable[float],
    max_line_width: int,
    edge_margin_ratio: float,
    lines: Sequence[int] | None = None,
) -> list[tuple[int, int]]:
    w, h = mask.size
    if lines is None:
        lines = detect_separator_lines(
            mask=mask,
            top=top,
            bottom=bottom,
            analysis_width=analysis_width,
            quantiles=quantiles,
            max_line_width=max_line_width,
            page_width=w,
        )

    if lines:
        lines = sorted(lines)
        left_gap = lines[1] - lines[0] if len(lines) > 1 else lines[0]
        right_gap = lines[-1] - lines[-2] if len(lines) > 1 else w - lines[-1]
        edge_margin_left = int(left_gap * edge_margin_ratio)
        edge_margin_right = int(right_gap * edge_margin_ratio)
        left = max(0, int(lines[0] - left_gap - edge_margin_left) - pad)
        right = min(w, int(lines[-1] + right_gap + edge_margin_right) + pad)

        bounds = [
            (left, lines[0]),
            (lines[0], lines[1]),
            (lines[1], lines[2]),
            (lines[2], lines[3]),
            (lines[3], right),
        ]
        return bounds

    # Fallback: use full width with light padding.
    left = max(0, pad)
    right = min(w, w - pad)
    col_width = (right - left) / 5.0
    bounds = []
    for i in range(5):
        x0 = int(round(left + i * col_width))
        x1 = int(round(left + (i + 1) * col_width))
        if i == 4:
            x1 = min(w, int(round(right)))
        bounds.append((x0, x1))
    return bounds


def segment_pages(
    in_dir: Path,
    out_dir: Path,
    start_page: int,
    end_page: int | None,
    threshold: int | None,
    analysis_width: int,
    row_window: int,
    row_threshold: float,
    min_run: int,
    pad: int,
    skip_existing: bool,
    no_progress: bool,
    quantiles: Iterable[float],
    max_line_width: int,
    edge_margin_ratio: float,
) -> None:
    console = Console(stderr=True)
    items = list_page_images(in_dir)
    if not items:
        raise SystemExit(f"No page images found in: {in_dir}")

    max_page = max(page_num for page_num, _ in items)
    start_idx, end_idx = resolve_page_range(max_page, start_page, end_page)
    start_page = start_idx + 1
    end_page = end_idx + 1

    selected = [(page_num, path) for page_num, path in items if start_page <= page_num <= end_page]
    if not selected:
        raise SystemExit(f"No page images in range {start_page}-{end_page}.")

    out_dir.mkdir(parents=True, exist_ok=True)

    def outputs_exist(page_num: int) -> bool:
        return all((out_dir / f"page-{page_num:04d}-col-{i}.png").exists() for i in range(1, 6))

    def process_one(page_num: int, path: Path) -> None:
        if skip_existing and outputs_exist(page_num):
            console.log(f"Skip page {page_num} (columns exist)")
            return
        img = Image.open(path)
        mask = build_ink_mask(img, threshold=threshold, max_threshold=220)
        w, h = mask.size

        rule_y = detect_horizontal_rule_runlength(
            mask=mask,
            analysis_width=min(1200, analysis_width),
            min_y_ratio=0.03,
            max_y_ratio=0.45,
            band=1,
            gap_allow=2,
            min_run_ratio=0.6,
            ink_threshold=10,
        )
        if rule_y is None:
            rule_y = detect_horizontal_rule(mask, min_density=0.5, min_y_ratio=0.03, max_y_ratio=0.45)
        if rule_y is not None:
            top = min(h - 1, rule_y + 8)
        else:
            top = detect_headerless_top(
                mask=mask,
                analysis_width=analysis_width,
                row_window=row_window,
                row_threshold=row_threshold,
                min_run=min_run,
                header_density_factor=1.6,
            )

        centers, spacing = detect_row_centers(
            mask=mask,
            top=top,
            analysis_width=analysis_width,
            left_ratio=0.2,
            smooth_window=row_window,
            threshold_factor=0.5,
            min_run=min_run,
            row_threshold=row_threshold,
        )
        bottom_pad = pad
        if centers:
            bottom_pad = max(pad, int(spacing * 0.2))

        bottom_offset = detect_bottom(
            mask=mask,
            top=top,
            analysis_width=analysis_width,
            smooth_window=row_window,
            threshold_factor=0.4,
            min_run=max(3, min_run),
        )
        bottom = min(h, top + bottom_offset + bottom_pad)
        top = max(0, top - pad)

        region = img.crop((0, top, w, bottom))
        region_mask = build_ink_mask(region, threshold=threshold, max_threshold=220)
        lines = detect_separator_lines(
            mask=region_mask,
            top=0,
            bottom=region_mask.height,
            analysis_width=analysis_width,
            quantiles=quantiles,
            max_line_width=max_line_width,
            page_width=region_mask.width,
        )
        line_quality = validate_separator_lines(
            lines=lines,
            width=region_mask.width,
            min_edge_ratio=0.04,
            min_spacing_ratio=0.6,
            spacing_ratio_range=None,
        )
        trim_left, trim_right = detect_horizontal_trim(
            region_mask,
            analysis_width=analysis_width,
            smooth_window=max(5, row_window),
            threshold_factor=0.2,
            min_run=3,
            pad=pad,
            margin_left_ratio=0.015,
            margin_right_ratio=0.04,
            max_trim_left_ratio=0.08,
            max_trim_right_ratio=0.04,
        )
        if line_quality is not None:
            mid_widths = [lines[1] - lines[0], lines[2] - lines[1], lines[3] - lines[2]]
            min_col_width = sum(mid_widths) / len(mid_widths)
            left_limit = max(0, int(lines[0] - min_col_width))
            right_limit = min(region.width, int(lines[3] + min_col_width))
            trim_left = min(trim_left, left_limit)
            trim_right = max(trim_right, right_limit)

        if trim_left > 0 or trim_right < region.width:
            region = region.crop((trim_left, 0, trim_right, region.height))
            region_mask = build_ink_mask(region, threshold=threshold, max_threshold=220)
            if lines:
                lines = [line - trim_left for line in lines]

        if line_quality is None:
            lines = detect_separator_lines(
                mask=region_mask,
                top=0,
                bottom=region_mask.height,
                analysis_width=analysis_width,
                quantiles=quantiles,
                max_line_width=max_line_width,
                page_width=region_mask.width,
            )

        line_quality = validate_separator_lines(
            lines=lines,
            width=region_mask.width,
            min_edge_ratio=0.04,
            min_spacing_ratio=0.6,
            spacing_ratio_range=None,
        )
        if line_quality is None:
            lines = []

        bounds = compute_column_bounds(
            mask=region_mask,
            top=0,
            bottom=region_mask.height,
            analysis_width=analysis_width,
            pad=pad,
            quantiles=quantiles,
            max_line_width=max_line_width,
            edge_margin_ratio=edge_margin_ratio,
            lines=lines,
        )

        for idx, (x0, x1) in enumerate(bounds, start=1):
            col = region.crop((x0, 0, x1, region.height))
            out_path = out_dir / f"page-{page_num:04d}-col-{idx}.png"
            col.save(out_path)

        console.log(f"Segmented page {page_num} -> cols 1-5")

    if no_progress:
        for page_num, path in selected:
            process_one(page_num, path)
        return

    progress = Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total} pages"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=False,
    )

    with progress:
        task_id = progress.add_task("Segmenting pages", total=len(selected))
        for page_num, path in selected:
            progress.update(task_id, description=f"Segmenting page {page_num}")
            process_one(page_num, path)
            progress.advance(task_id)

    console.log(f"Wrote segmented columns for pages {start_page}-{end_page} to {out_dir}")
