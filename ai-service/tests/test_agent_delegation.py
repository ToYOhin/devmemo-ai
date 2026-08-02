import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.agent_delegation import (
    INTERNAL_ANSWER_PATH,
    AgentDelegationError,
    AgentDelegationHeaders,
    DelegatedAnswerRequest,
    sign_delegated_request,
    verify_delegated_request,
)


def _fixture() -> dict[str, str]:
    path = Path(__file__).parents[2] / "contracts" / "evidence-answer-agent-internal-v1.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_delegation_signature_matches_the_cross_language_contract_fixture():
    fixture = _fixture()
    body = fixture["raw_body"].encode("utf-8")
    timestamp = int(fixture["timestamp"])

    headers = sign_delegated_request(
        fixture["method"], fixture["path"], body, timestamp, fixture["secret"]
    )
    request = verify_delegated_request(
        fixture["method"],
        fixture["path"],
        body,
        headers,
        fixture["secret"],
        datetime.fromtimestamp(timestamp + 30, timezone.utc),
    )

    assert headers.signature == fixture["signature"]
    assert request == DelegatedAnswerRequest(
        question="Docker port mapping",
        limit=3,
        visible_memo_uids=("memo-a", "memo-b"),
    )


@pytest.mark.parametrize(
    ("method", "path", "body", "now_offset"),
    [
        ("GET", INTERNAL_ANSWER_PATH, b'{"question":"Docker port mapping","limit":3,"visible_memo_uids":["memo-a","memo-b"]}', 0),
        ("POST", "/other", b'{"question":"Docker port mapping","limit":3,"visible_memo_uids":["memo-a","memo-b"]}', 0),
        ("POST", INTERNAL_ANSWER_PATH, b'{"question":"Docker port mapping","limit":3,"visible_memo_uids":["memo-a","memo-b"]} ', 0),
        ("POST", INTERNAL_ANSWER_PATH, b'{"question":"Docker port mapping","limit":3,"visible_memo_uids":["memo-a","memo-b"]}', 61),
    ],
)
def test_delegation_rejects_tampering_and_expiry(method, path, body, now_offset):
    fixture = _fixture()
    timestamp = int(fixture["timestamp"])
    headers = AgentDelegationHeaders(fixture["signature"], fixture["timestamp"])

    with pytest.raises(AgentDelegationError, match="invalid Agent delegation"):
        verify_delegated_request(
            method,
            path,
            body,
            headers,
            fixture["secret"],
            datetime.fromtimestamp(timestamp + now_offset, timezone.utc),
        )


@pytest.mark.parametrize(
    "body",
    [
        b'{"question":"Docker","limit":3,"visible_memo_uids":["memo-a"],"content":"forbidden"}',
        b'{"question":"Docker","limit":3,"visible_memo_uids":["memo-a","memo-a"]}',
        b'{"question":"Docker","limit":true,"visible_memo_uids":["memo-a"]}',
    ],
)
def test_delegation_rejects_unexpected_or_invalid_scope_fields(body):
    fixture = _fixture()
    timestamp = int(fixture["timestamp"])
    headers = sign_delegated_request("POST", INTERNAL_ANSWER_PATH, body, timestamp, fixture["secret"])

    with pytest.raises(AgentDelegationError, match="invalid Agent delegation"):
        verify_delegated_request(
            "POST",
            INTERNAL_ANSWER_PATH,
            body,
            headers,
            fixture["secret"],
            datetime.fromtimestamp(timestamp, timezone.utc),
        )


def test_delegation_accepts_only_an_opaque_memos_authority_reference():
    fixture = _fixture()
    timestamp = int(fixture["timestamp"])
    body = (
        b'{"question":"Docker","limit":3,"visible_memo_uids":["memo-a"],'
        b'"memos_authority_ref":"authority-ref-synthetic-0000000001"}'
    )
    headers = sign_delegated_request(
        "POST", INTERNAL_ANSWER_PATH, body, timestamp, fixture["secret"]
    )

    parsed = verify_delegated_request(
        "POST",
        INTERNAL_ANSWER_PATH,
        body,
        headers,
        fixture["secret"],
        datetime.fromtimestamp(timestamp, timezone.utc),
    )

    assert parsed.memos_authority_ref == "authority-ref-synthetic-0000000001"

    invalid_body = body.replace(
        b"authority-ref-synthetic-0000000001", b"caller-controlled"
    )
    invalid_headers = sign_delegated_request(
        "POST", INTERNAL_ANSWER_PATH, invalid_body, timestamp, fixture["secret"]
    )
    with pytest.raises(AgentDelegationError, match="invalid Agent delegation"):
        verify_delegated_request(
            "POST",
            INTERNAL_ANSWER_PATH,
            invalid_body,
            invalid_headers,
            fixture["secret"],
            datetime.fromtimestamp(timestamp, timezone.utc),
        )
