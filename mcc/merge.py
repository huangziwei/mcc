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


def build_stats(items: list[MergeItem]) -> dict[str, Any]:
    row_total = 0
    row_proofread = 0
    row_unproofread = 0
    row_passes: dict[int, int] = {}

    col_total = len(items)
    col_proofread = 0
    col_unproofread = 0
    col_passes: dict[int, int] = {}

    for item in items:
        row_count = len(item.rows)
        row_total += row_count
        pass_num = extract_pass(item.meta)
        if pass_num:
            row_proofread += row_count
            row_passes[pass_num] = row_passes.get(pass_num, 0) + row_count
            col_proofread += 1
            col_passes[pass_num] = col_passes.get(pass_num, 0) + 1
        else:
            row_unproofread += row_count
            col_unproofread += 1

    return {
        "rows": {
            "total": row_total,
            "proofread": row_proofread,
            "unproofread": row_unproofread,
            "passes": row_passes,
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

    stats = build_stats(merge_items)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    meta_columns = [
        "page",
        "col",
        "row_in_col",
        "source_csv",
        "source_image",
        "proofread_pass",
        "proofread_level",
        "proofread_by",
        "proofread_started_at",
        "proofread_completed_at",
        "proofread_status",
        "notes",
    ]
    header = master_columns + meta_columns

    with out_path.open("w", newline="", encoding="utf-8") as csv_file:
        if stats_mode == "comments":
            stats_payload = json.dumps(stats, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            csv_file.write(f"# mcc-stats: {stats_payload}\n")
        writer = csv.writer(csv_file)
        writer.writerow(header)
        for item in merge_items:
            meta = item.meta or {}
            pass_num = extract_pass(meta)
            level = normalize_value(meta.get("proofread_level"))
            if not level and pass_num:
                level = f"pass-{pass_num}"
            status = level or "unproofread"
            for row_idx, row in enumerate(item.rows, start=1):
                row_map = {
                    item.columns[col_idx]: normalize_value(row[col_idx])
                    for col_idx in range(len(item.columns))
                    if col_idx < len(row)
                }
                data_values = [row_map.get(name, "") for name in master_columns]
                meta_values = [
                    item.page,
                    item.col,
                    row_idx,
                    normalize_value(meta.get("source_csv") or item.path.name),
                    normalize_value(meta.get("source_image")),
                    normalize_value(pass_num),
                    level,
                    normalize_value(meta.get("proofread_by")),
                    normalize_value(meta.get("proofread_started_at")),
                    normalize_value(meta.get("proofread_completed_at")),
                    status,
                    normalize_value(meta.get("notes")),
                ]
                writer.writerow(data_values + meta_values)

    console.log(f"Wrote merged CSV: {out_path}")
