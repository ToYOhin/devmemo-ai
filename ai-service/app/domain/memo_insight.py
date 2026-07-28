"""Provider-neutral contract for reviewable developer-memory insights."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


InsightType = Literal["fact", "decision", "action", "bug"]
InsightStatus = Literal["pending", "accepted", "rejected"]


@dataclass(frozen=True)
class MemoInsight:
    insight_id: str
    memo_id: str
    insight_type: InsightType
    title: str
    summary: str
    confidence: float
    status: InsightStatus
    source_refs: tuple[str, ...]
    version: int
    created_at: str
    updated_at: str
