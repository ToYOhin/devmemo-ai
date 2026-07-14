"""Deterministic extraction of reviewable insights from one Memo."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from app.domain.memo_insight import MemoInsight
from app.services.content_parser import parse_memo_content


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def insight_id_for(memo_id: str, insight_type: str) -> str:
    digest = hashlib.sha256(f"{memo_id}:{insight_type}".encode("utf-8")).hexdigest()[:20]
    return f"insight-{digest}"


def _first_sentence(content: str) -> str:
    line = next((line.strip() for line in content.splitlines() if line.strip()), "")
    return line.split(".", 1)[0].strip()[:240]


def _build(
    memo_id: str,
    insight_type: str,
    title: str,
    summary: str,
    confidence: float,
    source_refs: tuple[str, ...],
) -> MemoInsight:
    now = _now()
    return MemoInsight(
        insight_id=insight_id_for(memo_id, insight_type),
        memo_id=memo_id,
        insight_type=insight_type,  # type: ignore[arg-type]
        title=title[:160],
        summary=summary[:500],
        confidence=max(0.0, min(1.0, confidence)),
        status="pending",
        source_refs=source_refs,
        version=1,
        created_at=now,
        updated_at=now,
    )


def derive_memo_insights(
    memo_id: str,
    title: str,
    content: str,
    summary: str = "",
) -> tuple[MemoInsight, ...]:
    """Derive bounded candidates without an LLM call or external network."""

    parsed = parse_memo_content(content)
    if parsed.kind == "code" and parsed.template is not None:
        template = parsed.template
        insights: list[MemoInsight] = [
            _build(
                memo_id,
                "fact",
                f"Code snippet: {template.title}",
                f"{template.language} code snippet with {len(template.code.splitlines())} lines.",
                0.95,
                ("template.title", "template.language", "template.code"),
            )
        ]
        if template.description.strip():
            insights.append(
                _build(
                    memo_id,
                    "action",
                    f"Review: {template.title}",
                    template.description,
                    0.78,
                    ("template.description",),
                )
            )
        return tuple(insights)

    if parsed.kind == "bug" and parsed.template is not None:
        template = parsed.template
        problem = template.root_cause.strip() or template.error.strip() or template.title
        insights = [
            _build(
                memo_id,
                "bug",
                template.title,
                problem,
                0.96,
                ("template.error", "template.root_cause"),
            )
        ]
        if template.solution.strip():
            insights.append(
                _build(
                    memo_id,
                    "action",
                    f"Apply fix: {template.title}",
                    template.solution,
                    0.86,
                    ("template.solution",),
                )
            )
        return tuple(insights)

    candidate = summary.strip()[:500] or _first_sentence(content)
    if not candidate:
        return ()
    fact_title = title.strip()[:160] or "Memo fact"
    return (
        _build(memo_id, "fact", fact_title, candidate, 0.58, ("summary",)),
    )
