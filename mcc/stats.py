from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from rich.console import Console

from mcc.merge import MergeItem, build_stats, extract_pass, list_column_csv, read_csv_rows, read_metadata

_STATS_START = "<!-- mcc:stats:start -->"
_STATS_END = "<!-- mcc:stats:end -->"


def _format_count(value: int) -> str:
    return f"{value:,}"


def _format_percent(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.0%"
    return f"{(numerator / denominator) * 100:.1f}%"


def _sort_pass_key(key: str) -> tuple[int, int | str]:
    try:
        return (0, int(key))
    except ValueError:
        return (1, key)


def compute_row_ranges(
    items: list[MergeItem],
) -> tuple[dict[str, list[int | list[int]]], list[int | list[int]]]:
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

    for item in items:
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

    return row_ranges_by_pass, unproofread_ranges


def collect_stats(
    csv_dir: Path,
    meta_dir: Path | None,
    console: Console | None = None,
) -> dict[str, Any]:
    if console is None:
        console = Console(stderr=True)
    items = list_column_csv(csv_dir)
    if not items:
        raise SystemExit(f"No CSV files found in: {csv_dir}")

    if meta_dir is not None and not meta_dir.exists():
        console.log(f"Metadata directory not found: {meta_dir}. Proceeding without metadata.")
        meta_dir = None

    merge_items: list[MergeItem] = []
    for page_num, col_num, path in items:
        rows = read_csv_rows(path)
        base = path.stem
        meta = read_metadata(meta_dir, base)
        merge_items.append(
            MergeItem(
                page=page_num,
                col=col_num,
                path=path,
                base=base,
                rows=rows,
                columns=[],
                meta=meta,
            )
        )

    row_ranges_by_pass, unproofread_ranges = compute_row_ranges(merge_items)
    return build_stats(merge_items, row_ranges_by_pass, unproofread_ranges)


def format_stats_lines(stats: dict[str, Any]) -> list[str]:
    rows = stats["rows"]
    cols = stats["columns"]
    row_total = int(rows.get("total", 0))
    row_proofread = int(rows.get("proofread", 0))
    col_total = int(cols.get("total", 0))
    col_proofread = int(cols.get("proofread", 0))

    lines = [
        (
            "Rows proofread: "
            f"{_format_count(row_proofread)} / {_format_count(row_total)} "
            f"({_format_percent(row_proofread, row_total)})"
        ),
        (
            "Columns proofread: "
            f"{_format_count(col_proofread)} / {_format_count(col_total)} "
            f"({_format_percent(col_proofread, col_total)})"
        ),
    ]

    row_passes = {str(key): int(value) for key, value in (rows.get("passes") or {}).items()}
    col_passes = {str(key): int(value) for key, value in (cols.get("passes") or {}).items()}
    pass_keys = sorted(set(row_passes) | set(col_passes), key=_sort_pass_key)
    if pass_keys:
        pass_parts = []
        for key in pass_keys:
            col_count = col_passes.get(key, 0)
            row_count = row_passes.get(key, 0)
            pass_parts.append(
                f"pass {key}: {_format_count(col_count)} cols / {_format_count(row_count)} rows"
            )
        lines.append("Passes: " + ", ".join(pass_parts))

    return lines


def format_readme_stats_lines(stats: dict[str, Any]) -> list[str]:
    rows = stats["rows"]
    row_total = int(rows.get("total", 0))
    row_unproofread = int(rows.get("unproofread", 0))
    row_passes = {str(key): int(value) for key, value in (rows.get("passes") or {}).items()}
    pass_numbers: list[int] = []
    for key in row_passes:
        try:
            pass_num = int(key)
        except (TypeError, ValueError):
            continue
        if pass_num > 0:
            pass_numbers.append(pass_num)
    current_pass = max(pass_numbers) if pass_numbers else 1

    if row_unproofread > 0 or current_pass <= 1:
        proofread = row_passes.get("1", 0)
        return [
            (
                "Pass 1: "
                f"{_format_count(proofread)} / {_format_count(row_total)} "
                f"({_format_percent(proofread, row_total)})"
            )
        ]

    proofread = row_passes.get(str(current_pass), 0)
    return [
        "Pass 1: 100%",
        (
            f"Pass {current_pass}: "
            f"{_format_count(proofread)} / {_format_count(row_total)} "
            f"({_format_percent(proofread, row_total)})"
        ),
    ]


def render_readme_block(stats: dict[str, Any]) -> str:
    bullet_lines = [f"- {line}" for line in format_readme_stats_lines(stats)]
    return "\n".join([_STATS_START, *bullet_lines, _STATS_END])


def update_readme_stats(readme_path: Path, stats: dict[str, Any], console: Console | None = None) -> None:
    if console is None:
        console = Console(stderr=True)
    if not readme_path.exists():
        raise SystemExit(f"README not found: {readme_path}")

    text = readme_path.read_text(encoding="utf-8")
    marker_block = render_readme_block(stats)
    if _STATS_START in text and _STATS_END in text:
        pattern = re.compile(
            rf"{re.escape(_STATS_START)}.*?{re.escape(_STATS_END)}", re.DOTALL
        )
        updated = pattern.sub(marker_block, text, count=1)
    else:
        section = "\n".join(["### Proofreading Progress", "", marker_block])
        match = re.search(r"^###\s+Usage\b", text, re.MULTILINE)
        if match:
            updated = (
                text[: match.start()].rstrip()
                + "\n\n"
                + section
                + "\n\n"
                + text[match.start() :].lstrip()
            )
        else:
            updated = text.rstrip() + "\n\n" + section + "\n"

    if updated != text:
        readme_path.write_text(updated, encoding="utf-8")
        console.log(f"Updated README stats: {readme_path}")
    else:
        console.log(f"README stats already up to date: {readme_path}")
