#!/usr/bin/env python3
"""
OCR pipeline CLI for scanned frequency list PDFs.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from mcc.preprocess.ocr import ocr_columns
from mcc.preprocess.render import render_pages
from mcc.preprocess.segment import segment_pages
from mcc.proofread.server import run_proofread_server


def build_parser() -> argparse.ArgumentParser:
    repo_root = Path(__file__).resolve().parents[1]
    default_pdf = repo_root / "raw" / "modern-common-chinese-words.pdf"
    default_out = repo_root / "pre" / "pages"
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


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
