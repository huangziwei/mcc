from __future__ import annotations

import base64
import csv
import json
import os
import re
import shutil
import urllib.error
import urllib.request
from collections import Counter
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
_RANK_LINE_RE = re.compile(
    r"^\s*(?:[-*•]\s*)?(?:\(?(\d+)\)?)\s*(?:[,\t|:.\-]\s*)?(.*)$"
)
_TAG_PAIR_RE = re.compile(
    r"<rank>\s*(\d+)\s*</rank>\s*<word>\s*([^<]+)\s*</word>",
    re.IGNORECASE,
)
_TAG_WORD_RE = re.compile(r"<word>\s*([^<]+)\s*</word>", re.IGNORECASE)
_UNICODE_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")

DEFAULT_PROMPT = (
    "Extract the Chinese text in the image along with their ranks."
    "In the image, the rank is on the left of the Chinese word."
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


def decode_unicode_escapes(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        return chr(int(match.group(1), 16))

    return _UNICODE_ESCAPE_RE.sub(replace, text)


def normalize_ollama_text(text: str) -> str:
    if "\\n" in text or "\\t" in text or "\\r" in text:
        text = text.replace("\\r", "\r").replace("\\n", "\n").replace("\\t", "\t")
    if "\\u" in text:
        text = decode_unicode_escapes(text)
    return text


def resolve_prompt(prompt: str | None, prompt_path: Path | None) -> str:
    if prompt and prompt_path:
        raise SystemExit("Use only one of --prompt or --prompt-file.")
    if prompt_path is not None:
        text = prompt_path.read_text(encoding="utf-8")
        return normalize_ollama_text(text)
    if prompt is not None:
        return normalize_ollama_text(prompt)
    return DEFAULT_PROMPT


def render_prompt(prompt_text: str, image_path: Path) -> str:
    return prompt_text.replace("{image_path}", str(image_path)).replace(
        "{image_name}", image_path.name
    )


def parse_ollama_output(text: str) -> tuple[list[tuple[str, str]], bool]:
    text = normalize_ollama_text(text)

    tag_pairs = _TAG_PAIR_RE.findall(text)
    if tag_pairs:
        rows: list[tuple[str, str]] = []
        for rank, word_text in tag_pairs:
            word = "".join(_CJK_RE.findall(word_text))
            if not word:
                continue
            rows.append((str(int(rank)), word))
        if rows:
            return rows, False

    tag_words = _TAG_WORD_RE.findall(text)
    if tag_words:
        words = ["".join(_CJK_RE.findall(word)) for word in tag_words]
        words = [word for word in words if word]
        if words:
            return [(str(idx + 1), word) for idx, word in enumerate(words)], True

    rows: list[tuple[str, str]] = []
    saw_structured = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("```"):
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
        if not word:
            if rest and _LATIN_RE.search(rest):
                continue
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


def read_csv_rows(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.reader(handle))


def normalize_pair(row: list[str]) -> tuple[str, str] | None:
    if not row:
        return None
    rank = row[0].strip() if row else ""
    word = row[1].strip() if len(row) > 1 else ""
    if rank.isdigit():
        rank = str(int(rank))
    if not rank and not word:
        return None
    return rank, word


def compare_csv_rows(
    actual_path: Path, expected_path: Path
) -> tuple[int, int, int, list[str]]:
    expected_rows = read_csv_rows(expected_path)
    actual_rows = read_csv_rows(actual_path)
    expected_pairs = [
        pair for pair in (normalize_pair(row) for row in expected_rows) if pair
    ]
    actual_pairs = [
        pair for pair in (normalize_pair(row) for row in actual_rows) if pair
    ]

    expected_by_rank: dict[str, list[str]] = {}
    expected_order: list[str] = []
    seen_expected: set[str] = set()
    for rank, word in expected_pairs:
        expected_by_rank.setdefault(rank, []).append(word)
        if rank not in seen_expected:
            expected_order.append(rank)
            seen_expected.add(rank)

    actual_by_rank: dict[str, list[str]] = {}
    actual_order: list[str] = []
    seen_actual: set[str] = set()
    for rank, word in actual_pairs:
        actual_by_rank.setdefault(rank, []).append(word)
        if rank not in seen_actual:
            actual_order.append(rank)
            seen_actual.add(rank)

    matched_rows = 0
    for rank, expected_words in expected_by_rank.items():
        actual_words = actual_by_rank.get(rank, [])
        if not actual_words:
            continue
        expected_counts = Counter(expected_words)
        actual_counts = Counter(actual_words)
        matched_rows += sum((expected_counts & actual_counts).values())

    mismatches: list[str] = []
    for rank in expected_order:
        expected_words = expected_by_rank.get(rank, [])
        actual_words = actual_by_rank.get(rank)
        if actual_words is None:
            mismatches.append(f"rank {rank}: missing (expected {expected_words})")
            continue
        if Counter(expected_words) == Counter(actual_words):
            continue
        if len(expected_words) == 1 and len(actual_words) == 1:
            mismatches.append(
                f"rank {rank}: expected {expected_words[0]} actual {actual_words[0]}"
            )
        else:
            mismatches.append(
                f"rank {rank}: expected {expected_words} actual {actual_words}"
            )

    for rank in actual_order:
        if rank in expected_by_rank:
            continue
        actual_words = actual_by_rank.get(rank, [])
        mismatches.append(f"rank {rank}: extra (actual {actual_words})")

    return matched_rows, len(expected_pairs), len(actual_pairs), mismatches


def run_ollama_generate(
    host: str,
    model: str,
    prompt: str,
    image_path: Path,
    timeout: float,
    options: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
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
        return "", result
    return response_text, result


def run_ollama_chat(
    host: str,
    model: str,
    prompt: str,
    image_path: Path,
    timeout: float,
    options: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
        "stream": False,
    }
    if options:
        payload["options"] = options

    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{host}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        message = f"Ollama chat request failed ({exc.code})."
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

    message = result.get("message", {})
    if isinstance(message, dict):
        content = message.get("content")
        if content is not None:
            return content, result
    response_text = result.get("response")
    if response_text is None:
        return "", result
    return response_text, result


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
    prompt: str | None,
    prompt_file: Path | None,
    limit: int | None,
    compare_dir: Path | None,
    dump_raw: bool,
    dump_json: bool,
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
    if limit is not None:
        if limit < 1:
            raise SystemExit("--limit must be >= 1.")
        selected = selected[:limit]

    out_dir.mkdir(parents=True, exist_ok=True)
    if compare_dir is not None and not compare_dir.exists():
        raise SystemExit(f"Ground truth directory not found: {compare_dir}")
    host = resolve_ollama_host(host)
    prompt_text = resolve_prompt(prompt, prompt_file)
    options = {"temperature": temperature, "num_predict": num_predict}
    ollama_ready = False
    raw_dir = out_dir / "raw" if dump_raw else None
    json_dir = out_dir / "raw-json" if dump_json else None

    def ensure_ollama() -> None:
        nonlocal ollama_ready
        if ollama_ready:
            return
        ensure_model_available(host=host, model=model, timeout=timeout)
        ollama_ready = True

    def write_raw(page_num: int, col_num: int, label: str, text: str) -> None:
        if raw_dir is None:
            return
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path = raw_dir / f"page-{page_num:04d}-col-{col_num}-{label}.txt"
        raw_path.write_text(text, encoding="utf-8")

    def write_json(
        page_num: int, col_num: int, label: str, payload: dict[str, Any]
    ) -> None:
        if json_dir is None:
            return
        json_dir.mkdir(parents=True, exist_ok=True)
        json_path = json_dir / f"page-{page_num:04d}-col-{col_num}-{label}.json"
        json_path.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

    def process_one(page_num: int, col_num: int, path: Path) -> None:
        csv_path = out_dir / f"page-{page_num:04d}-col-{col_num}.csv"

        if skip_existing and csv_path.exists():
            console.log(f"Skip page {page_num} col {col_num} (CSV exists)")
            return

        ensure_ollama()
        prompt_for_image = render_prompt(prompt_text, path)
        response_text, response_payload = run_ollama_generate(
            host=host,
            model=model,
            prompt=prompt_for_image,
            image_path=path,
            timeout=timeout,
            options=options,
        )
        if dump_raw:
            write_raw(page_num, col_num, "generate", response_text)
        if dump_json:
            write_json(page_num, col_num, "generate", response_payload)
        if not response_text.strip():
            console.log(
                f"Warning: empty response from /api/generate for page {page_num} col {col_num}."
            )
        rows, used_fallback = parse_ollama_output(response_text)
        if not rows:
            console.log(
                f"Warning: no parsed rows from /api/generate for page {page_num} col {col_num}. "
                "Retrying via /api/chat."
            )
            response_text, response_payload = run_ollama_chat(
                host=host,
                model=model,
                prompt=prompt_for_image,
                image_path=path,
                timeout=timeout,
                options=options,
            )
            if dump_raw:
                write_raw(page_num, col_num, "chat", response_text)
            if dump_json:
                write_json(page_num, col_num, "chat", response_payload)
            if not response_text.strip():
                console.log(
                    f"Warning: empty response from /api/chat for page {page_num} col {col_num}."
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
        if compare_dir is not None:
            expected_path = compare_dir / csv_path.name
            if expected_path.exists():
                matched, expected_total, actual_total, mismatches = compare_csv_rows(
                    actual_path=csv_path,
                    expected_path=expected_path,
                )
                accuracy = matched / expected_total if expected_total else 0.0
                console.log(
                    f"Compare {csv_path.name}: {accuracy:.2%} "
                    f"({matched}/{expected_total}), actual rows {actual_total}"
                )
                if mismatches:
                    for diff in mismatches:
                        console.log(f"Diff {csv_path.name}: {diff}")
            else:
                console.log(
                    f"Warning: ground truth missing for {csv_path.name} in {compare_dir}"
                )
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
            progress.update(task_id, description=f"OCR page {page_num} col {col_num}")
            process_one(page_num, col_num, path)
            progress.advance(task_id)

    console.log(f"Wrote OCR CSV for pages {start_page}-{end_page} to {out_dir}")
