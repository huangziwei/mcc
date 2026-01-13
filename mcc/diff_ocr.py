from __future__ import annotations

from pathlib import Path

from rich.console import Console

from mcc.merge import list_column_csv
from mcc.preprocess.ollama_ocr import compare_csv_rows


def build_csv_map(csv_dir: Path) -> dict[str, Path]:
    items = list_column_csv(csv_dir)
    return {path.name: path for _, _, path in items}


def diff_ocr_dirs(left_dir: Path, right_dir: Path) -> None:
    console = Console(stderr=True)
    left_map = build_csv_map(left_dir)
    right_map = build_csv_map(right_dir)

    common = sorted(set(left_map) & set(right_map))
    if not common:
        raise SystemExit(
            f"No matching CSV files between {left_dir} and {right_dir}."
        )

    matched_total = 0
    expected_total = 0
    actual_total = 0
    diff_count = 0

    for name in common:
        matched, expected_rows, actual_rows, mismatches = compare_csv_rows(
            actual_path=right_map[name],
            expected_path=left_map[name],
        )
        matched_total += matched
        expected_total += expected_rows
        actual_total += actual_rows
        for diff in mismatches:
            diff_count += 1
            console.log(f"Diff {name}: {diff}")

    accuracy = matched_total / expected_total if expected_total else 0.0
    console.log(
        f"Overall agreement: {accuracy:.2%} ({matched_total}/{expected_total}), "
        f"files {len(common)}, actual rows {actual_total}, diffs {diff_count}"
    )
