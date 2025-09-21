from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from collections.abc import Callable
from typing import Any

from ib_insync import IB

log = logging.getLogger(__name__)

_ASYNC_SUPPORT: dict[str, bool] = {}
_connect_lock = asyncio.Lock()
_connecting: asyncio.Task[IB] | None = None
_ib_singleton: IB | None = None


def _supports_async(method: str) -> bool:
    return _ASYNC_SUPPORT.get(method, True)


def _mark_sync(method: str) -> None:
    _ASYNC_SUPPORT[method] = False


def _clear_connecting(task: asyncio.Task[Any]) -> None:
    global _connecting
    if _connecting is task:
        _connecting = None


async def _to_thread(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Always offload blocking ib_insync sync methods from the event loop."""

    policy = asyncio.get_event_loop_policy()

    def runner() -> Any:
        loop = policy.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return fn(*args, **kwargs)
        finally:
            asyncio.set_event_loop(None)
            loop.close()

    return await asyncio.to_thread(runner)


async def connect(host: str, port: int, client_id: int, timeout: float | None = None) -> IB:
    """Return a connected IB instance; serialize concurrent connects and respect timeout."""

    global _connecting, _ib_singleton

    if _ib_singleton and _ib_singleton.isConnected():
        return _ib_singleton

    env_timeout = os.getenv("PSD_IB_CONNECT_TIMEOUT", "7")
    try:
        default_timeout = float(env_timeout)
    except ValueError:
        default_timeout = 7.0
    timeout_value = timeout if timeout is not None else default_timeout

    async with _connect_lock:
        if _ib_singleton and _ib_singleton.isConnected():
            return _ib_singleton

        if _connecting and not _connecting.done():
            task = _connecting
        else:
            if _connecting and _connecting.done():
                _connecting = None
            ib = IB()

            async def _do_connect() -> IB:
                try:
                    try:
                        await ib.connectAsync(host, port, clientId=client_id, timeout=timeout_value)
                    except (RuntimeError, NotImplementedError) as exc:
                        log.debug("connectAsync not available here (%s), falling back to sync connect", exc)
                        _mark_sync("connect")
                        await _to_thread(ib.connect, host, port, clientId=client_id, timeout=timeout_value)
                    return ib
                except Exception:
                    with contextlib.suppress(Exception):
                        ib.disconnect()
                    raise

            task = asyncio.create_task(_do_connect())
            _connecting = task
            task.add_done_callback(_clear_connecting)

    ib_instance = await task
    _ib_singleton = ib_instance
    return ib_instance


async def req_positions(ib: IB) -> Any:
    method = "reqPositions"
    if _supports_async(method):
        async_fn = getattr(ib, "reqPositionsAsync", None)
        if async_fn is not None:
            try:
                result = await async_fn()
                _ASYNC_SUPPORT[method] = True
                return result
            except (RuntimeError, NotImplementedError) as exc:
                log.debug("reqPositionsAsync unsupported (%s) → sync fallback", exc)
                _mark_sync(method)
        else:
            _mark_sync(method)
    sync_fn = getattr(ib, "reqPositions", None)
    if sync_fn is None:
        raise AttributeError("IB instance missing reqPositions")
    return await _to_thread(sync_fn)


async def qualify_contracts(ib: IB, *contracts: Any) -> Any:
    method = "qualifyContracts"
    if _supports_async(method):
        async_fn = getattr(ib, "qualifyContractsAsync", None)
        if async_fn is not None:
            try:
                result = await async_fn(*contracts)
                _ASYNC_SUPPORT[method] = True
                return result
            except (RuntimeError, NotImplementedError) as exc:
                log.debug("qualifyContractsAsync unsupported (%s) → sync fallback", exc)
                _mark_sync(method)
        else:
            _mark_sync(method)
    sync_fn = getattr(ib, "qualifyContracts", None)
    if sync_fn is None:
        raise AttributeError("IB instance missing qualifyContracts")
    return await _to_thread(sync_fn, *contracts)


async def req_mkt_data(
    ib: IB,
    contract: Any,
    genericTickList: str = "",
    snapshot: bool = False,
    **kwargs: Any,
) -> Any:
    method = "reqMktData"
    if _supports_async(method):
        async_fn = getattr(ib, "reqMktDataAsync", None)
        if async_fn is not None:
            try:
                result = await async_fn(contract, genericTickList, snapshot, **kwargs)
                _ASYNC_SUPPORT[method] = True
                return result
            except (RuntimeError, NotImplementedError) as exc:
                log.debug("reqMktDataAsync unsupported (%s) → sync fallback", exc)
                _mark_sync(method)
        else:
            _mark_sync(method)
    sync_fn = getattr(ib, "reqMktData", None)
    if sync_fn is None:
        raise AttributeError("IB instance missing reqMktData")
    return await _to_thread(sync_fn, contract, genericTickList, snapshot, **kwargs)


async def req_contract_details(ib: IB, contract: Any) -> Any:
    method = "reqContractDetails"
    if _supports_async(method):
        async_fn = getattr(ib, "reqContractDetailsAsync", None)
        if async_fn is not None:
            try:
                result = await async_fn(contract)
                _ASYNC_SUPPORT[method] = True
                return result
            except (RuntimeError, NotImplementedError) as exc:
                log.debug("reqContractDetailsAsync unsupported (%s) → sync fallback", exc)
                _mark_sync(method)
        else:
            _mark_sync(method)
    sync_fn = getattr(ib, "reqContractDetails", None)
    if sync_fn is None:
        raise AttributeError("IB instance missing reqContractDetails")
    return await _to_thread(sync_fn, contract)


async def disconnect() -> None:
    """Disconnect and reset cached IB state."""

    global _ib_singleton, _connecting

    async with _connect_lock:
        if _ib_singleton is not None:
            with contextlib.suppress(Exception):
                _ib_singleton.disconnect()
        _ib_singleton = None
        _connecting = None
        _ASYNC_SUPPORT.clear()
