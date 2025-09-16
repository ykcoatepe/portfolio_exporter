"""Minimal FastAPI + WebSocket server for PSD.

This module intentionally imports FastAPI/uvicorn lazily so importing the
package does not require those optional dependencies. The HTML served at `/`
includes minimal CSS/JS and connects to the `/ws` endpoint.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

# Connection registry (per-process)
_clients: set[Any] = set()


def _html_page() -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Portfolio Sentinel</title>"
        "<style>body{font-family:system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif;"
        "margin:0;padding:0;background:#0b0e11;color:#e6e6e6}"
        "header{position:sticky;top:0;background:#11151a;border-bottom:1px solid #222;"
        "padding:10px 14px}"
        "table{width:100%;border-collapse:collapse}th,td{border-bottom:1px solid #222;"
        "padding:8px 10px;text-align:left}"
        "tr:nth-child(even){background:#0f1216}.muted{opacity:.8;font-size:.9em}"
        "</style></head><body>"
        "<header id='banner'>Loading…</header>"
        "<table><thead><tr><th>UID</th><th>Sleeve</th><th>Kind</th><th>R</th><th>Stop</th><th>Target</th><th>Mark</th><th>Alert</th></tr></thead>"
        "<tbody id='rows'></tbody></table>"
        "<script>\n"
        "const url=`ws://${location.host}/ws`;\n"
        "function render(dto){try{const b=document.getElementById('banner');"
        "const r=document.getElementById('rows');\n"
        "const snap=dto.snapshot||{};const regime=snap.band||'-';const db=(snap.delta_beta??0).toFixed(2);\n"
        "const vr=(snap.var95_1d??0).toFixed(0);const mu=((snap.margin_used??0)*100).toFixed(1);\n"
        "b.innerHTML='<strong>Regime:</strong> ' + regime + ' <span class=\"muted\">' +"
        "'&nbsp;Δβ=' + db + ' • VaR=' + vr + ' • Margin%=' + mu + '</span>';\n"
        "const rows=(dto.rows||[]).map(function(x){return '<tr><td>' + (x.uid||'') + '</td>' +"
        "'<td>' + (x.sleeve||'') + '</td><td>' + (x.kind||'') + '</td>' +"
        "'<td>' + (x.R??'') + '</td><td>' + (x.stop||'') + '</td>' +"
        "'<td>' + (x.target||'') + '</td><td>' + (x.mark??'') + '</td>' +"
        "'<td>' + (x.alert||'') + '</td></tr>';}).join('');\n"
        "r.innerHTML=rows;}catch(e){console.error(e)}}\n"
        "function connect(delay=500){const ws=new WebSocket(url);\n"
        "ws.onopen=()=>console.log('ws open');\n"
        "ws.onmessage=(e)=>{try{render(JSON.parse(e.data))}catch(err){console.error(err)}};\n"
        "ws.onclose=()=>setTimeout(()=>connect(Math.min(delay*1.6,8000)),delay);\n"
        "ws.onerror=()=>ws.close();}\n"
        "connect();\n"
        "</script></body></html>"
    )


def make_app():  # type: ignore[override]
    """Create and return a FastAPI app instance.

    Imported lazily to avoid hard dependency when unused.
    """
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse, JSONResponse

    app = FastAPI()

    @app.get("/")
    async def index() -> HTMLResponse:  # type: ignore[override]
        return HTMLResponse(content=_html_page())

    @app.get("/healthz")
    async def healthz() -> JSONResponse:  # type: ignore[override]
        return JSONResponse({"ok": True})

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:  # type: ignore[override]
        # Always accept the handshake first to avoid 403
        await ws.accept()
        _clients.add(ws)
        try:
            while True:
                # Passive receive to keep connection alive; ignore payload
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            try:
                _clients.discard(ws)
                await ws.close()
            except Exception:
                pass

    # Trailing-slash variant to tolerate client url typos (e.g., /ws/)
    @app.websocket("/ws/")
    async def ws_endpoint_slash(ws: WebSocket) -> None:  # type: ignore[override]
        await ws_endpoint(ws)

    return app


def broadcast(dto: dict) -> None:
    """Send ``dto`` to all connected clients (best-effort)."""
    if not _clients:
        return
    payload = json.dumps(dto, separators=(",", ":"))

    async def _send_all() -> None:
        living: set[Any] = set()
        for ws in list(_clients):
            try:
                await ws.send_text(payload)
                living.add(ws)
            except Exception:
                # Drop dead sockets silently
                try:
                    await ws.close()
                except Exception:
                    pass
        _clients.clear()
        _clients.update(living)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_send_all())
    else:
        loop.create_task(_send_all())


def pick_free_port(host: str) -> int:
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((host, 0))
        return s.getsockname()[1]
    finally:
        try:
            s.close()
        except Exception:
            pass


def start(host: str = "127.0.0.1", port: int = 8787, *, background: bool = True) -> tuple[str, int]:
    """Run the server with uvicorn.

    When ``background`` is True (default), starts in a daemon thread and
    returns ``(host, port)`` immediately. When False, blocks the caller.
    If ``port`` is 0, a free port is chosen first.
    """
    try:
        import uvicorn  # type: ignore
    except Exception as e:  # pragma: no cover - optional dep
        raise RuntimeError("uvicorn is required to start the web server") from e
    actual_port = int(port) if int(port) != 0 else pick_free_port(host)
    app = make_app()
    # Allow selecting WS backend via env with sensible fallbacks.
    # Supported values: auto (default), websockets, wsproto
    import os as _os

    ws_env = (_os.getenv("PSD_UVICORN_WS", "").strip().lower() or "auto")

    def _run_with_ws(ws_value: str | None) -> None:
        try:
            print(f"[psd-web] starting at http://{host}:{actual_port} (ws={ws_value or 'auto'})")
        except Exception:
            pass
        if ws_value is None:
            uvicorn.run(app, host=host, port=actual_port, log_level="info")
        else:
            uvicorn.run(app, host=host, port=actual_port, log_level="info", ws=ws_value)

    def _serve_with_fallbacks() -> None:
        order: list[str | None]
        if ws_env == "auto":
            order = [None, "websockets", "wsproto"]
        elif ws_env in {"websockets", "wsproto"}:
            order = [ws_env, None, ("wsproto" if ws_env == "websockets" else "websockets")]
        else:
            order = [None, "websockets", "wsproto"]
        last_err: Exception | None = None
        for ws_value in order:
            try:
                _run_with_ws(ws_value)
                return
            except Exception as e:
                last_err = e
                try:
                    print(f"[psd-web] ws backend {ws_value or 'auto'} failed: {e}")
                except Exception:
                    pass
                continue
        if last_err is not None:
            raise last_err

    if not background:
        _serve_with_fallbacks()
        return host, actual_port
    import threading

    th = threading.Thread(target=_serve_with_fallbacks, name="psd-web", daemon=True)
    th.start()
    return host, actual_port
