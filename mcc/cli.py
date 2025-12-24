#!/usr/bin/env python3
"""
OCR pipeline CLI for scanned frequency list PDFs.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console

from mcc.dx import (
    check_proofread_index_continuity,
    find_duplicate_words,
    find_homophones,
    find_heteronyms,
    find_typo_words,
)
from mcc.merge import merge_csv
from mcc.publish import DEFAULT_CSV_URL, DEFAULT_TITLE, publish_site
from mcc.preprocess.ocr import ocr_columns
from mcc.preprocess.render import render_pages
from mcc.preprocess.segment import segment_pages
from mcc.proofread.server import run_proofread_server
from mcc.stats import collect_stats, format_stats_lines, update_readme_stats


def build_parser() -> argparse.ArgumentParser:
    repo_root = Path(__file__).resolve().parents[1]
    default_pdf = repo_root / "raw" / "modern-chinese-common-words.pdf"
    default_out = repo_root / "pre" / "pages"
    default_merged = (
        repo_root / "post" / "merged" / "modern-chinese-common-words.csv"
    )
    parser = argparse.ArgumentParser(prog="mcc")
    subparsers = parser.add_subparsers(dest="command", required=True)

    render_parser = subparsers.add_parser(
        "render", help="Render PDF pages to PNG images"
    )
    render_parser.add_argument(
        "--pdf", default=default_pdf, type=Path, help="Input PDF path"
    )
    render_parser.add_argument(
        "--out", default=default_out, type=Path, help="Output directory"
    )
    render_parser.add_argument("--dpi", type=int, default=250, help="Render DPI")
    render_parser.add_argument(
        "--start-page", type=int, default=1, help="1-based start page"
    )
    render_parser.add_argument(
        "--end-page", type=int, default=None, help="1-based end page (inclusive)"
    )
    render_parser.add_argument(
        "--skip-existing", action="store_true", help="Skip pages already rendered"
    )
    render_parser.add_argument(
        "--no-progress", action="store_true", help="Disable the progress bar"
    )
    render_parser.set_defaults(func=cmd_render)

    segment_parser = subparsers.add_parser(
        "segment", help="Crop headers/footers and split into 5 columns"
    )
    segment_parser.add_argument(
        "--in",
        dest="in_dir",
        default=default_out,
        type=Path,
        help="Input image directory",
    )
    segment_parser.add_argument(
        "--out",
        dest="out_dir",
        default=repo_root / "pre" / "columns",
        type=Path,
        help="Output directory",
    )
    segment_parser.add_argument(
        "--start-page", type=int, default=1, help="1-based start page"
    )
    segment_parser.add_argument(
        "--end-page", type=int, default=None, help="1-based end page (inclusive)"
    )
    segment_parser.add_argument(
        "--threshold", type=int, default=None, help="Manual grayscale threshold (0-255)"
    )
    segment_parser.add_argument(
        "--analysis-width", type=int, default=800, help="Downscale width for analysis"
    )
    segment_parser.add_argument(
        "--row-threshold", type=float, default=0.01, help="Row ink density threshold"
    )
    segment_parser.add_argument(
        "--row-window", type=int, default=5, help="Smoothing window for row density"
    )
    segment_parser.add_argument(
        "--min-run", type=int, default=5, help="Minimum run length for row clusters"
    )
    segment_parser.add_argument(
        "--pad", type=int, default=6, help="Padding in pixels around crop box"
    )
    segment_parser.add_argument(
        "--skip-existing", action="store_true", help="Skip pages already segmented"
    )
    segment_parser.add_argument(
        "--no-progress", action="store_true", help="Disable the progress bar"
    )
    segment_parser.set_defaults(func=cmd_segment)

    ocr_parser = subparsers.add_parser(
        "ocr", help="Run Tesseract OCR over segmented column images"
    )
    ocr_parser.add_argument(
        "--in",
        dest="in_dir",
        default=repo_root / "pre" / "columns",
        type=Path,
        help="Input column image directory",
    )
    ocr_parser.add_argument(
        "--out",
        dest="out_dir",
        default=repo_root / "post" / "csv",
        type=Path,
        help="Output directory",
    )
    ocr_parser.add_argument(
        "--start-page", type=int, default=1, help="1-based start page"
    )
    ocr_parser.add_argument(
        "--end-page", type=int, default=None, help="1-based end page (inclusive)"
    )
    ocr_parser.add_argument(
        "--lang",
        default="chi_sim+eng",
        help="Tesseract language(s), e.g. chi_sim+eng",
    )
    ocr_parser.add_argument("--psm", type=int, default=6, help="Tesseract PSM mode")
    ocr_parser.add_argument(
        "--oem", type=int, default=None, help="Tesseract OCR engine mode"
    )
    ocr_parser.add_argument(
        "--tessdata-dir",
        type=Path,
        default=None,
        help="Optional tessdata directory override",
    )
    ocr_parser.add_argument(
        "--skip-existing", action="store_true", help="Skip columns already OCRed"
    )
    ocr_parser.add_argument(
        "--no-progress", action="store_true", help="Disable the progress bar"
    )
    ocr_parser.set_defaults(func=cmd_ocr)

    proofread_parser = subparsers.add_parser(
        "proofread", help="Launch the proofreading web app"
    )
    proofread_parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Local server port (0 picks a random free port)",
    )
    proofread_parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open a browser automatically",
    )
    proofread_parser.add_argument(
        "--root",
        type=Path,
        default=repo_root,
        help="Repository root used for default paths",
    )
    proofread_parser.set_defaults(func=cmd_proofread)

    merge_parser = subparsers.add_parser(
        "merge", help="Merge proofread CSVs into a single dataset"
    )
    merge_parser.add_argument(
        "--csv",
        dest="csv_dir",
        default=repo_root / "post" / "csv",
        type=Path,
        help="Input CSV directory",
    )
    merge_parser.add_argument(
        "--meta",
        dest="meta_dir",
        default=repo_root / "post" / "meta",
        type=Path,
        help="Metadata directory",
    )
    merge_parser.add_argument(
        "--out",
        default=repo_root / "post" / "merged" / "modern-chinese-common-words.csv",
        type=Path,
        help="Output merged CSV path",
    )
    merge_parser.add_argument(
        "--stats",
        choices=["comments", "none"],
        default="comments",
        help="Write stats header comments",
    )
    merge_parser.set_defaults(func=cmd_merge)

    publish_parser = subparsers.add_parser(
        "publish", help="Generate static site for GitHub Pages"
    )
    publish_parser.add_argument(
        "--site-dir",
        default=repo_root / "docs",
        type=Path,
        help="Output directory for the published site",
    )
    publish_parser.add_argument(
        "--csv-url",
        default=DEFAULT_CSV_URL,
        help="Merged CSV URL for the published site",
    )
    publish_parser.add_argument(
        "--title",
        default=DEFAULT_TITLE,
        help="Site title for the published site",
    )
    publish_parser.set_defaults(func=cmd_publish)

    stats_parser = subparsers.add_parser(
        "stats", help="Show proofreading progress stats"
    )
    stats_parser.add_argument(
        "--csv",
        dest="csv_dir",
        default=repo_root / "post" / "csv",
        type=Path,
        help="Input CSV directory",
    )
    stats_parser.add_argument(
        "--meta",
        dest="meta_dir",
        default=repo_root / "post" / "meta",
        type=Path,
        help="Metadata directory",
    )
    stats_parser.add_argument(
        "--readme",
        nargs="?",
        const=repo_root / "README.md",
        default=None,
        type=Path,
        help="Update README stats block (default: repo README)",
    )
    stats_parser.set_defaults(func=cmd_stats)

    dx_parser = subparsers.add_parser("dx", help="Diagnostics for merged CSV")
    dx_subparsers = dx_parser.add_subparsers(dest="dx_command", required=True)

    dx_index_parser = dx_subparsers.add_parser(
        "index", help="Check proofread index continuity"
    )
    dx_index_parser.add_argument(
        "--merged",
        default=default_merged,
        type=Path,
        help="Merged CSV path",
    )
    dx_index_parser.add_argument(
        "--csv",
        dest="csv_dir",
        default=repo_root / "post" / "csv",
        type=Path,
        help="Source CSV directory for page/col lookup",
    )
    dx_index_parser.set_defaults(func=cmd_dx_index)

    dx_dup_parser = dx_subparsers.add_parser(
        "duplicates",
        aliases=["dupicates"],
        help="List duplicate words",
    )
    dx_dup_parser.add_argument(
        "--merged",
        default=default_merged,
        type=Path,
        help="Merged CSV path",
    )
    dx_dup_parser.add_argument(
        "--csv",
        dest="csv_dir",
        default=repo_root / "post" / "csv",
        type=Path,
        help="Source CSV directory for page/col lookup",
    )
    dx_dup_parser.set_defaults(func=cmd_dx_duplicates)

    dx_homophone_parser = dx_subparsers.add_parser(
        "homophone",
        help="List words that share the same pinyin",
    )
    dx_homophone_parser.add_argument(
        "--merged",
        default=default_merged,
        type=Path,
        help="Merged CSV path",
    )
    dx_homophone_parser.add_argument(
        "--csv",
        dest="csv_dir",
        default=repo_root / "post" / "csv",
        type=Path,
        help="Source CSV directory for page/col lookup",
    )
    tone_group = dx_homophone_parser.add_mutually_exclusive_group()
    tone_group.add_argument(
        "--tone",
        action="store_true",
        help="Match pinyin including tones",
    )
    tone_group.add_argument(
        "--no-tone",
        dest="tone",
        action="store_false",
        help="Ignore tones when grouping (default)",
    )
    dx_homophone_parser.set_defaults(func=cmd_dx_homophone, tone=False)

    dx_heteronym_parser = dx_subparsers.add_parser(
        "heteronym",
        help="List words with multiple pronunciations",
    )
    dx_heteronym_parser.add_argument(
        "--merged",
        default=default_merged,
        type=Path,
        help="Merged CSV path",
    )
    dx_heteronym_parser.add_argument(
        "--csv",
        dest="csv_dir",
        default=repo_root / "post" / "csv",
        type=Path,
        help="Source CSV directory for page/col lookup",
    )
    heteronym_tone_group = dx_heteronym_parser.add_mutually_exclusive_group()
    heteronym_tone_group.add_argument(
        "--tone",
        action="store_true",
        help="Match pinyin including tones (default)",
    )
    heteronym_tone_group.add_argument(
        "--no-tone",
        dest="tone",
        action="store_false",
        help="Ignore tones when grouping",
    )
    dx_heteronym_parser.set_defaults(func=cmd_dx_heteronym, tone=True)

    dx_typo_parser = dx_subparsers.add_parser(
        "typo",
        aliases=["type"],
        help="List words missing from CC-CEDICT",
    )
    dx_typo_parser.add_argument(
        "--merged",
        default=default_merged,
        type=Path,
        help="Merged CSV path",
    )
    dx_typo_parser.add_argument(
        "--csv",
        dest="csv_dir",
        default=repo_root / "post" / "csv",
        type=Path,
        help="Source CSV directory for page/col lookup",
    )
    dx_typo_parser.add_argument(
        "--pinyin",
        action="store_true",
        help="Also flag CC-CEDICT pinyin mismatches",
    )
    dx_typo_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write results to a file instead of stderr",
    )
    typo_tone_group = dx_typo_parser.add_mutually_exclusive_group()
    typo_tone_group.add_argument(
        "--tone",
        action="store_true",
        help="Match pinyin including tones",
    )
    typo_tone_group.add_argument(
        "--no-tone",
        dest="tone",
        action="store_false",
        help="Ignore tones when matching pinyin (default)",
    )
    dx_typo_parser.set_defaults(func=cmd_dx_typo, tone=False, pinyin=False)

    return parser


def cmd_render(args: argparse.Namespace) -> None:
    render_pages(
        pdf_path=args.pdf,
        out_dir=args.out,
        dpi=args.dpi,
        start_page=args.start_page,
        end_page=args.end_page,
        skip_existing=args.skip_existing,
        no_progress=args.no_progress,
    )


def cmd_segment(args: argparse.Namespace) -> None:
    segment_pages(
        in_dir=args.in_dir,
        out_dir=args.out_dir,
        start_page=args.start_page,
        end_page=args.end_page,
        threshold=args.threshold,
        analysis_width=args.analysis_width,
        row_window=args.row_window,
        row_threshold=args.row_threshold,
        min_run=args.min_run,
        pad=args.pad,
        skip_existing=args.skip_existing,
        no_progress=args.no_progress,
        quantiles=(0.999, 0.995, 0.99, 0.985),
        max_line_width=3,
        edge_margin_ratio=0.2,
    )


def cmd_ocr(args: argparse.Namespace) -> None:
    ocr_columns(
        in_dir=args.in_dir,
        out_dir=args.out_dir,
        start_page=args.start_page,
        end_page=args.end_page,
        lang=args.lang,
        psm=args.psm,
        oem=args.oem,
        tessdata_dir=args.tessdata_dir,
        skip_existing=args.skip_existing,
        no_progress=args.no_progress,
    )


def cmd_proofread(args: argparse.Namespace) -> None:
    web_root = Path(__file__).resolve().parent / "proofread" / "web"
    run_proofread_server(
        web_root=web_root,
        repo_root=args.root,
        port=args.port,
        open_browser=not args.no_open,
    )


def cmd_merge(args: argparse.Namespace) -> None:
    merge_csv(
        csv_dir=args.csv_dir,
        meta_dir=args.meta_dir,
        out_path=args.out,
        stats_mode=args.stats,
    )


def cmd_publish(args: argparse.Namespace) -> None:
    publish_site(
        site_dir=args.site_dir,
        csv_url=args.csv_url,
        title=args.title,
    )


def cmd_stats(args: argparse.Namespace) -> None:
    stats = collect_stats(csv_dir=args.csv_dir, meta_dir=args.meta_dir)
    lines = format_stats_lines(stats)
    print("\n".join(lines))
    if args.readme is not None:
        update_readme_stats(args.readme, stats)


def cmd_dx_index(args: argparse.Namespace) -> None:
    check_proofread_index_continuity(args.merged, csv_dir=args.csv_dir)


def cmd_dx_duplicates(args: argparse.Namespace) -> None:
    find_duplicate_words(args.merged, csv_dir=args.csv_dir)


def cmd_dx_homophone(args: argparse.Namespace) -> None:
    find_homophones(args.merged, csv_dir=args.csv_dir, tone=args.tone)


def cmd_dx_heteronym(args: argparse.Namespace) -> None:
    find_heteronyms(args.merged, csv_dir=args.csv_dir, tone=args.tone)


def cmd_dx_typo(args: argparse.Namespace) -> None:
    if args.output is None:
        find_typo_words(
            args.merged,
            csv_dir=args.csv_dir,
            use_pinyin=args.pinyin,
            tone=args.tone,
        )
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as output_file:
        find_typo_words(
            args.merged,
            csv_dir=args.csv_dir,
            use_pinyin=args.pinyin,
            tone=args.tone,
            console=Console(
                file=output_file,
                force_terminal=False,
                color_system=None,
                stderr=False,
            ),
        )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
