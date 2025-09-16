"""Minimal FastAPI server for the Portfolio Sentinel Dashboard.

The server serves the single-page dashboard at `/` and reuses
`psd.web.app` for stateful JSON endpoints and the SSE stream.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

_HTML_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Portfolio Sentinel Dashboard</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
:root {
  color-scheme: dark;
  font-family: "Inter", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
body {
  margin: 0;
  background: #080b10;
  color: #e6ecf3;
}
header {
  position: sticky;
  top: 0;
  background: rgba(9, 12, 18, 0.97);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid #1f2730;
  padding: 14px 20px 12px;
  z-index: 10;
}
.banner {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}
.banner .title {
  font-size: 1.1rem;
  font-weight: 600;
  letter-spacing: 0.02em;
}
.badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 0.85rem;
  background: #1f2730;
  color: #d8dee6;
}
.badge.warn {
  background: #5a451c;
  color: #f9d27d;
}
.badge.alert {
  background: #5c1f26;
  color: #f5a7a7;
}
.badge.hidden {
  display: none;
}
main {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 28px;
}
.summary-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
}
.card {
  background: #0c1119;
  border: 1px solid #1a222b;
  border-radius: 12px;
  padding: 14px 16px;
}
.card .label {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #8b97a8;
  margin-bottom: 4px;
}
.card .value {
  font-size: 1.5rem;
  font-weight: 600;
  letter-spacing: 0.01em;
}
.section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.section-title {
  font-size: 1.1rem;
  font-weight: 600;
  margin: 0;
}
#breach-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-height: 24px;
}
#breach-list.empty {
  color: #8b97a8;
}
.muted {
  color: #8b97a8;
  font-size: 0.9rem;
}
table {
  width: 100%;
  border-collapse: collapse;
  border-spacing: 0;
  background: #0c1119;
  border: 1px solid #1a222b;
  border-radius: 12px;
  overflow: hidden;
}
th, td {
  padding: 12px 14px;
  border-bottom: 1px solid #1a222b;
  text-align: left;
}
th {
  font-weight: 500;
  text-transform: uppercase;
  font-size: 0.75rem;
  letter-spacing: 0.08em;
  color: #8b97a8;
}
tbody tr:nth-child(2n) {
  background: #0f141d;
}
td.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
td.empty {
  text-align: center;
  padding: 24px 0;
}
#positions-info {
  margin-bottom: 4px;
}
@media (max-width: 720px) {
  header {
    padding: 12px 16px 10px;
  }
  main {
    padding: 16px;
  }
  th, td {
    padding: 10px 12px;
  }
}
</style>
</head>
<body>
<header>
  <div class="banner">
    <div class="title">Portfolio Sentinel</div>
    <span class="badge hidden" id="badge-ibkr">IBKR disconnected</span>
    <span class="badge hidden" id="badge-stale">Stale data: <span id="stale-value">0</span>s</span>
  </div>
  <div class="muted" id="connection-status">Connecting…</div>
</header>
<main>
  <section class="summary-grid">
    <div class="card">
      <div class="label">Last Update</div>
      <div class="value" id="metric-updated">—</div>
    </div>
    <div class="card">
      <div class="label">Positions</div>
      <div class="value" id="metric-positions">—</div>
    </div>
    <div class="card">
      <div class="label">Notional</div>
      <div class="value" id="metric-notional">—</div>
    </div>
    <div class="card">
      <div class="label">Beta</div>
      <div class="value" id="metric-beta">—</div>
    </div>
    <div class="card">
      <div class="label">VaR 1d</div>
      <div class="value" id="metric-var">—</div>
    </div>
    <div class="card">
      <div class="label">Margin Used</div>
      <div class="value" id="metric-margin">—</div>
    </div>
  </section>
  <section class="section">
    <h2 class="section-title">Breaches</h2>
    <div id="breach-list" class="empty muted">No active breaches</div>
  </section>
  <section class="section">
    <h2 class="section-title">Positions</h2>
    <div class="muted" id="positions-info">Waiting for data…</div>
    <table>
      <thead>
        <tr>
          <th>Symbol</th>
          <th>Qty</th>
          <th>Mark</th>
          <th>Delta</th>
          <th>Gamma</th>
          <th>Theta</th>
        </tr>
      </thead>
      <tbody id="positions-body">
        <tr><td colspan="6" class="empty muted">Waiting for positions…</td></tr>
      </tbody>
    </table>
  </section>
</main>
<script>
(function () {
  const store = {
    snapshot: null,
    positions: [],
    risk: {},
    breaches: [],
    health: { ibkr_connected: null, data_age_s: null },
    lastSnapshotMs: 0,
    staleSeconds: 0,
    es: null
  };

  const els = {
    status: document.getElementById('connection-status'),
    badgeIbkr: document.getElementById('badge-ibkr'),
    badgeStale: document.getElementById('badge-stale'),
    staleValue: document.getElementById('stale-value'),
    breachList: document.getElementById('breach-list'),
    positionsInfo: document.getElementById('positions-info'),
    positionsBody: document.getElementById('positions-body'),
    metrics: {
      updated: document.getElementById('metric-updated'),
      positions: document.getElementById('metric-positions'),
      notional: document.getElementById('metric-notional'),
      beta: document.getElementById('metric-beta'),
      var: document.getElementById('metric-var'),
      margin: document.getElementById('metric-margin')
    }
  };

  function setStatus(text) {
    els.status.textContent = text;
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function pick(row, keys) {
    for (let i = 0; i < keys.length; i += 1) {
      const key = keys[i];
      if (row && Object.prototype.hasOwnProperty.call(row, key)) {
        const val = row[key];
        if (val !== undefined && val !== null && val !== '') {
          return val;
        }
      }
    }
    return null;
  }

  function formatNumber(value, digits) {
    const num = Number(value);
    if (!Number.isFinite(num)) {
      return '—';
    }
    const options = {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits
    };
    return num.toLocaleString(undefined, options);
  }

  function formatPercent(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) {
      return '—';
    }
    return formatNumber(num * 100, 1) + '%';
  }

  function formatCurrency(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) {
      return '—';
    }
    return num.toLocaleString(undefined, {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    });
  }

  function formatTime(ms) {
    if (!ms) {
      return '—';
    }
    const d = new Date(ms);
    if (!Number.isFinite(d.getTime())) {
      return '—';
    }
    return d.toLocaleTimeString();
  }

  function parseBreaches(raw) {
    if (!raw) {
      return [];
    }
    if (Array.isArray(raw)) {
      return raw.map((item) => String(item)).filter((item) => item.length > 0);
    }
    if (typeof raw === 'object') {
      return Object.keys(raw).filter((key) => raw[key]);
    }
    return [];
  }

  function applySnapshot(data) {
    if (!data || typeof data !== 'object') {
      return;
    }
    store.snapshot = data;
    store.positions = Array.isArray(data.positions) ? data.positions : [];
    store.risk = data.risk && typeof data.risk === 'object' ? data.risk : {};
    store.lastSnapshotMs = typeof data.ts === 'number' ? data.ts * 1000 : Date.now();
    const snapshotBreaches = parseBreaches(data.breaches);
    store.breaches = snapshotBreaches.length ? snapshotBreaches : [];
    updateStaleTicker();
    render();
    setStatus('Snapshot · ' + formatTime(store.lastSnapshotMs));
  }

  async function loadInitial() {
    try {
      const response = await fetch('/state', { cache: 'no-store' });
      if (!response.ok) {
        throw new Error('HTTP ' + response.status);
      }
      const data = await response.json();
      if (data && !data.empty) {
        applySnapshot(data);
      } else {
        setStatus('Waiting for first snapshot…');
      }
    } catch (err) {
      console.error('state fetch failed', err);
      setStatus('Initial load failed – waiting for stream…');
    }
  }

  function handleBreachEvent(payload) {
    const breaches = parseBreaches(payload && payload.breaches);
    store.breaches = breaches;
    renderBreaches();
    renderBanner();
  }

  function handleHealthEvent(payload) {
    if (!payload || typeof payload !== 'object') {
      return;
    }
    const connected = Boolean(payload.ibkr_connected);
    const age = typeof payload.data_age_s === 'number' ? payload.data_age_s : null;
    store.health = { ibkr_connected: connected, data_age_s: age };
    updateStaleTicker();
    renderBanner();
  }

  function startSse() {
    if (store.es) {
      try {
        store.es.close();
      } catch (e) {
        console.warn('closing prior EventSource failed', e);
      }
    }
    const es = new EventSource('/stream');
    store.es = es;

    es.addEventListener('snapshot', (event) => {
      try {
        applySnapshot(JSON.parse(event.data));
      } catch (err) {
        console.error('snapshot parse failed', err);
      }
    });

    es.addEventListener('breach', (event) => {
      try {
        handleBreachEvent(JSON.parse(event.data));
      } catch (err) {
        console.error('breach parse failed', err);
      }
    });

    es.addEventListener('health', (event) => {
      try {
        handleHealthEvent(JSON.parse(event.data));
      } catch (err) {
        console.error('health parse failed', err);
      }
    });

    es.addEventListener('heartbeat', () => {
      setStatus('Live · heartbeat ' + new Date().toLocaleTimeString());
    });

    es.onerror = () => {
      setStatus('Stream reconnecting…');
    };

    es.onopen = () => {
      setStatus('Stream connected');
    };
  }

  function updateStaleTicker() {
    const nowMs = Date.now();
    let computed = 0;
    if (store.lastSnapshotMs) {
      computed = Math.max(0, (nowMs - store.lastSnapshotMs) / 1000);
    }
    const healthAge = store.health && typeof store.health.data_age_s === 'number'
      ? Number(store.health.data_age_s)
      : 0;
    store.staleSeconds = Math.max(computed, healthAge || 0);
    renderBanner();
  }

  function renderBanner() {
    const { badgeIbkr, badgeStale, staleValue } = els;
    const connected = store.health && store.health.ibkr_connected !== null
      ? Boolean(store.health.ibkr_connected)
      : null;
    if (connected === false) {
      badgeIbkr.classList.remove('hidden');
    } else {
      badgeIbkr.classList.add('hidden');
    }

    if (!store.lastSnapshotMs) {
      badgeStale.classList.add('hidden');
      return;
    }

    const secs = Math.max(0, Number(store.staleSeconds || 0));
    staleValue.textContent = Math.round(secs).toString();
    badgeStale.classList.remove('hidden');
    badgeStale.classList.remove('warn', 'alert');

    if (secs > 60) {
      badgeStale.classList.add('alert');
    } else if (secs > 15) {
      badgeStale.classList.add('warn');
    }
  }

  function renderSummary() {
    const risk = store.risk || {};
    const totalPositions = store.positions.length;
    const { updated, positions, notional, beta, var: varEl, margin } = els.metrics;
    updated.textContent = formatTime(store.lastSnapshotMs);
    positions.textContent = Number.isFinite(totalPositions)
      ? totalPositions.toLocaleString()
      : '—';
    notional.textContent = formatCurrency(risk.notional);
    beta.textContent = formatNumber(risk.beta, 2);
    varEl.textContent = formatCurrency(risk.var95_1d);
    margin.textContent = formatPercent(risk.margin_pct);
  }

  function renderBreaches() {
    const { breachList } = els;
    if (!store.breaches || store.breaches.length === 0) {
      breachList.classList.add('empty');
      breachList.innerHTML = 'No active breaches';
      return;
    }

    breachList.classList.remove('empty');
    breachList.innerHTML = store.breaches
      .map((breach) => '<span class="badge alert">' + escapeHtml(breach) + '</span>')
      .join('');
  }

  function renderPositions() {
    const total = store.positions.length;
    const limit = 30;
    if (!total) {
      els.positionsInfo.textContent = 'No positions available';
      els.positionsBody.innerHTML = '<tr><td colspan="6" class="empty muted">No positions</td></tr>';
      return;
    }

    els.positionsInfo.textContent = 'Showing ' + Math.min(limit, total) + ' of ' + total + ' positions';

    const rows = store.positions.slice(0, limit).map((row) => {
      const symbol = pick(row, ['symbol', 'underlying', 'localSymbol', 'ticker']) || '—';
      const qty = pick(row, ['qty', 'position', 'quantity']);
      const mark = pick(row, ['mark', 'price', 'marketPrice', 'lastPrice']);
      const delta = pick(row, ['delta', 'delta_exposure', 'deltaExposure']);
      const gamma = pick(row, ['gamma', 'gamma_exposure', 'gammaExposure']);
      const theta = pick(row, ['theta', 'theta_exposure', 'thetaExposure']);

      return '<tr>'
        + '<td>' + escapeHtml(symbol) + '</td>'
        + '<td class="num">' + formatNumber(qty, 2) + '</td>'
        + '<td class="num">' + formatNumber(mark, 2) + '</td>'
        + '<td class="num">' + formatNumber(delta, 2) + '</td>'
        + '<td class="num">' + formatNumber(gamma, 4) + '</td>'
        + '<td class="num">' + formatNumber(theta, 2) + '</td>'
        + '</tr>';
    }).join('');

    els.positionsBody.innerHTML = rows;
  }

  function render() {
    renderBanner();
    renderSummary();
    renderBreaches();
    renderPositions();
  }

  loadInitial().finally(() => {
    startSse();
    setInterval(updateStaleTicker, 1000);
    render();
  });
})();
</script>
</body>
</html>
"""

_clients: set[Any] = set()


def _html_page() -> str:
    return _HTML_PAGE


def make_app():
    """Create and return the FastAPI application powering the PSD dashboard."""
    from fastapi import WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse

    from psd.web.app import app as api_app

    app = api_app

    if getattr(app.state, "psd_dashboard_registered", False):
        return app

    @app.get("/", include_in_schema=False)
    async def index() -> HTMLResponse:  # type: ignore[override]
        return HTMLResponse(content=_html_page())

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:  # type: ignore[override]
        await ws.accept()
        _clients.add(ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            try:
                _clients.discard(ws)
                await ws.close()
            except Exception:
                pass

    @app.websocket("/ws/")
    async def ws_endpoint_slash(ws: WebSocket) -> None:  # type: ignore[override]
        await ws_endpoint(ws)

    app.state.psd_dashboard_registered = True
    return app


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
    """Start the PSD dashboard server via uvicorn."""
    try:
        import uvicorn  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("uvicorn is required to start the web server") from exc

    actual_port = int(port) if int(port) != 0 else pick_free_port(host)
    app = make_app()

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
            except Exception as err:
                last_err = err
                try:
                    print(f"[psd-web] ws backend {ws_value or 'auto'} failed: {err}")
                except Exception:
                    pass
                continue
        if last_err is not None:
            raise last_err

    if not background:
        _serve_with_fallbacks()
        return host, actual_port

    import threading

    thread = threading.Thread(target=_serve_with_fallbacks, name="psd-web", daemon=True)
    thread.start()
    return host, actual_port


def broadcast(dto: dict) -> None:
    """Best-effort broadcast to connected WebSocket clients."""
    payload = json.dumps(dto, separators=(",", ":"))
    if not _clients:
        return

    async def _send_all() -> None:
        living: set[Any] = set()
        for ws in list(_clients):
            try:
                await ws.send_text(payload)
                living.add(ws)
            except Exception:
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
