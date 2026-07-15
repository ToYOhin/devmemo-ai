import json

import pytest

from app.domain.context_pack import (
    ContextPackMemo,
    ContextPackRequest,
    ContextPackValidationError,
)


def test_context_pack_request_has_safe_bounded_defaults():
    request = ContextPackRequest(question="Why did the bug happen?")

    assert request.memo_ids == ()
    assert request.insight_ids == ()
    assert request.max_chars == 6000
    assert request.max_items == 20


def test_context_pack_contract_rejects_empty_question_or_budget():
    with pytest.raises(ContextPackValidationError):
        ContextPackRequest(question=" ")
    with pytest.raises(ContextPackValidationError):
        ContextPackRequest(question="question", max_chars=63)
    with pytest.raises(ContextPackValidationError):
        ContextPackRequest(question="question", max_chars=20001)
    with pytest.raises(ContextPackValidationError):
        ContextPackRequest(question="question", max_items=0)
    with pytest.raises(ContextPackValidationError):
        ContextPackRequest(question="question", max_items=51)


def test_context_pack_memo_has_no_raw_content_field_and_requires_title():
    memo = ContextPackMemo(memo_id="memo-1", title="Port mapping", summary="Use 8080.")

    assert memo.summary == "Use 8080."
    assert not hasattr(memo, "content")
    with pytest.raises(ContextPackValidationError):
        ContextPackMemo(memo_id="memo-1", title=" ")


def test_context_pack_json_contract_is_deterministic():
    from app.domain.context_pack import ContextPackResponse

    response = ContextPackResponse(
        pack_version="context-pack-v1",
        question="question",
        markdown="# pack",
        items=(),
        sources=(),
        truncated=False,
        truncation_reason=None,
    )

    assert json.loads(response.to_json()) == response.to_dict()
    assert response.to_json() == response.to_json()
