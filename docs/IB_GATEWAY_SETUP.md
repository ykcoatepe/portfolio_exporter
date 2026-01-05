# IB Gateway Setup Guide

This guide describes a stable, low-friction way to run IB Gateway for
`portfolio_exporter`. It is intentionally evergreen: replace placeholders
(e.g., `<IBC_VERSION>`) with the current version you install.

## Why Gateway

IB Gateway is lighter than TWS and well-suited for unattended scripts.
The default live port is 4001 (paper 4002). If `IB_PORT` is unset,
scripts try Gateway (4001) and fall back to TWS (7496).

## Install (manual)

1) Install IB Gateway from Interactive Brokers.
2) Optional but recommended: install IBC (Interactive Brokers Controller)
   to auto-login and auto-restart.
   - Example IBC version placeholder: `<IBC_VERSION>`

## Configure the API in Gateway

Open IB Gateway and set:
- **Enable ActiveX and Socket Clients** (must be on)
- **Read-Only API**: off (if you need trading), on (if you only read)
- **Socket Port**:
  - Live: `4001`
  - Paper: `4002`
- **Trusted IPs**: allow `127.0.0.1` if local

## Environment Variables

Recommended defaults (live):
- `IB_HOST=127.0.0.1`
- Leave `IB_PORT` **unset** to auto-try Gateway (4001) then TWS (7496)

For paper trading, set one explicitly:
- `IB_PORT=4002` (Gateway paper)
- `IB_PORT=7497` (TWS paper)

## Running with IBC (optional)

IBC can launch and keep Gateway alive. Typical files:
- `GatewayStart.sh` / `GatewayStart.bat`
- `ibc.ini` (or `config.ini`) with your credentials

Example (pseudocode):
```
./GatewayStart.sh -g --ibc-path /path/to/IBC/<IBC_VERSION>
```

## Daily Restart Note

IB Gateway (and TWS) often require a daily restart. Plan a scheduled
restart outside market hours (or use IBC to auto-restart).
If you see intermittent disconnects, a clean restart usually fixes it.

## Troubleshooting

- **Connection refused**: confirm Gateway is running and API is enabled.
- **Stuck on login**: verify credentials / MFA steps (IBC helps here).
- **Wrong port**: ensure Gateway uses 4001/4002 and TWS uses 7496/7497.
- **No data**: check market data subscriptions and account permissions.
- **Multiple clients**: use unique `IB_CLIENT_ID` per script/process.

## Fallback Behavior

- If `IB_PORT` is **unset**: try Gateway 4001 -> fallback TWS 7496.
- If `IB_PORT` is **set**: only that port is used (no fallback).
