from __future__ import annotations

import json
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


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
