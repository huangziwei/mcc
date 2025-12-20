from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from .common import resolve_page_range

try:
    import fitz  # PyMuPDF
except ImportError as exc:
    raise SystemExit("Missing dependency PyMuPDF. Install with: pip install pymupdf") from exc


def render_pages(
    pdf_path: Path,
    out_dir: Path,
    dpi: int,
    start_page: int,
    end_page: int | None,
    skip_existing: bool,
    no_progress: bool,
) -> None:
    if not pdf_path.exists():
        raise SystemExit(f"PDF not found: {pdf_path}")

    out_dir.mkdir(parents=True, exist_ok=True)
    console = Console(stderr=True)

    with fitz.open(str(pdf_path)) as doc:
        start_idx, end_idx = resolve_page_range(doc.page_count, start_page, end_page)
        total_pages = end_idx - start_idx + 1
        page_digits = max(4, len(str(end_idx + 1)))
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)

        if no_progress:
            for page_index in range(start_idx, end_idx + 1):
                page_number = page_index + 1
                out_path = out_dir / f"page-{page_number:0{page_digits}d}.png"
                if skip_existing and out_path.exists():
                    console.log(f"Skip page {page_number} (exists)")
                    continue
                page = doc.load_page(page_index)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                pix.save(str(out_path))
                console.log(f"Rendered page {page_number} -> {out_path.name}")
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
            task_id = progress.add_task("Rendering pages", total=total_pages)
            for page_index in range(start_idx, end_idx + 1):
                page_number = page_index + 1
                progress.update(task_id, description=f"Rendering page {page_number}")
                out_path = out_dir / f"page-{page_number:0{page_digits}d}.png"
                if skip_existing and out_path.exists():
                    console.log(f"Skip page {page_number} (exists)")
                    progress.advance(task_id)
                    continue
                page = doc.load_page(page_index)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                pix.save(str(out_path))
                progress.advance(task_id)
                console.log(f"Rendered page {page_number} -> {out_path.name}")

    console.log(f"Wrote pages {start_idx + 1}-{end_idx + 1} to {out_dir}")
