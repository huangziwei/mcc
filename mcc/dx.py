from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Console

from mcc.merge import list_column_csv, read_csv_rows

STATS_PREFIX = "# mcc-stats:"


@dataclass
class MergedCsv:
    stats: dict[str, Any] | None
    header: list[str]
    rows: list[list[str]]


def load_merged_csv(path: Path) -> MergedCsv:
    if not path.exists():
        raise SystemExit(f"Merged CSV not found: {path}")
    text = path.read_text(encoding="utf-8")
    stats: dict[str, Any] | None = None
    first_line, _, remainder = text.partition("\n")
    if first_line.startswith(STATS_PREFIX):
        payload = first_line[len(STATS_PREFIX) :].strip()
        if payload:
            try:
                stats = json.loads(payload)
            except json.JSONDecodeError:
                stats = None
        csv_text = remainder
    else:
        csv_text = text
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    if not rows:
        raise SystemExit(f"Merged CSV is empty: {path}")
    header = rows[0]
    data_rows = rows[1:]
    return MergedCsv(stats=stats, header=header, rows=data_rows)


def find_column(header: list[str], name: str, fallback: int | None = None) -> int:
    normalized = [value.strip().lower() for value in header]
    if name in normalized:
        return normalized.index(name)
    if fallback is not None and fallback < len(header):
        return fallback
    raise SystemExit(f"Column '{name}' not found in merged CSV header.")


def build_proofread_row_set(stats: dict[str, Any] | None) -> set[int]:
    if not stats or "rows" not in stats:
        raise SystemExit(
            "Missing stats header in merged CSV. Re-run `mcc merge` with stats comments."
        )
    ranges_by_pass = stats.get("rows", {}).get("ranges_by_pass") or {}
    proofread_rows: set[int] = set()
    for ranges in ranges_by_pass.values():
        if not isinstance(ranges, list):
            continue
        for item in ranges:
            if isinstance(item, list) and len(item) == 2:
                start, end = item
                try:
                    start_num = int(start)
                    end_num = int(end)
                except (TypeError, ValueError):
                    continue
                if start_num <= end_num:
                    proofread_rows.update(range(start_num, end_num + 1))
            else:
                try:
                    proofread_rows.add(int(item))
                except (TypeError, ValueError):
                    continue
    return proofread_rows


def build_row_sources(csv_dir: Path) -> list[tuple[int, int, int] | None]:
    items = list_column_csv(csv_dir)
    if not items:
        raise SystemExit(f"No CSV files found in: {csv_dir}")
    sources: list[tuple[int, int, int] | None] = [None]
    for page_num, col_num, path in items:
        row_count = len(read_csv_rows(path))
        for offset in range(row_count):
            sources.append((page_num, col_num, offset + 1))
    return sources


def format_row_source(
    row_sources: list[tuple[int, int, int] | None] | None, row_num: int
) -> str:
    if not row_sources or row_num >= len(row_sources):
        return "source unknown"
    source = row_sources[row_num]
    if not source:
        return "source unknown"
    page_num, col_num, local_row = source
    return f"page-{page_num:04d}-col-{col_num} row {local_row}"


def check_proofread_index_continuity(
    merged_path: Path,
    csv_dir: Path | None = None,
    console: Console | None = None,
) -> int:
    if console is None:
        console = Console(stderr=True)
    merged = load_merged_csv(merged_path)
    row_sources = build_row_sources(csv_dir) if csv_dir is not None else None
    if row_sources is not None and len(row_sources) - 1 != len(merged.rows):
        console.print(
            "Warning: source CSV row count does not match merged row count."
        )
    proofread_rows = build_proofread_row_set(merged.stats)
    if not proofread_rows:
        console.print("No proofread rows found in stats header.")
        return 0
    index_col = find_column(merged.header, "index", fallback=0)

    issues: list[str] = []
    gap_count = 0
    overlap_count = 0
    invalid_count = 0
    prev_index: int | None = None
    prev_row: int | None = None

    for row_num, row in enumerate(merged.rows, start=1):
        if row_num not in proofread_rows:
            prev_index = None
            prev_row = None
            continue
        raw_value = row[index_col].strip() if index_col < len(row) else ""
        try:
            current = int(raw_value)
        except (TypeError, ValueError):
            invalid_count += 1
            source = format_row_source(row_sources, row_num)
            issues.append(f"row {row_num} ({source}): invalid index '{raw_value}'")
            prev_index = None
            prev_row = None
            continue
        if prev_index is not None:
            if current == prev_index:
                overlap_count += 1
                source = format_row_source(row_sources, row_num)
                prev_source = format_row_source(row_sources, prev_row)
                issues.append(
                    "row "
                    f"{row_num} ({source}): overlap at index {current} "
                    f"(prev row {prev_row} ({prev_source}))"
                )
            elif current < prev_index:
                overlap_count += 1
                source = format_row_source(row_sources, row_num)
                prev_source = format_row_source(row_sources, prev_row)
                issues.append(
                    "row "
                    f"{row_num} ({source}): index {current} decreases from "
                    f"{prev_index} (prev row {prev_row} ({prev_source}))"
                )
            elif current > prev_index + 1:
                gap_count += 1
                missing_start = prev_index + 1
                missing_end = current - 1
                if missing_start == missing_end:
                    missing = str(missing_start)
                else:
                    missing = f"{missing_start}-{missing_end}"
                source = format_row_source(row_sources, row_num)
                prev_source = format_row_source(row_sources, prev_row)
                issues.append(
                    "row "
                    f"{row_num} ({source}): gap after {prev_index} "
                    f"(prev row {prev_row} ({prev_source})), missing {missing}"
                )
        prev_index = current
        prev_row = row_num

    total = len(proofread_rows)
    console.print(f"Proofread rows checked: {total}")
    console.print(
        f"Issues: {gap_count} gaps, {overlap_count} overlaps, {invalid_count} invalid indices"
    )
    for issue in issues:
        console.print(f"- {issue}")
    return len(issues)


def find_duplicate_words(
    merged_path: Path,
    csv_dir: Path | None = None,
    console: Console | None = None,
) -> int:
    if console is None:
        console = Console(stderr=True)
    merged = load_merged_csv(merged_path)
    row_sources = build_row_sources(csv_dir) if csv_dir is not None else None
    if row_sources is not None and len(row_sources) - 1 != len(merged.rows):
        console.print(
            "Warning: source CSV row count does not match merged row count."
        )
    proofread_rows = build_proofread_row_set(merged.stats)
    if not proofread_rows:
        console.print("No proofread rows found in stats header.")
        return 0
    word_col = find_column(merged.header, "word", fallback=1)
    index_col = find_column(merged.header, "index", fallback=0)
    pinyin_col = find_column(merged.header, "pinyin", fallback=None)

    word_map: dict[tuple[str, str], list[tuple[str, str]]] = {}
    checked = 0
    for row_num, row in enumerate(merged.rows, start=1):
        if row_num not in proofread_rows:
            continue
        checked += 1
        word = row[word_col].strip() if word_col < len(row) else ""
        if not word:
            continue
        pinyin_raw = row[pinyin_col] if pinyin_col < len(row) else ""
        pinyin = " ".join(str(pinyin_raw).strip().split())
        index_value = ""
        if index_col < len(row):
            index_value = row[index_col].strip()
        if not index_value:
            index_value = str(row_num)
        source = format_row_source(row_sources, row_num)
        word_map.setdefault((word, pinyin), []).append((index_value, source))

    duplicates = {
        key: refs for key, refs in word_map.items() if len(refs) > 1
    }
    if not duplicates:
        console.print(f"No duplicate words found in {checked} proofread rows.")
        return 0

    console.print(f"Proofread rows checked: {checked}")
    console.print(f"Duplicate word+pinyin pairs: {len(duplicates)}")
    for key in sorted(
        duplicates.keys(),
        key=lambda value: (-len(duplicates[value]), value),
    ):
        word, pinyin = key
        refs = ", ".join(
            f"{source} (index {index_value})"
            for index_value, source in duplicates[key]
        )
        console.print(f"- {word} [{pinyin}] ({len(duplicates[key])}): {refs}")
    return len(duplicates)
