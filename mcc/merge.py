from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Console

_CSV_RE = re.compile(r"^page-(\d+)-col-(\d+)\.csv$", re.IGNORECASE)
_PASS_RE = re.compile(r"(?:pass|level)-(\d+)")
_DEFAULT_COLUMNS = ["index", "word"]


@dataclass
class MergeItem:
    page: int
    col: int
    path: Path
    base: str
    rows: list[list[str]]
    columns: list[str]
    meta: dict[str, Any] | None


def list_column_csv(in_dir: Path) -> list[tuple[int, int, Path]]:
    if not in_dir.exists():
        raise SystemExit(f"Input directory not found: {in_dir}")
    items: list[tuple[int, int, Path]] = []
    for path in in_dir.iterdir():
        if not path.is_file():
            continue
        match = _CSV_RE.match(path.name)
        if not match:
            continue
        items.append((int(match.group(1)), int(match.group(2)), path))
    items.sort(key=lambda item: (item[0], item[1]))
    return items


def read_csv_rows(path: Path) -> list[list[str]]:
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return [row for row in csv.reader(csv_file)]


def read_metadata(meta_dir: Path | None, base: str) -> dict[str, Any] | None:
    if meta_dir is None:
        return None
    meta_path = meta_dir / f"{base}.json"
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def normalize_columns(columns: list[str], max_len: int) -> list[str]:
    normalized = list(columns)
    if max_len <= len(normalized):
        return normalized
    for idx in range(len(normalized), max_len):
        normalized.append(f"col-{idx + 1}")
    return normalized


def derive_columns(meta: dict[str, Any] | None, rows: list[list[str]]) -> list[str]:
    max_len = max((len(row) for row in rows), default=0)
    if meta and isinstance(meta.get("columns"), list) and meta["columns"]:
        columns = [str(value) for value in meta["columns"]]
        return normalize_columns(columns, max_len)
    return normalize_columns(list(_DEFAULT_COLUMNS), max_len)


def extract_pass(meta: dict[str, Any] | None) -> int | None:
    if not meta:
        return None
    value = meta.get("proofread_pass")
    if value is None:
        match = _PASS_RE.search(str(meta.get("proofread_level") or ""))
        if match:
            value = match.group(1)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def normalize_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def build_stats(
    items: list[MergeItem],
    row_ranges_by_pass: dict[str, list[int | list[int]]],
    unproofread_ranges: list[int | list[int]],
) -> dict[str, Any]:
    row_total = 0
    row_proofread = 0
    row_unproofread = 0
    row_passes: dict[str, int] = {}

    col_total = len(items)
    col_proofread = 0
    col_unproofread = 0
    col_passes: dict[str, int] = {}

    for item in items:
        row_count = len(item.rows)
        row_total += row_count
        pass_num = extract_pass(item.meta)
        if pass_num:
            row_proofread += row_count
            pass_key = str(pass_num)
            row_passes[pass_key] = row_passes.get(pass_key, 0) + row_count
            col_proofread += 1
            col_passes[pass_key] = col_passes.get(pass_key, 0) + 1
        else:
            row_unproofread += row_count
            col_unproofread += 1

    return {
        "rows": {
            "total": row_total,
            "proofread": row_proofread,
            "unproofread": row_unproofread,
            "passes": row_passes,
            "ranges_by_pass": row_ranges_by_pass,
            "unproofread_ranges": unproofread_ranges,
        },
        "columns": {
            "total": col_total,
            "proofread": col_proofread,
            "unproofread": col_unproofread,
            "passes": col_passes,
        },
    }


def merge_csv(
    csv_dir: Path,
    meta_dir: Path | None,
    out_path: Path,
    stats_mode: str = "comments",
) -> None:
    console = Console(stderr=True)
    items = list_column_csv(csv_dir)
    if not items:
        raise SystemExit(f"No CSV files found in: {csv_dir}")

    if meta_dir is not None and not meta_dir.exists():
        console.log(f"Metadata directory not found: {meta_dir}. Proceeding without metadata.")
        meta_dir = None

    merge_items: list[MergeItem] = []
    master_columns: list[str] = []

    for page_num, col_num, path in items:
        rows = read_csv_rows(path)
        base = path.stem
        meta = read_metadata(meta_dir, base)
        columns = derive_columns(meta, rows)
        for name in columns:
            if name not in master_columns:
                master_columns.append(name)
        merge_items.append(
            MergeItem(
                page=page_num,
                col=col_num,
                path=path,
                base=base,
                rows=rows,
                columns=columns,
                meta=meta,
            )
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    header = master_columns

    def append_range(target: list[int | list[int]], start: int, end: int) -> None:
        if start > end:
            return
        if start == end:
            target.append(start)
        else:
            target.append([start, end])

    row_ranges_by_pass: dict[str, list[int | list[int]]] = {}
    unproofread_ranges: list[int | list[int]] = []
    current_pass: int | None = None
    current_start: int | None = None
    row_cursor = 1
    for item in merge_items:
        row_count = len(item.rows)
        if row_count == 0:
            continue
        pass_num = extract_pass(item.meta)
        if current_start is None:
            current_start = row_cursor
            current_pass = pass_num
        elif pass_num != current_pass:
            end = row_cursor - 1
            if current_pass is None:
                append_range(unproofread_ranges, current_start, end)
            else:
                pass_key = str(current_pass)
                row_ranges_by_pass.setdefault(pass_key, [])
                append_range(row_ranges_by_pass[pass_key], current_start, end)
            current_start = row_cursor
            current_pass = pass_num
        row_cursor += row_count

    if current_start is not None:
        end = row_cursor - 1
        if current_pass is None:
            append_range(unproofread_ranges, current_start, end)
        else:
            pass_key = str(current_pass)
            row_ranges_by_pass.setdefault(pass_key, [])
            append_range(row_ranges_by_pass[pass_key], current_start, end)

    stats = build_stats(merge_items, row_ranges_by_pass, unproofread_ranges)

    with out_path.open("w", newline="", encoding="utf-8") as csv_file:
        if stats_mode == "comments":
            stats_payload = json.dumps(stats, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            csv_file.write(f"# mcc-stats: {stats_payload}\n")
        writer = csv.writer(csv_file)
        writer.writerow(header)
        for item in merge_items:
            for row in item.rows:
                row_map = {
                    item.columns[col_idx]: normalize_value(row[col_idx])
                    for col_idx in range(len(item.columns))
                    if col_idx < len(row)
                }
                data_values = [row_map.get(name, "") for name in master_columns]
                writer.writerow(data_values)

    console.log(f"Wrote merged CSV: {out_path}")
