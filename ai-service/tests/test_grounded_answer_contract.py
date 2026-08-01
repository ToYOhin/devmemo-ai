import json
from pathlib import Path

import pytest

from app.domain.agent import AgentCitation, EvidenceMetadata
from app.domain.grounded_answer import (
    GROUNDED_ANSWER_VERSION,
    MAX_GROUNDED_ANSWER_CHARS,
    MAX_GROUNDED_CITATIONS,
    GroundedAnswerContractError,
    GroundedAnswerFailure,
    ProviderGroundedAnswer,
    map_grounded_answer_failure,
    parse_provider_grounded_answer,
    validate_grounded_answer,
)


def _citation(memo_id: str = "memo-authorized") -> AgentCitation:
    return AgentCitation(
        memo_id=memo_id,
        embedding_id=f"{memo_id}-vector",
        score=0.91,
        title="Docker ports",
        summary="Authorized complete Memo retrieved as evidence.",
        source_refs=(f"memos/{memo_id}",),
        metadata=EvidenceMetadata(tags=("docker",)),
    )


def test_shared_fixture_round_trips_and_maps_only_server_owned_citations():
    fixture_path = (
        Path(__file__).resolve().parents[2]
        / "contracts"
        / "grounded-answer-result-v1.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    body = json.dumps(fixture["provider_result"], separators=(",", ":")).encode()

    provider_result = parse_provider_grounded_answer(body)
    validated = validate_grounded_answer(
        provider_result, {"evidence-1": _citation()}
    )

    assert fixture["contract_version"] == GROUNDED_ANSWER_VERSION
    assert provider_result.to_dict() == fixture["provider_result"]
    assert validated.answer == fixture["provider_result"]["answer"]
    assert validated.citations == (_citation(),)
    assert set(validated.to_dict()) == {"answer", "citations"}
    assert GroundedAnswerFailure("invalid_grounded_answer").to_dict() == fixture[
        "safe_failure"
    ]


def test_provider_result_normalizes_bounded_answer_and_opaque_references():
    result = ProviderGroundedAnswer(
        answer="  Safe synthesized answer [1].  ",
        citation_refs=(" evidence-1 ",),
    )

    assert result.answer == "Safe synthesized answer [1]."
    assert result.citation_refs == ("evidence-1",)


@pytest.mark.parametrize(
    "payload",
    [
        {"answer": "Answer [1].", "citation_refs": ["evidence-1"]},
        {
            "version": "grounded-answer-result-v2",
            "answer": "Answer [1].",
            "citation_refs": ["evidence-1"],
        },
        {
            "version": GROUNDED_ANSWER_VERSION,
            "answer": "Answer [1].",
            "citation_refs": ["evidence-1"],
            "extra": True,
        },
        {
            "version": GROUNDED_ANSWER_VERSION,
            "answer": 42,
            "citation_refs": ["evidence-1"],
        },
        {
            "version": GROUNDED_ANSWER_VERSION,
            "answer": "Answer [1].",
            "citation_refs": "evidence-1",
        },
        {
            "version": GROUNDED_ANSWER_VERSION,
            "answer": "Answer [1].",
            "citation_refs": [True],
        },
    ],
)
def test_provider_result_rejects_missing_unknown_version_and_type_errors(payload):
    body = json.dumps(payload, separators=(",", ":")).encode()

    with pytest.raises(GroundedAnswerContractError, match="invalid grounded answer"):
        parse_provider_grounded_answer(body)


def test_provider_result_rejects_duplicate_json_fields_and_malformed_json():
    duplicate = (
        b'{"version":"grounded-answer-result-v1",'
        b'"answer":"first","answer":"second",'
        b'"citation_refs":["evidence-1"]}'
    )

    for body in (duplicate, b"{not-json", b"[]", b""):
        with pytest.raises(GroundedAnswerContractError) as error:
            parse_provider_grounded_answer(body)
        assert str(error.value) == "invalid grounded answer"


@pytest.mark.parametrize(
    "citation_refs",
    [
        (),
        ("evidence-1", "evidence-1"),
        ("memo-authorized",),
        ("evidence-1",) * (MAX_GROUNDED_CITATIONS + 1),
    ],
)
def test_provider_result_rejects_empty_duplicate_direct_or_excess_references(
    citation_refs,
):
    with pytest.raises(GroundedAnswerContractError):
        ProviderGroundedAnswer(answer="Answer [1].", citation_refs=citation_refs)


@pytest.mark.parametrize("answer", ["", "   ", "x" * (MAX_GROUNDED_ANSWER_CHARS + 1)])
def test_provider_result_rejects_empty_or_excess_answer(answer: str):
    with pytest.raises(GroundedAnswerContractError):
        ProviderGroundedAnswer(answer=answer, citation_refs=("evidence-1",))


@pytest.mark.parametrize(
    "unsafe_field",
    [
        "document",
        "memo_uid",
        "score",
        "metadata",
        "prompt",
        "context",
        "embedding",
        "identity",
        "visibility",
        "secret",
        "trace",
    ],
)
def test_provider_result_rejects_provider_supplied_content_and_metadata(unsafe_field):
    payload = {
        "version": GROUNDED_ANSWER_VERSION,
        "answer": "Answer [1].",
        "citation_refs": ["evidence-1"],
        unsafe_field: "provider-controlled value",
    }

    with pytest.raises(GroundedAnswerContractError):
        parse_provider_grounded_answer(
            json.dumps(payload, separators=(",", ":")).encode()
        )


def test_validation_rejects_unknown_reference_and_empty_or_invalid_server_mapping():
    result = ProviderGroundedAnswer(
        answer="Answer [1].", citation_refs=("evidence-unknown",)
    )

    with pytest.raises(GroundedAnswerContractError):
        validate_grounded_answer(result, {"evidence-1": _citation()})
    with pytest.raises(GroundedAnswerContractError):
        validate_grounded_answer(result, {})
    with pytest.raises(GroundedAnswerContractError):
        validate_grounded_answer(
            ProviderGroundedAnswer(
                answer="Answer [1].", citation_refs=("evidence-1",)
            ),
            {"evidence-1": {"memo_id": "provider-controlled"}},  # type: ignore[dict-item]
        )


def test_validation_rejects_normalized_raw_context_echo():
    raw_context = "Deployment secret rotates only through the Memos authority."
    result = ProviderGroundedAnswer(
        answer="DEPLOYMENT   SECRET rotates only through the Memos authority. [1]",
        citation_refs=("evidence-1",),
    )

    with pytest.raises(GroundedAnswerContractError):
        validate_grounded_answer(
            result,
            {"evidence-1": _citation()},
            protected_context_fragments=(raw_context,),
        )


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (GroundedAnswerContractError(), "invalid_grounded_answer"),
        (TimeoutError("raw timeout detail"), "provider_timeout"),
        (OSError("raw provider endpoint and secret"), "provider_unavailable"),
    ],
)
def test_failures_map_to_fixed_content_free_codes(error, expected_code):
    failure = map_grounded_answer_failure(error)

    assert failure.to_dict() == {"error_code": expected_code}
    assert str(error) not in repr(failure)
    assert len(expected_code) <= 64


def test_failure_projection_rejects_non_contract_code():
    with pytest.raises(ValueError, match="unsupported grounded answer failure code"):
        GroundedAnswerFailure("raw_upstream_detail")  # type: ignore[arg-type]
