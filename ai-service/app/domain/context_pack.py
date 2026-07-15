"""Provider-neutral contract for bounded, reviewable developer context packs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal


ContextPackVersion = Literal["context-pack-v1"]
ContextPackItemType = Literal["memo", "insight"]
ContextPackSourceType = Literal["memo", "insight"]


class ContextPackValidationError(ValueError):
    """Raised when an explicit pack selection violates its contract."""


@dataclass(frozen=True)
class ContextPackRequest:
    question: str
    memo_ids: tuple[str, ...] = ()
    insight_ids: tuple[str, ...] = ()
    max_chars: int = 6000
    max_items: int = 20

    def __post_init__(self) -> None:
        if not self.question.strip():
            raise ContextPackValidationError("question must not be empty")
        if self.max_chars < 64:
            raise ContextPackValidationError("max_chars must be at least 64")
        if self.max_chars > 20000:
            raise ContextPackValidationError("max_chars must be at most 20000")
        if self.max_items < 1:
            raise ContextPackValidationError("max_items must be at least 1")
        if self.max_items > 50:
            raise ContextPackValidationError("max_items must be at most 50")


@dataclass(frozen=True)
class ContextPackMemo:
    memo_id: str
    title: str
    summary: str = ""

    def __post_init__(self) -> None:
        if not self.memo_id.strip():
            raise ContextPackValidationError("memo_id must not be empty")
        if not self.title.strip():
            raise ContextPackValidationError("memo title must not be empty")


@dataclass(frozen=True)
class ContextPackItem:
    item_id: str
    item_type: ContextPackItemType
    memo_id: str
    insight_id: str | None
    title: str
    summary: str
    confidence: float | None
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class ContextPackSource:
    source_id: str
    source_type: ContextPackSourceType
    memo_id: str
    insight_id: str | None
    title: str
    source_refs: tuple[str, ...]


@dataclass(frozen=True)
class ContextPackResponse:
    pack_version: ContextPackVersion
    question: str
    markdown: str
    items: tuple[ContextPackItem, ...]
    sources: tuple[ContextPackSource, ...]
    truncated: bool
    truncation_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "pack_version": self.pack_version,
            "question": self.question,
            "markdown": self.markdown,
            "items": [
                {
                    "item_id": item.item_id,
                    "item_type": item.item_type,
                    "memo_id": item.memo_id,
                    "insight_id": item.insight_id,
                    "title": item.title,
                    "summary": item.summary,
                    "confidence": item.confidence,
                    "source_ids": list(item.source_ids),
                }
                for item in self.items
            ],
            "sources": [
                {
                    "source_id": source.source_id,
                    "source_type": source.source_type,
                    "memo_id": source.memo_id,
                    "insight_id": source.insight_id,
                    "title": source.title,
                    "source_refs": list(source.source_refs),
                }
                for source in self.sources
            ],
            "truncated": self.truncated,
            "truncation_reason": self.truncation_reason,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)
