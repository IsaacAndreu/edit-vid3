"""Local web panel: `python main.py --panel` → http://127.0.0.1:8765

Tabs: Outliers (search), Canal (analysis), Guardados (saved videos) and Ideas (daily ideas).
Only listens on this PC (127.0.0.1); the API keys never reach the browser.
"""

from __future__ import annotations

import json
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import lab
from .context import RunContext
from .ytapi import NoKeysLeft, YouTubeAPI

PAGE = Path(__file__).resolve().parent.parent / "panel" / "index.html"


def _num(query: dict[str, list[str]], name: str, default: float = 0) -> float:
    try:
        return float(query.get(name, [default])[0] or default)
    except ValueError:
        return default


def handle_get(ctx: RunContext, path: str, query: dict[str, list[str]]) -> Any:
    api = YouTubeAPI(ctx)
    if path == "/api/quota":
        return {**api.quota(), "competitors": ctx.section("ideas").get("competitors", []),
                "myChannel": ctx.section("ideas").get("my_channel", ""),
                "queries": ctx.section("lab").get("queries", [])}
    if path == "/api/outliers":
        q = (query.get("q") or [""])[0].strip()
        if not q:
            raise ValueError("Escribe qué buscar")
        return lab.outliers(ctx, q, days=int(_num(query, "days", 365)), duration=(query.get("duration") or ["4plus"])[0],
                            min_ratio=_num(query, "minRatio"), max_subs=int(_num(query, "maxSubs")),
                            min_views=int(_num(query, "minViews")), language=(query.get("lang") or [""])[0],
                            pages=int(_num(query, "pages", 1)), api=api)
    if path == "/api/channel":
        return lab.channel_report(ctx, (query.get("h") or [""])[0], api=api)
    if path == "/api/saved":
        return lab.saved(ctx)
    if path == "/api/ideas":
        folder = ctx.root / "out" / "_ideas"
        files = sorted(folder.glob("20*.md"), reverse=True) if folder.is_dir() else []
        return {"files": [f.name for f in files[:30]],
                "latest": files[0].read_text("utf-8") if files else ""}
    raise FileNotFoundError(path)


def handle_post(ctx: RunContext, path: str, body: dict[str, Any]) -> Any:
    if path == "/api/save":
        return lab.save(ctx, body.get("video") or {}, str(body.get("note") or ""))
    if path == "/api/unsave":
        return lab.unsave(ctx, str(body.get("id") or ""))
    if path == "/api/ideas/run":
        from . import ideas

        out = ideas.run(RunContext.create("_ideas", root=ctx.root))
        return {"file": out.name, "latest": out.read_text("utf-8")}
    raise FileNotFoundError(path)


def make_handler(ctx: RunContext, port: int) -> type[BaseHTTPRequestHandler]:
    allowed = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:  # keep the terminal quiet
            pass

        def _send(self, status: int, payload: Any, kind: str = "application/json") -> None:
            data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", f"{kind}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _run(self, action: Any) -> None:
            try:
                self._send(200, action())
            except FileNotFoundError:
                self._send(404, {"error": "no existe"})
            except (NoKeysLeft, ValueError, RuntimeError) as error:
                self._send(400, {"error": str(error)})
            except Exception as error:
                traceback.print_exc()
                self._send(500, {"error": f"{type(error).__name__}: {error}"})

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path in ("/", "/index.html"):
                self._send(200, PAGE.read_bytes(), "text/html")
                return
            self._run(lambda: handle_get(ctx, url.path, parse_qs(url.query)))

        def do_POST(self) -> None:
            # Only this page may write: blocks other websites from posting to the panel.
            if self.headers.get("Origin") not in allowed or self.headers.get("Content-Type") != "application/json":
                self._send(403, {"error": "origen no permitido"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                self._send(400, {"error": "JSON no válido"})
                return
            self._run(lambda: handle_post(ctx, urlparse(self.path).path, body))

    return Handler


def serve(ctx: RunContext, port: int = 8765, open_browser: bool = True) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(ctx, port))
    url = f"http://127.0.0.1:{port}"
    print(f"Panel en {url}  (Ctrl+C para cerrarlo)")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
