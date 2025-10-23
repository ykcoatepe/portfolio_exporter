"""Optional Pandera schemas for CSV preflight checks."""

from __future__ import annotations

import pandas as pd

try:  # optional pandera dependency
    import pandera as pa
except Exception:  # pragma: no cover - optional
    pa = None  # type: ignore


if pa:  # pragma: no branch

    class PositionsSchema(pa.DataFrameModel):
        underlying: pa.typing.Series[str]
        right: pa.typing.Series[str]
        strike: pa.typing.Series[float]
        expiry: pa.typing.Series[str]
        qty: pa.typing.Series[float]

    class TotalsSchema(pa.DataFrameModel):
        account: pa.typing.Series[str]
        net_liq: pa.typing.Series[float]

    class CombosSchema(pa.DataFrameModel):
        underlying: pa.typing.Series[str]
        expiry: pa.typing.Series[str]
        structure_label: pa.typing.Series[str]
        type: pa.typing.Series[str]

    class TradesSchema(pa.DataFrameModel):
        ticker: pa.typing.Series[str]
        side: pa.typing.Series[str]
        qty: pa.typing.Series[float]
        price: pa.typing.Series[float]

    SCHEMAS = {
        "positions": PositionsSchema.to_schema(),
        "totals": TotalsSchema.to_schema(),
        "combos": CombosSchema.to_schema(),
        "trades": TradesSchema.to_schema(),
    }

    def check_headers(name: str, df: pd.DataFrame) -> list[str]:
        schema = SCHEMAS.get(name)
        if schema is None:
            return []
        missing = set(schema.columns.keys()) - set(df.columns)
        if missing:
            return [f"missing columns {sorted(missing)}"]
        return []

else:  # pandera not installed

    def check_headers(name: str, df: pd.DataFrame) -> list[str]:  # type: ignore[override]
        return ["pandera not installed"]
