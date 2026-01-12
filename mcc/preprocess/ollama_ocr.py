from __future__ import annotations

import base64
import json
import os
import re
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

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
from .ocr import list_column_images, parse_ocr_text, write_rank_word_csv

_CJK_RE = re.compile(r"[\u3400-\u9fff]+")
_LATIN_RE = re.compile(r"[A-Za-z]")
_RANK_LINE_RE = re.compile(r"^\s*(\d+)\s*(?:[,\t|:.\-]\s*)?(.*)$")

DEFAULT_PROMPT = (
    "You are an OCR engine. Extract each row's rank number and Chinese word "
    "from the image.\n"
    "Output only the data, one row per line, as: <rank>\\t<word>\n"
    "Use Arabic digits for ranks. Do not add headers, code fences, or commentary."
)


def resolve_ollama_host(host: str | None) -> str:
    raw = host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434"
    if "://" not in raw:
        raw = f"http://{raw}"
    return raw.rstrip("/")


def fetch_ollama_tags(host: str, timeout: float) -> list[str]:
    url = f"{host}/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.load(response)
    except urllib.error.URLError as exc:
        message = (
            f"Ollama server not reachable at {host}. "
            "Start it with `ollama serve` or open the Ollama app."
        )
        if shutil.which("ollama") is None:
            message = (
                f"Ollama server not reachable at {host} and the `ollama` CLI "
                "was not found. Install Ollama and start it, or set OLLAMA_HOST."
            )
        raise SystemExit(message) from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid response from Ollama at {url}.") from exc

    models = payload.get("models", [])
    names = []
    for item in models:
        name = item.get("name")
        if name:
            names.append(name)
    return names


def model_available(model: str, names: list[str]) -> bool:
    if model in names:
        return True
    if ":" not in model:
        prefix = f"{model}:"
        return any(name.startswith(prefix) for name in names)
    return False


def ensure_model_available(host: str, model: str, timeout: float) -> None:
    names = fetch_ollama_tags(host, timeout=timeout)
    if model_available(model, names):
        return
    raise SystemExit(
        f"Ollama model '{model}' not found on {host}. "
        f"Run `ollama pull {model}` on that machine."
    )


def parse_ollama_output(text: str) -> tuple[list[tuple[str, str]], bool]:
    rows: list[tuple[str, str]] = []
    saw_structured = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("|") and line.endswith("|"):
            line = line.strip("|").strip()
        if not line:
            continue
        if set(line.replace("|", "").strip()) <= {"-"}:
            continue
        match = _RANK_LINE_RE.match(line)
        if not match:
            continue
        rank = match.group(1)
        rest = match.group(2).strip()
        word = "".join(_CJK_RE.findall(rest))
        if not word and rest and _LATIN_RE.search(rest):
            continue
        try:
            rank = str(int(rank))
        except ValueError:
            continue
        rows.append((rank, word))
        saw_structured = True
    if saw_structured and rows:
        return rows, False

    rows = parse_ocr_text(text)
    if rows:
        return rows, False

    words = _CJK_RE.findall(text)
    if not words:
        return [], False
    return [(str(idx + 1), word) for idx, word in enumerate(words)], True


def run_ollama_generate(
    host: str,
    model: str,
    prompt: str,
    image_path: Path,
    timeout: float,
    options: dict[str, Any] | None = None,
) -> str:
    image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False,
    }
    if options:
        payload["options"] = options

    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{host}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        message = f"Ollama request failed ({exc.code})."
        if detail:
            message = f"{message} {detail}"
        raise SystemExit(message) from exc
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"Ollama server not reachable at {host}. "
            "Start it with `ollama serve` or open the Ollama app."
        ) from exc
    except json.JSONDecodeError as exc:
        raise SystemExit("Invalid response from Ollama during OCR.") from exc

    if "error" in result:
        raise SystemExit(f"Ollama error: {result['error']}")

    response_text = result.get("response")
    if response_text is None:
        return ""
    return response_text


def ollama_ocr_columns(
    in_dir: Path,
    out_dir: Path,
    start_page: int,
    end_page: int | None,
    model: str,
    host: str | None,
    timeout: float,
    temperature: float,
    num_predict: int,
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
    host = resolve_ollama_host(host)
    options = {"temperature": temperature, "num_predict": num_predict}
    ollama_ready = False

    def ensure_ollama() -> None:
        nonlocal ollama_ready
        if ollama_ready:
            return
        ensure_model_available(host=host, model=model, timeout=timeout)
        ollama_ready = True

    def process_one(page_num: int, col_num: int, path: Path) -> None:
        csv_path = out_dir / f"page-{page_num:04d}-col-{col_num}.csv"

        if skip_existing and csv_path.exists():
            console.log(f"Skip page {page_num} col {col_num} (CSV exists)")
            return

        ensure_ollama()
        response_text = run_ollama_generate(
            host=host,
            model=model,
            prompt=DEFAULT_PROMPT,
            image_path=path,
            timeout=timeout,
            options=options,
        )
        rows, used_fallback = parse_ollama_output(response_text)
        if used_fallback:
            console.log(
                f"Warning: fallback parsing for page {page_num} col {col_num} "
                "(no ranks detected)."
            )

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
