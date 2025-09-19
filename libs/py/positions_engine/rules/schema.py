# SPDX-License-Identifier: MIT

"""Pydantic schema definitions for portfolio rules evaluation."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


Severity = Literal["INFO", "WARNING", "CRITICAL"]
Scope = Literal["PORT", "UL", "COMBO", "LEG"]
BreachStatus = Literal["OPEN", "ACKNOWLEDGED", "RESOLVED"]


class Rule(BaseModel):
    rule_id: str
    name: str
    severity: Severity
    scope: Scope
    filter: str
    expr: str
    enabled: bool = True

    model_config = ConfigDict(extra="forbid")


class Breach(BaseModel):
    breach_id: str
    rule_id: str
    scope: Scope
    subject_id: str
    symbol: str | None = None
    triggered_at: datetime
    value: float | None = None
    status: BreachStatus = "OPEN"
    notes: str | None = None

    model_config = ConfigDict(extra="forbid")
