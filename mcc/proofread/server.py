from __future__ import annotations

import io
import json
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import jieba
from rich.console import Console
from pycccedict.cccedict import CcCedict

from mcc.stats import collect_stats, update_readme_stats

_README_STATS_LOCK = threading.Lock()
_CCCEDICT_LOCK = threading.Lock()
_CCCEDICT_WORDS: set[str] | None = None
_JIEBA_LOCK = threading.Lock()
_JIEBA_READY = False
_JIEBA_CACHE: dict[str, bool] = {}


def _load_cccedict_words() -> set[str]:
    global _CCCEDICT_WORDS
    if _CCCEDICT_WORDS is not None:
        return _CCCEDICT_WORDS
    with _CCCEDICT_LOCK:
        if _CCCEDICT_WORDS is not None:
            return _CCCEDICT_WORDS
        ccedict = CcCedict()
        words: set[str] = set()
        for entry in ccedict.get_entries():
            simplified = entry.get("simplified")
            traditional = entry.get("traditional")
            if simplified:
                words.add(simplified)
            if traditional:
                words.add(traditional)
        _CCCEDICT_WORDS = words
    return _CCCEDICT_WORDS


def _filter_missing_with_jieba(words: list[str]) -> list[str]:
    global _JIEBA_READY
    if not words:
        return []
    remaining: list[str] = []
    to_check: list[str] = []
    for word in words:
        cached = _JIEBA_CACHE.get(word)
        if cached is None:
            to_check.append(word)
        elif cached is False:
            remaining.append(word)
    if not to_check:
        return remaining
    with _JIEBA_LOCK:
        if not _JIEBA_READY:
            jieba.initialize()
            _JIEBA_READY = True
        for word in to_check:
            cached = _JIEBA_CACHE.get(word)
            if cached is None:
                freq = jieba.get_FREQ(word)
                cached = bool(freq) and freq > 0
                _JIEBA_CACHE[word] = cached
            if cached is False:
                remaining.append(word)
    return remaining


class ProofreadRequestHandler(SimpleHTTPRequestHandler):
    def __init__(
        self,
        *args: Any,
        directory: str | None = None,
        config: dict[str, str] | None = None,
        repo_root: Path | None = None,
        allowed_read_dirs: list[Path] | None = None,
        allowed_write_dirs: list[Path] | None = None,
        **kwargs: Any,
    ) -> None:
        self._config = config or {}
        self._repo_root = repo_root
        self._allowed_read_dirs = allowed_read_dirs or []
        self._allowed_write_dirs = allowed_write_dirs or []
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self) -> None:  # noqa: N802 - upstream method name
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/config.json":
            payload = json.dumps(self._config).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if path.startswith("/api/"):
            handled = self._handle_api_get(parsed)
            if handled:
                return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802 - upstream method name
        parsed = urlparse(self.path)
        if parsed.path == "/api/write":
            self._handle_api_write(parsed)
            return
        if parsed.path == "/api/readme-stats":
            self._handle_api_readme_stats()
            return
        if parsed.path == "/api/cccedict-check":
            self._handle_api_cccedict_check()
            return
        self.send_error(404, "Unknown endpoint")

    def _handle_api_get(self, parsed) -> bool:
        if parsed.path == "/api/list":
            params = parse_qs(parsed.query)
            dir_value = params.get("dir", [None])[0]
            ext_value = params.get("ext", [""])[0]
            if not dir_value:
                self.send_error(400, "Missing dir parameter")
                return True
            target = self._resolve_path(dir_value, allow_write=False)
            if not target or not target.is_dir():
                self.send_error(404, "Directory not found")
                return True
            exts = [ext.strip().lower() for ext in ext_value.split(",") if ext.strip()]
            files = []
            for entry in target.iterdir():
                if not entry.is_file():
                    continue
                if exts and entry.suffix.lower().lstrip(".") not in exts:
                    continue
                files.append(entry.name)
            payload = json.dumps({"files": sorted(files)}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return True
        if parsed.path in {"/api/read", "/api/file"}:
            params = parse_qs(parsed.query)
            path_value = params.get("path", [None])[0]
            if not path_value:
                self.send_error(400, "Missing path parameter")
                return True
            target = self._resolve_path(path_value, allow_write=False)
            if not target or not target.is_file():
                self.send_error(404, "File not found")
                return True
            data = target.read_bytes()
            content_type = "application/octet-stream"
            if target.suffix.lower() == ".json":
                content_type = "application/json"
            elif target.suffix.lower() == ".csv":
                content_type = "text/csv; charset=utf-8"
            elif target.suffix.lower() in {".png"}:
                content_type = "image/png"
            elif target.suffix.lower() in {".jpg", ".jpeg"}:
                content_type = "image/jpeg"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return True
        return False

    def _handle_api_write(self, parsed) -> None:
        params = parse_qs(parsed.query)
        path_value = params.get("path", [None])[0]
        if not path_value:
            self.send_error(400, "Missing path parameter")
            return
        target = self._resolve_path(path_value, allow_write=True)
        if not target:
            self.send_error(403, "Path not allowed")
            return
        content_length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(content_length)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        self.send_response(200)
        self.end_headers()

    def _handle_api_readme_stats(self) -> None:
        if self._repo_root is None:
            self.send_error(500, "Server not configured")
            return
        config = self._config or {}
        csv_dir_value = config.get("default_csv_dir") or "post/csv"
        meta_dir_value = config.get("default_meta_dir") or "post/meta"
        readme_value = config.get("readme_stats_path") or "README.md"

        csv_dir = self._resolve_path(csv_dir_value, allow_write=False)
        meta_dir = self._resolve_path(meta_dir_value, allow_write=False)
        readme_path = self._resolve_repo_path(readme_value)
        if not csv_dir or not meta_dir or not readme_path:
            self.send_error(403, "Stats paths not allowed")
            return

        if not _README_STATS_LOCK.acquire(blocking=False):
            payload = json.dumps({"status": "busy"}).encode("utf-8")
            self.send_response(202)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        quiet_console = Console(file=io.StringIO())
        try:
            stats = collect_stats(csv_dir=csv_dir, meta_dir=meta_dir, console=quiet_console)
            update_readme_stats(readme_path, stats, console=quiet_console)
        except SystemExit as exc:
            self.send_error(400, str(exc))
            return
        except Exception:
            self.send_error(500, "Failed to update README stats")
            return
        finally:
            _README_STATS_LOCK.release()

        payload = json.dumps({"status": "ok"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle_api_cccedict_check(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(content_length)
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON payload")
            return
        words = payload.get("words")
        if not isinstance(words, list):
            self.send_error(400, "Missing words list")
            return
        normalized: set[str] = set()
        for word in words:
            if word is None:
                continue
            text = str(word).strip()
            if text:
                normalized.add(text)
        if not normalized:
            response = json.dumps({"missing": []}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            return
        try:
            ccedict_words = _load_cccedict_words()
        except Exception:
            self.send_error(500, "Failed to load CC-CEDICT")
            return
        missing = sorted(normalized.difference(ccedict_words))
        if missing:
            try:
                missing = _filter_missing_with_jieba(missing)
            except Exception:
                self.send_error(500, "Failed to load Jieba dictionary")
                return
        response = json.dumps({"missing": missing}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def _resolve_repo_path(self, raw_path: str) -> Path | None:
        if self._repo_root is None:
            return None
        candidate = (self._repo_root / raw_path).resolve()
        if not candidate.is_relative_to(self._repo_root):
            return None
        return candidate

    def _resolve_path(self, raw_path: str, *, allow_write: bool) -> Path | None:
        if self._repo_root is None:
            return None
        candidate = (self._repo_root / raw_path).resolve()
        if not candidate.is_relative_to(self._repo_root):
            return None
        allowed = self._allowed_write_dirs if allow_write else self._allowed_read_dirs
        if allowed and not any(candidate.is_relative_to(root) for root in allowed):
            return None
        return candidate


def run_proofread_server(
    web_root: Path,
    repo_root: Path,
    port: int = 8765,
    host: str = "127.0.0.1",
    open_browser: bool = True,
) -> None:
    if not web_root.exists():
        raise SystemExit(f"Web assets not found at {web_root}")

    config = {
        "default_post_dir": "post",
        "default_csv_dir": "post/csv",
        "default_meta_dir": "post/meta",
        "default_columns_dir": "pre/columns",
        "readme_stats_path": "README.md",
        "server_mode": True,
    }

    handler = partial(
        ProofreadRequestHandler,
        directory=str(web_root),
        config=config,
        repo_root=repo_root,
        allowed_read_dirs=[repo_root / "post", repo_root / "pre"],
        allowed_write_dirs=[repo_root / "post"],
    )

    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{server.server_address[1]}/"
    print(f"Proofread app running at {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down proofread server")
    finally:
        server.server_close()
