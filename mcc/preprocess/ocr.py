from __future__ import annotations

import csv
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import median

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

from .common import resolve_page_range

_COLUMN_RE = re.compile(
    r"^page-(\d+)-col-(\d+)\.(?:png|jpe?g|tif|tiff)$", re.IGNORECASE
)
_CJK_RE = re.compile(r"[\u3400-\u9fff]+")
_DIGIT_RE = re.compile(r"\d+")
_LANG_RE = re.compile(r"^[A-Za-z0-9_]+$")
_LATIN_BLACKLIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_TESSERACT_CONFIG = [f"tessedit_char_blacklist={_LATIN_BLACKLIST}"]

try:
    RESAMPLE_BICUBIC = Image.Resampling.BICUBIC
except AttributeError:  # Pillow < 9
    RESAMPLE_BICUBIC = Image.BICUBIC


@dataclass
class LineInfo:
    top: int
    bottom: int
    text: str

    @property
    def center(self) -> float:
        return (self.top + self.bottom) / 2


@dataclass
class RowCandidate:
    center: float
    text: str


@dataclass
class RowSlice:
    top: int
    bottom: int
    text: str


def list_column_images(in_dir: Path) -> list[tuple[int, int, Path]]:
    if not in_dir.exists():
        raise SystemExit(f"Input directory not found: {in_dir}")
    items: list[tuple[int, int, Path]] = []
    for path in in_dir.iterdir():
        if not path.is_file():
            continue
        match = _COLUMN_RE.match(path.name)
        if not match:
            continue
        page_num = int(match.group(1))
        col_num = int(match.group(2))
        items.append((page_num, col_num, path))
    items.sort(key=lambda item: (item[0], item[1]))
    return items


def ensure_tesseract() -> str:
    tesseract = shutil.which("tesseract")
    if not tesseract:
        raise SystemExit(
            "Missing dependency tesseract. Install it and ensure it is on your PATH."
        )
    return tesseract


def validate_languages(
    tesseract_cmd: str, lang: str, tessdata_dir: Path | None
) -> None:
    cmd = [tesseract_cmd, "--list-langs"]
    if tessdata_dir is not None:
        cmd.extend(["--tessdata-dir", str(tessdata_dir)])
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        details = exc.stderr.strip() if exc.stderr else str(exc)
        raise SystemExit(f"Tesseract language check failed: {details}") from exc
    output = "\n".join([result.stdout, result.stderr]).strip()
    languages = {
        line.strip()
        for line in output.splitlines()
        if line.strip() and _LANG_RE.match(line.strip())
    }
    missing = [token for token in lang.split("+") if token and token not in languages]
    if missing:
        missing_list = ", ".join(missing)
        raise SystemExit(
            "Missing Tesseract language data: "
            f"{missing_list}. Install the data or set --tessdata-dir."
        )


def run_tesseract(
    tesseract_cmd: str,
    image_path: Path,
    lang: str,
    psm: int,
    oem: int | None,
    tessdata_dir: Path | None,
    output_format: str | None,
    config: list[str] | None,
) -> str:
    cmd: list[str] = [
        tesseract_cmd,
        str(image_path),
        "stdout",
        "-l",
        lang,
        "--psm",
        str(psm),
        "-c",
        "preserve_interword_spaces=1",
    ]
    if oem is not None:
        cmd.extend(["--oem", str(oem)])
    if tessdata_dir is not None:
        cmd.extend(["--tessdata-dir", str(tessdata_dir)])
    if config:
        for item in config:
            cmd.extend(["-c", item])
    if output_format:
        cmd.append(output_format)

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        details = exc.stderr.strip() if exc.stderr else str(exc)
        raise SystemExit(f"Tesseract failed for {image_path.name}: {details}") from exc

    return result.stdout


def run_tesseract_text(
    tesseract_cmd: str,
    image_path: Path,
    lang: str,
    psm: int,
    oem: int | None,
    tessdata_dir: Path | None,
    config: list[str] | None = None,
) -> str:
    return run_tesseract(
        tesseract_cmd=tesseract_cmd,
        image_path=image_path,
        lang=lang,
        psm=psm,
        oem=oem,
        tessdata_dir=tessdata_dir,
        output_format=None,
        config=config,
    )


def run_tesseract_tsv(
    tesseract_cmd: str,
    image_path: Path,
    lang: str,
    psm: int,
    oem: int | None,
    tessdata_dir: Path | None,
    config: list[str] | None = None,
) -> str:
    return run_tesseract(
        tesseract_cmd=tesseract_cmd,
        image_path=image_path,
        lang=lang,
        psm=psm,
        oem=oem,
        tessdata_dir=tessdata_dir,
        output_format="tsv",
        config=config,
    )


def strip_english_lang(lang: str) -> str:
    parts = [part for part in lang.split("+") if part and part.lower() != "eng"]
    return "+".join(parts) if parts else lang


def parse_tesseract_lines(tsv_text: str) -> list[LineInfo]:
    if not tsv_text.strip():
        return []
    rows = list(csv.DictReader(tsv_text.splitlines(), delimiter="\t"))
    line_boxes: dict[tuple[str, str, str], LineInfo] = {}
    line_words: dict[tuple[str, str, str], list[str]] = {}
    for row in rows:
        level = row.get("level")
        if level == "4":
            key = (row["block_num"], row["par_num"], row["line_num"])
            top = int(row["top"])
            height = int(row["height"])
            line_boxes[key] = LineInfo(top=top, bottom=top + height, text="")
            continue
        if level != "5":
            continue
        key = (row["block_num"], row["par_num"], row["line_num"])
        text = row.get("text", "")
        if text:
            line_words.setdefault(key, []).append(text)
        else:
            line_words.setdefault(key, [])

    lines: list[LineInfo] = []
    for key, line in line_boxes.items():
        words = line_words.get(key, [])
        line_text = " ".join(words).strip()
        lines.append(LineInfo(top=line.top, bottom=line.bottom, text=line_text))
    lines.sort(key=lambda item: item.top)
    return lines


def build_row_slices(lines: list[LineInfo], image_height: int) -> list[RowSlice]:
    if not lines:
        return []
    centers = [line.center for line in lines]
    if len(centers) < 2:
        return [RowSlice(top=line.top, bottom=line.bottom, text=line.text) for line in lines]

    spacings = [centers[i + 1] - centers[i] for i in range(len(centers) - 1)]
    spacing = median(spacings) if spacings else 0.0
    if spacing <= 0:
        return [RowSlice(top=line.top, bottom=line.bottom, text=line.text) for line in lines]

    candidates: list[RowCandidate] = []
    prev_center: float | None = None
    for line in lines:
        center = line.center
        if prev_center is not None:
            while center - prev_center > spacing * 1.5:
                prev_center += spacing
                candidates.append(RowCandidate(center=prev_center, text=""))
        candidates.append(RowCandidate(center=center, text=line.text))
        prev_center = candidates[-1].center

    centers = [candidate.center for candidate in candidates]
    rows: list[RowSlice] = []
    for idx, candidate in enumerate(candidates):
        if idx == 0:
            top = int(round(candidate.center - spacing / 2))
        else:
            top = int(round((centers[idx - 1] + candidate.center) / 2))
        if idx == len(candidates) - 1:
            bottom = int(round(candidate.center + spacing / 2))
        else:
            bottom = int(round((candidate.center + centers[idx + 1]) / 2))
        top = max(0, top)
        bottom = min(image_height, bottom)
        if bottom <= top:
            bottom = min(image_height, top + 1)
        rows.append(RowSlice(top=top, bottom=bottom, text=candidate.text))
    return rows


def extract_rank(text: str) -> str | None:
    digits = _DIGIT_RE.findall(text)
    if not digits:
        return None
    return "".join(digits)


def extract_word(text: str) -> str:
    parts = _CJK_RE.findall(text)
    return "".join(parts)


def parse_ocr_text(text: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    pending_rank: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        matches = list(_DIGIT_RE.finditer(line))
        if matches:
            for idx, match in enumerate(matches):
                rank = match.group(0)
                seg_start = match.end()
                seg_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(line)
                segment = line[seg_start:seg_end]
                word = extract_word(segment)
                if word:
                    rows.append((str(int(rank)), word))
                    pending_rank = None
                else:
                    pending_rank = rank
            continue
        if pending_rank:
            word = extract_word(line)
            if word:
                rows.append((str(int(pending_rank)), word))
                pending_rank = None
    return rows


def choose_rank_anchor(anchors: list[int]) -> int:
    if not anchors:
        return 1
    counts = Counter(anchors)
    anchor, count = counts.most_common(1)[0]
    if count == 1:
        return int(round(median(anchors)))
    return anchor


def build_rank_sequence(texts: list[str]) -> list[str]:
    anchors: list[int] = []
    for idx, text in enumerate(texts):
        rank = extract_rank(text)
        if rank is None:
            continue
        try:
            anchors.append(int(rank) - idx)
        except ValueError:
            continue
    if not anchors:
        return [str(idx + 1) for idx in range(len(texts))]
    anchor = choose_rank_anchor(anchors)
    return [str(anchor + idx) for idx in range(len(texts))]


def ocr_row_text(
    tesseract_cmd: str,
    image: Image.Image,
    row: RowSlice,
    lang: str,
    oem: int | None,
    tessdata_dir: Path | None,
    config: list[str] | None,
    scale: int = 2,
) -> str:
    if row.bottom <= row.top:
        return ""
    pad = 4
    top = max(0, row.top - pad)
    bottom = min(image.height, row.bottom + pad)
    crop = image.crop((0, top, image.width, bottom)).convert("L")
    if scale > 1:
        crop = crop.resize((crop.width * scale, crop.height * scale), resample=RESAMPLE_BICUBIC)
    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        crop.save(tmp.name)
        return run_tesseract_text(
            tesseract_cmd=tesseract_cmd,
            image_path=Path(tmp.name),
            lang=lang,
            psm=7,
            oem=oem,
            tessdata_dir=tessdata_dir,
            config=config,
        )


def write_rank_word_csv(rows: list[tuple[str, str]], csv_path: Path) -> None:
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        for rank, word in rows:
            writer.writerow([rank, word])


def ocr_columns(
    in_dir: Path,
    out_dir: Path,
    start_page: int,
    end_page: int | None,
    lang: str,
    psm: int,
    oem: int | None,
    tessdata_dir: Path | None,
    skip_existing: bool,
    no_progress: bool,
) -> None:
    console = Console(stderr=True)
    items = list_column_images(in_dir)
    if not items:
        raise SystemExit(f"No column images found in: {in_dir}")

    max_page = max(page_num for page_num, _, _ in items)
    start_idx, end_idx = resolve_page_range(max_page, start_page, end_page)
    start_page = start_idx + 1
    end_page = end_idx + 1

    selected = [
        (page_num, col_num, path)
        for page_num, col_num, path in items
        if start_page <= page_num <= end_page
    ]
    if not selected:
        raise SystemExit(f"No column images in range {start_page}-{end_page}.")

    out_dir.mkdir(parents=True, exist_ok=True)
    tesseract_cmd: str | None = None
    langs_checked = False

    def get_tesseract() -> str:
        nonlocal tesseract_cmd, langs_checked
        if tesseract_cmd is None:
            tesseract_cmd = ensure_tesseract()
        if not langs_checked:
            validate_languages(tesseract_cmd, lang=lang, tessdata_dir=tessdata_dir)
            langs_checked = True
        return tesseract_cmd

    def process_one(page_num: int, col_num: int, path: Path) -> None:
        csv_path = out_dir / f"page-{page_num:04d}-col-{col_num}.csv"

        if skip_existing and csv_path.exists():
            console.log(f"Skip page {page_num} col {col_num} (CSV exists)")
            return

        tesseract_cmd = get_tesseract()
        tsv_text = run_tesseract_tsv(
            tesseract_cmd=tesseract_cmd,
            image_path=path,
            lang=lang,
            psm=psm,
            oem=oem,
            tessdata_dir=tessdata_dir,
            config=_TESSERACT_CONFIG,
        )
        lines = parse_tesseract_lines(tsv_text)
        rows: list[tuple[str, str]] = []

        if lines:
            with Image.open(path) as image:
                row_slices = build_row_slices(lines, image.height)
                if row_slices:
                    word_lang = strip_english_lang(lang)
                    row_texts: list[str] = []
                    words: list[str] = []
                    for row in row_slices:
                        row_text = row.text
                        word = extract_word(row_text)
                        if not word:
                            fallback_text = ocr_row_text(
                                tesseract_cmd=tesseract_cmd,
                                image=image,
                                row=row,
                                lang=word_lang,
                                oem=oem,
                                tessdata_dir=tessdata_dir,
                                config=_TESSERACT_CONFIG,
                            ).strip()
                            if fallback_text:
                                row_text = fallback_text
                                word = extract_word(fallback_text)
                        row_texts.append(row_text)
                        words.append(word)
                    ranks = build_rank_sequence(row_texts)
                    rows = list(zip(ranks, words))

        if not rows:
            text = run_tesseract_text(
                tesseract_cmd=tesseract_cmd,
                image_path=path,
                lang=lang,
                psm=psm,
                oem=oem,
                tessdata_dir=tessdata_dir,
                config=_TESSERACT_CONFIG,
            )
            rows = parse_ocr_text(text)
        if not rows:
            console.log(f"Warning: no OCR rows for page {page_num} col {col_num}")
        else:
            missing_words = sum(1 for _, word in rows if not word)
            if missing_words:
                console.log(
                    f"Warning: {missing_words} missing words for page {page_num} col {col_num}"
                )
        write_rank_word_csv(rows, csv_path)
        console.log(
            f"OCR page {page_num} col {col_num} -> {csv_path.name} ({len(rows)} rows)"
        )

    if no_progress:
        for page_num, col_num, path in selected:
            process_one(page_num, col_num, path)
        return

    progress = Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total} columns"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=False,
    )

    with progress:
        task_id = progress.add_task("OCR columns", total=len(selected))
        for page_num, col_num, path in selected:
            progress.update(
                task_id, description=f"OCR page {page_num} col {col_num}"
            )
            process_one(page_num, col_num, path)
            progress.advance(task_id)

    console.log(f"Wrote OCR CSV for pages {start_page}-{end_page} to {out_dir}")
