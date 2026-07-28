"""Pure builder for bounded, explicitly selected developer context packs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from app.domain.context_pack import (
    ContextPackItem,
    ContextPackMemo,
    ContextPackRequest,
    ContextPackResponse,
    ContextPackSource,
    ContextPackValidationError,
)
from app.domain.memo_insight import MemoInsight


@dataclass(frozen=True)
class _PackCandidate:
    item: ContextPackItem
    sources: tuple[ContextPackSource, ...]
    markdown: str


def build_context_pack(
    request: ContextPackRequest,
    memos: Mapping[str, ContextPackMemo],
    insights: Mapping[str, MemoInsight],
) -> ContextPackResponse:
    """Build a deterministic pack from only the explicitly selected inputs."""

    memo_ids = _unique_ids(request.memo_ids, "memo")
    insight_ids = _unique_ids(request.insight_ids, "insight")
    if insight_ids and not memo_ids:
        raise ContextPackValidationError(
            "insight IDs must be explicitly selected with their memo IDs"
        )

    _require_known_ids(memo_ids, memos, "memo")
    _require_known_ids(insight_ids, insights, "insight")

    selected_memo_ids = set(memo_ids)
    selected_insights: list[MemoInsight] = []
    for insight_id in insight_ids:
        insight = insights[insight_id]
        if insight.status != "accepted":
            raise ContextPackValidationError(
                f"insight {insight_id} must be accepted before it enters a context pack"
            )
        if insight.memo_id not in selected_memo_ids:
            raise ContextPackValidationError(
                f"insight {insight_id} memo must be explicitly selected"
            )
        selected_insights.append(insight)

    selected_insights.sort(key=lambda item: item.insight_id)
    selected_insights.sort(key=lambda item: item.updated_at, reverse=True)
    selected_insights.sort(key=lambda item: item.confidence, reverse=True)

    memo_candidates = [
        _memo_candidate(memos[memo_id]) for memo_id in sorted(memo_ids)
    ]
    insight_candidates = [
        _insight_candidate(insight, memos[insight.memo_id]) for insight in selected_insights
    ]
    candidates = memo_candidates + insight_candidates

    markdown = _pack_header(request.question, request.max_chars)
    selected_items: list[ContextPackItem] = []
    selected_sources: list[ContextPackSource] = []
    source_ids: set[str] = set()
    truncation_reasons: set[str] = set()

    for candidate in candidates:
        if len(selected_items) >= request.max_items:
            truncation_reasons.add("max_items")
            break
        if len(markdown) + len(candidate.markdown) > request.max_chars:
            truncation_reasons.add("max_chars")
            break
        markdown += candidate.markdown
        selected_items.append(candidate.item)
        for source in candidate.sources:
            if source.source_id not in source_ids:
                source_ids.add(source.source_id)
                selected_sources.append(source)

    reason = ",".join(sorted(truncation_reasons)) or None
    return ContextPackResponse(
        pack_version="context-pack-v1",
        question=request.question.strip(),
        markdown=markdown,
        items=tuple(selected_items),
        sources=tuple(selected_sources),
        truncated=reason is not None,
        truncation_reason=reason,
    )


def _unique_ids(ids: tuple[str, ...], label: str) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for raw_id in ids:
        value = str(raw_id).strip()
        if not value:
            raise ContextPackValidationError(f"{label} ID must not be empty")
        if value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


def _require_known_ids(ids: tuple[str, ...], records: Mapping[str, object], label: str) -> None:
    for record_id in ids:
        if record_id not in records:
            raise ContextPackValidationError(f"unknown {label} id: {record_id}")


def _memo_candidate(memo: ContextPackMemo) -> _PackCandidate:
    source_id = f"memo:{memo.memo_id}"
    title = _safe_text(memo.title)
    summary = _safe_text(memo.summary) or "No memo summary was provided."
    source = ContextPackSource(
        source_id=source_id,
        source_type="memo",
        memo_id=memo.memo_id,
        insight_id=None,
        title=title,
        source_refs=(),
    )
    item = ContextPackItem(
        item_id=source_id,
        item_type="memo",
        memo_id=memo.memo_id,
        insight_id=None,
        title=title,
        summary=summary,
        confidence=None,
        source_ids=(source_id,),
    )
    return _PackCandidate(
        item=item,
        sources=(source,),
        markdown=(
            f"## Memo `{source_id}` — {title}\n"
            f"Summary: {summary}\n\n"
        ),
    )


def _insight_candidate(insight: MemoInsight, memo: ContextPackMemo) -> _PackCandidate:
    memo_source_id = f"memo:{memo.memo_id}"
    title = _safe_text(insight.title)
    summary = _safe_text(insight.summary) or "No insight summary was provided."
    source_refs = _safe_refs(insight.source_refs)
    insight_source = ContextPackSource(
        source_id=insight.insight_id,
        source_type="insight",
        memo_id=insight.memo_id,
        insight_id=insight.insight_id,
        title=title,
        source_refs=source_refs,
    )
    item = ContextPackItem(
        item_id=insight.insight_id,
        item_type="insight",
        memo_id=insight.memo_id,
        insight_id=insight.insight_id,
        title=title,
        summary=summary,
        confidence=insight.confidence,
        source_ids=(memo_source_id, insight.insight_id),
    )
    refs = ", ".join(f"`{ref}`" for ref in source_refs) or "none"
    return _PackCandidate(
        item=item,
        sources=(insight_source,),
        markdown=(
            f"## Insight `{insight.insight_id}` — {title}\n"
            f"- Memo: `{insight.memo_id}` — {_safe_text(memo.title)}\n"
            f"- Type: {insight.insight_type}\n"
            f"- Confidence: {insight.confidence:.2f}\n"
            f"- Summary: {summary}\n"
            f"- Source refs: {refs}\n\n"
        ),
    )


def _pack_header(question: str, max_chars: int) -> str:
    prefix = "# DevMemory Context Pack\n\nQuestion: "
    suffix = "\n\n"
    available = max_chars - len(prefix) - len(suffix)
    if available <= 0:
        return (prefix + suffix)[:max_chars]
    bounded_question = _safe_text(question, available)
    return f"{prefix}{bounded_question}{suffix}"


def _safe_refs(refs: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        value = _safe_text(ref, 160).replace("`", "'")
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


def _safe_text(value: str, limit: int = 800) -> str:
    normalized = " ".join(str(value).split()).replace("`", "'")
    return normalized[:limit].rstrip()
