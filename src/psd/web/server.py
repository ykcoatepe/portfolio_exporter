"""Minimal FastAPI + WebSocket server for PSD.

This module intentionally imports FastAPI/uvicorn lazily so importing the
package does not require those optional dependencies. The HTML served at `/`
includes minimal CSS/JS and connects to the `/ws` endpoint.
"""
from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

# Connection registry (per-process)
_clients: set[Any] = set()
_sse_clients: set[asyncio.Queue[str]] = set()
_last_broadcast_ts: float | None = None


def _html_page() -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Portfolio Sentinel</title>"
        "<style>body{font-family:system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif;"
        "margin:0;padding:0;background:#0b0e11;color:#e6e6e6}"
        "header{position:sticky;top:0;background:#11151a;border-bottom:1px solid #222;"
        "padding:10px 14px}"
        "#ws-status{margin-top:4px;font-size:.85em}"
        "table{width:100%;border-collapse:collapse}th,td{border-bottom:1px solid #222;"
        "padding:8px 10px;text-align:left}"
        "tr:nth-child(even){background:#0f1216}.muted{opacity:.8;font-size:.9em}"
        "</style></head><body>"
        "<header><div id='banner-main'>Loading…</div><div id='ws-status' class='muted'>ws pending…</div></header>"
        "<table><thead><tr><th>UID</th><th>Sleeve</th><th>Kind</th><th>R</th><th>Stop</th><th>Target</th><th>Mark</th><th>Alert</th></tr></thead>"
        "<tbody id='rows'></tbody></table>"
        "<script>\n"
        "const wsUrl=`ws://${location.host}/ws`;\n"
        "const banner=document.getElementById('banner-main');\n"
        "const statusEl=document.getElementById('ws-status');\n"
        "let ws=null;\n"
        "let sse=null;\n"
        "let wsOk=false;\n"
        "let sseOk=false;\n"
        "function render(dto){try{const r=document.getElementById('rows');\n"
        "const snap=dto.snapshot||{};const regime=snap.band||'-';const db=(snap.delta_beta??0).toFixed(2);\n"
        "const vr=(snap.var95_1d??0).toFixed(0);const mu=((snap.margin_used??0)*100).toFixed(1);\n"
        "banner.innerHTML='<strong>Regime:</strong> ' + regime + ' <span class=\"muted\">' +"
        "'&nbsp;Δβ=' + db + ' • VaR=' + vr + ' • Margin%=' + mu + '</span>';\n"
        "const rows=(dto.rows||[]).map(function(x){return '<tr><td>' + (x.uid||'') + '</td>' +"
        "'<td>' + (x.sleeve||'') + '</td><td>' + (x.kind||'') + '</td>' +"
        "'<td>' + (x.R??'') + '</td><td>' + (x.stop||'') + '</td>' +"
        "'<td>' + (x.target||'') + '</td><td>' + ((x.mark===null||x.mark===undefined||x.mark==='')?'—':x.mark) + '</td>' +"
        "'<td>' + (x.alert||'') + '</td></tr>';}).join('');\n"
        "r.innerHTML=rows;}catch(e){console.error(e)}}\n"
        "function startSse(delay=1000){if(sse){return;}sse=new EventSource('/stream');\n"
        "sse.onopen=()=>{sseOk=true;if(!wsOk){statusEl.textContent='SSE connected';}};\n"
        "sse.onmessage=(e)=>{try{render(JSON.parse(e.data));statusEl.dataset.lastPush=Date.now();}catch(err){console.error(err)}};\n"
        "sse.onerror=()=>{sseOk=false;try{sse.close();}catch(_){}sse=null;if(!wsOk){statusEl.textContent='SSE reconnecting…';setTimeout(()=>startSse(Math.min(delay*1.6,8000)),delay);}};\n"
        "}\n"
        "function connect(delay=500){if(ws){try{ws.close();}catch(_){}}ws=new WebSocket(wsUrl);\n"
        "ws.onopen=()=>{wsOk=true;statusEl.textContent='WS connected';if(sse){try{sse.close();}catch(_){ }sse=null;sseOk=false;}};\n"
        "ws.onmessage=(e)=>{try{render(JSON.parse(e.data));statusEl.dataset.lastPush=Date.now();}catch(err){console.error(err)}};\n"
        "ws.onclose=()=>{wsOk=false;statusEl.textContent='WS reconnecting…';startSse();setTimeout(()=>connect(Math.min(delay*1.6,8000)),delay);};\n"
        "ws.onerror=()=>{try{ws.close();}catch(_){}};}\n"
        "connect();\n"
        "async function pollHealth(){try{const res=await fetch('/healthz');if(!res.ok)throw new Error('bad');const data=await res.json();\n"
        "const clients=data.clients??0;const ts=data.last_broadcast_iso||null;\n"
        "let tsText='-';\n"
        "if(ts){const d=new Date(ts);tsText=d.toLocaleTimeString();}\n"
        "const base=wsOk?'WS OK':(sseOk?'SSE OK':'offline');\n"
        "statusEl.textContent=base+' · clients='+clients+' · last push='+tsText;\n"
        "}catch(err){statusEl.textContent='Status unavailable';}}\n"
        "pollHealth();\n"
        "setInterval(pollHealth,5000);\n"
        "</script></body></html>"
    )


def make_app():  # type: ignore[override]
    """Create and return a FastAPI app instance.

    Imported lazily to avoid hard dependency when unused.
    """
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

    app = FastAPI()

    try:
        from fastapi.middleware.cors import CORSMiddleware

        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_origin_regex=r".*",
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    except Exception:
        pass

    @app.get("/")
    async def index() -> HTMLResponse:  # type: ignore[override]
        return HTMLResponse(content=_html_page())

    @app.get("/healthz")
    async def healthz() -> JSONResponse:  # type: ignore[override]
        ts = _last_broadcast_ts
        iso = None
        if ts:
            iso = datetime.fromtimestamp(ts, timezone.utc).isoformat()
        total_clients = len(_clients) + len(_sse_clients)
        return JSONResponse({"ok": True, "clients": total_clients, "last_broadcast": ts, "last_broadcast_iso": iso})

    @app.get("/stream")
    async def stream() -> StreamingResponse:  # type: ignore[override]
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1)
        _sse_clients.add(queue)

        async def _gen() -> Any:
            try:
                while True:
                    payload = await queue.get()
                    yield f"data: {payload}\n\n"
            except asyncio.CancelledError:  # pragma: no cover - client disconnect
                pass
            finally:
                _sse_clients.discard(queue)

        return StreamingResponse(_gen(), media_type="text/event-stream")

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
    global _last_broadcast_ts
    _last_broadcast_ts = time.time()
    payload = json.dumps(dto, separators=(",", ":"))

    for queue in list(_sse_clients):
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:  # pragma: no cover - defensive
                continue

    if not _clients:
        return

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
