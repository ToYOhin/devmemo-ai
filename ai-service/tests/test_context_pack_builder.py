import json
from dataclasses import replace

import pytest

from app.domain.context_pack import ContextPackRequest, ContextPackValidationError
from app.services.context_pack import build_context_pack
from tests.context_pack_fixture import context_pack_inputs


def test_empty_explicit_selection_returns_empty_pack():
    memos, insights = context_pack_inputs()

    response = build_context_pack(
        ContextPackRequest(question="What should I know?"), memos, insights
    )

    assert response.items == ()
    assert response.sources == ()
    assert response.truncated is False
    assert "What should I know?" in response.markdown


def test_unknown_ids_and_implicit_memo_expansion_are_rejected():
    memos, insights = context_pack_inputs()

    with pytest.raises(ContextPackValidationError, match="unknown memo id"):
        build_context_pack(ContextPackRequest("question", memo_ids=("missing",)), memos, insights)
    with pytest.raises(ContextPackValidationError, match="unknown insight id"):
        build_context_pack(
            ContextPackRequest("question", memo_ids=("memo-bug",), insight_ids=("missing",)),
            memos,
            insights,
        )
    with pytest.raises(ContextPackValidationError, match="must be explicitly selected"):
        build_context_pack(
            ContextPackRequest("question", insight_ids=("insight-bug",)), memos, insights
        )


@pytest.mark.parametrize("status", ["pending", "rejected"])
def test_pending_or_rejected_insight_cannot_enter_pack(status):
    memos, insights = context_pack_inputs()
    insights["insight-pending"] = replace(insights["insight-pending"], status=status)
    request = ContextPackRequest(
        "question", memo_ids=("memo-bug",), insight_ids=("insight-pending",)
    )

    with pytest.raises(ContextPackValidationError, match="accepted"):
        build_context_pack(request, memos, insights)


def test_same_memo_and_insight_ids_are_deduplicated_and_traceable():
    memos, insights = context_pack_inputs()

    response = build_context_pack(
        ContextPackRequest(
            "How do I prevent the failure?",
            memo_ids=("memo-bug", "memo-bug"),
            insight_ids=("insight-bug", "insight-bug"),
        ),
        memos,
        insights,
    )

    assert [source.source_id for source in response.sources] == [
        "memo:memo-bug",
        "insight-bug",
    ]
    assert response.sources[1].source_refs == ("template.root_cause",)
    assert all(item.memo_id == "memo-bug" for item in response.items)


def test_insights_are_sorted_by_confidence_then_updated_at_then_stable_id():
    memos, insights = context_pack_inputs()

    response = build_context_pack(
        ContextPackRequest(
            "Summarize the confirmed decisions",
            memo_ids=("memo-bug", "memo-code"),
            insight_ids=("insight-action", "insight-bug"),
        ),
        memos,
        insights,
    )

    assert [item.item_id for item in response.items] == [
        "memo:memo-bug",
        "memo:memo-code",
        "insight-bug",
        "insight-action",
    ]


def test_budget_is_explicitly_truncated_without_partial_item():
    memos, insights = context_pack_inputs()

    response = build_context_pack(
        ContextPackRequest(
            "What happened?",
            memo_ids=("memo-bug", "memo-code"),
            insight_ids=("insight-bug", "insight-action"),
            max_items=2,
            max_chars=500,
        ),
        memos,
        insights,
    )

    assert len(response.items) <= 2
    assert len(response.markdown) <= 500
    assert response.truncated is True
    assert response.truncation_reason == "max_items"
    assert "insight-action" not in response.markdown


def test_markdown_and_json_share_the_same_sources_and_items():
    memos, insights = context_pack_inputs()

    response = build_context_pack(
        ContextPackRequest(
            "Give me the verified port context",
            memo_ids=("memo-bug",),
            insight_ids=("insight-bug",),
        ),
        memos,
        insights,
    )
    payload = json.loads(response.to_json())

    assert payload["pack_version"] == "context-pack-v1"
    assert [item["item_id"] for item in payload["items"]] == [
        item.item_id for item in response.items
    ]
    assert [source["source_id"] for source in payload["sources"]] == [
        source.source_id for source in response.sources
    ]
    assert all(item.item_id in response.markdown for item in response.items)
    assert "content" not in response.to_json()
