"""Provider-neutral design contract for Memos-owned evidence rehydration.

This module chooses current, authorized Memos rehydration over persistent AI
content storage.  It defines no HTTP, HMAC, database, vector-store, Provider,
or runtime adapter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Mapping, cast

from app.domain.agent_lifecycle import (
    MAX_DOCUMENT_CHARS,
    MEMO_INDEX_VERSION,
    hash_lifecycle_document,
)
from app.domain.durable_authorized_retrieval import (
    AuthorizedRetrievalQuery,
    DerivedCandidateSnapshot,
    DerivedMemoCandidate,
    DerivedMemoDocument,
    DerivedRetrievalContractError,
    select_eligible_candidates,
)


CONTENT_REHYDRATION_VERSION = "memo-evidence-rehydration-v1"
CONTENT_REHYDRATION_PATH = "/internal/ai/agent/evidence/rehydrate"
CONTENT_REHYDRATION_SIGNATURE_PURPOSE = "devmemo-agent-evidence-rehydration-v1"
MAX_REHYDRATION_ITEMS = 10

_MEMO_UID_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,34}[A-Za-z0-9])?$"
)
_OPAQUE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_SELECTION_REF_PATTERN = re.compile(r"^rehydration-[1-9][0-9]*$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ContentRehydrationContractError(ValueError):
    """Reject unsafe rehydration state without echoing content or identity."""

    def __init__(self) -> None:
        super().__init__("invalid content rehydration state")


@dataclass(frozen=True)
class ContentRehydrationDecision:
    """Executable record of the selected production content boundary."""

    content_source: Literal["memos-current-authority"] = "memos-current-authority"
    ai_content_retention: Literal["request-memory-only"] = "request-memory-only"
    response_mode: Literal["all-or-nothing"] = "all-or-nothing"
    backup_restore_authority: Literal["memos-only"] = "memos-only"
    derived_recovery: Literal["discard-and-rebuild-from-memos"] = (
        "discard-and-rebuild-from-memos"
    )
    runtime_scope: Literal["single-host-authenticated-internal"] = (
        "single-host-authenticated-internal"
    )
    multi_instance_gate: Literal["encrypted-transport-and-shared-replay-required"] = (
        "encrypted-transport-and-shared-replay-required"
    )

    def __post_init__(self) -> None:
        if self.to_dict() != {
            "content_source": "memos-current-authority",
            "ai_content_retention": "request-memory-only",
            "response_mode": "all-or-nothing",
            "backup_restore_authority": "memos-only",
            "derived_recovery": "discard-and-rebuild-from-memos",
            "runtime_scope": "single-host-authenticated-internal",
            "multi_instance_gate": "encrypted-transport-and-shared-replay-required",
        }:
            raise ContentRehydrationContractError

    def to_dict(self) -> dict[str, str]:
        return {
            "content_source": self.content_source,
            "ai_content_retention": self.ai_content_retention,
            "response_mode": self.response_mode,
            "backup_restore_authority": self.backup_restore_authority,
            "derived_recovery": self.derived_recovery,
            "runtime_scope": self.runtime_scope,
            "multi_instance_gate": self.multi_instance_gate,
        }


CONTENT_REHYDRATION_DECISION = ContentRehydrationDecision()


@dataclass(frozen=True)
class ContentRehydrationFailure:
    """The only content-free failure projection permitted by this design."""

    error_code: Literal["authorized_retrieval_unavailable"] = (
        "authorized_retrieval_unavailable"
    )

    def __post_init__(self) -> None:
        if self.error_code != "authorized_retrieval_unavailable":
            raise ContentRehydrationContractError

    def to_dict(self) -> dict[str, str]:
        return {"error_code": self.error_code}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> ContentRehydrationFailure:
        _require_exact_fields(payload, {"error_code"})
        return cls(
            error_code=cast(
                Literal["authorized_retrieval_unavailable"],
                payload["error_code"],
            )
        )


@dataclass(frozen=True)
class ContentRehydrationSelection:
    """One eligible derived candidate requested from current Memos authority."""

    selection_ref: str
    memo_uid: str
    source_sequence: int
    document_hash: str
    index_version: Literal["memo-v1"] = MEMO_INDEX_VERSION

    def __post_init__(self) -> None:
        if not isinstance(
            self.selection_ref, str
        ) or not _SELECTION_REF_PATTERN.fullmatch(self.selection_ref):
            raise ContentRehydrationContractError
        _require_memo_uid(self.memo_uid)
        _require_sequence_hash_version(
            self.source_sequence, self.document_hash, self.index_version
        )

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, object]
    ) -> ContentRehydrationSelection:
        _require_exact_fields(
            payload,
            {
                "selection_ref",
                "memo_uid",
                "source_sequence",
                "document_hash",
                "index_version",
            },
        )
        return cls(
            selection_ref=cast(str, payload["selection_ref"]),
            memo_uid=cast(str, payload["memo_uid"]),
            source_sequence=cast(int, payload["source_sequence"]),
            document_hash=cast(str, payload["document_hash"]),
            index_version=cast(Literal["memo-v1"], payload["index_version"]),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "selection_ref": self.selection_ref,
            "memo_uid": self.memo_uid,
            "source_sequence": self.source_sequence,
            "document_hash": self.document_hash,
            "index_version": self.index_version,
        }


@dataclass(frozen=True)
class ContentRehydrationRequest:
    """Exact bounded request created only after R5 eligibility selection."""

    snapshot_token: str
    memos_authority_ref: str
    selections: tuple[ContentRehydrationSelection, ...]
    version: Literal["memo-evidence-rehydration-v1"] = CONTENT_REHYDRATION_VERSION

    def __post_init__(self) -> None:
        if self.version != CONTENT_REHYDRATION_VERSION:
            raise ContentRehydrationContractError
        _require_opaque_id(self.snapshot_token)
        _require_opaque_id(self.memos_authority_ref)
        if (
            not isinstance(self.selections, tuple)
            or not 1 <= len(self.selections) <= MAX_REHYDRATION_ITEMS
            or any(
                not isinstance(selection, ContentRehydrationSelection)
                for selection in self.selections
            )
        ):
            raise ContentRehydrationContractError
        if len({item.selection_ref for item in self.selections}) != len(
            self.selections
        ) or len({item.memo_uid for item in self.selections}) != len(self.selections):
            raise ContentRehydrationContractError

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> ContentRehydrationRequest:
        _require_exact_fields(
            payload,
            {"version", "snapshot_token", "memos_authority_ref", "selections"},
        )
        raw_selections = payload["selections"]
        if not isinstance(raw_selections, list):
            raise ContentRehydrationContractError
        return cls(
            version=cast(Literal["memo-evidence-rehydration-v1"], payload["version"]),
            snapshot_token=cast(str, payload["snapshot_token"]),
            memos_authority_ref=cast(str, payload["memos_authority_ref"]),
            selections=tuple(
                ContentRehydrationSelection.from_dict(_require_mapping(item))
                for item in raw_selections
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "snapshot_token": self.snapshot_token,
            "memos_authority_ref": self.memos_authority_ref,
            "selections": [selection.to_dict() for selection in self.selections],
        }


@dataclass(frozen=True)
class MemosAuthorizedCurrentDocument:
    """One current document emitted by Memos after visibility/eligibility checks."""

    memo_uid: str
    document: str
    source_sequence: int
    document_hash: str
    index_version: Literal["memo-v1"] = MEMO_INDEX_VERSION

    def __post_init__(self) -> None:
        _require_memo_uid(self.memo_uid)
        _require_document(self.document, self.document_hash)
        _require_sequence_hash_version(
            self.source_sequence, self.document_hash, self.index_version
        )


@dataclass(frozen=True)
class MemosCurrentAuthoritySnapshot:
    """Caller-specific documents from one current, atomic Memos authority read."""

    memos_authority_ref: str
    authority_token: str
    documents: tuple[MemosAuthorizedCurrentDocument, ...]

    def __post_init__(self) -> None:
        _require_opaque_id(self.memos_authority_ref)
        _require_opaque_id(self.authority_token)
        if not isinstance(self.documents, tuple) or any(
            not isinstance(document, MemosAuthorizedCurrentDocument)
            for document in self.documents
        ):
            raise ContentRehydrationContractError
        if len(self.documents) > MAX_REHYDRATION_ITEMS or len(
            {document.memo_uid for document in self.documents}
        ) != len(self.documents):
            raise ContentRehydrationContractError


@dataclass(frozen=True)
class RehydratedContent:
    """Exact Memos response item; identity remains in the server request map."""

    selection_ref: str
    document: str
    source_sequence: int
    document_hash: str
    index_version: Literal["memo-v1"] = MEMO_INDEX_VERSION

    def __post_init__(self) -> None:
        if not isinstance(
            self.selection_ref, str
        ) or not _SELECTION_REF_PATTERN.fullmatch(self.selection_ref):
            raise ContentRehydrationContractError
        _require_document(self.document, self.document_hash)
        _require_sequence_hash_version(
            self.source_sequence, self.document_hash, self.index_version
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> RehydratedContent:
        _require_exact_fields(
            payload,
            {
                "selection_ref",
                "document",
                "source_sequence",
                "document_hash",
                "index_version",
            },
        )
        return cls(
            selection_ref=cast(str, payload["selection_ref"]),
            document=cast(str, payload["document"]),
            source_sequence=cast(int, payload["source_sequence"]),
            document_hash=cast(str, payload["document_hash"]),
            index_version=cast(Literal["memo-v1"], payload["index_version"]),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "selection_ref": self.selection_ref,
            "document": self.document,
            "source_sequence": self.source_sequence,
            "document_hash": self.document_hash,
            "index_version": self.index_version,
        }


@dataclass(frozen=True)
class ContentRehydrationResponse:
    """All-or-nothing response from one current Memos authority snapshot."""

    snapshot_token: str
    authority_token: str
    documents: tuple[RehydratedContent, ...]
    version: Literal["memo-evidence-rehydration-v1"] = CONTENT_REHYDRATION_VERSION

    def __post_init__(self) -> None:
        if self.version != CONTENT_REHYDRATION_VERSION:
            raise ContentRehydrationContractError
        _require_opaque_id(self.snapshot_token)
        _require_opaque_id(self.authority_token)
        if (
            not isinstance(self.documents, tuple)
            or not 1 <= len(self.documents) <= MAX_REHYDRATION_ITEMS
            or any(
                not isinstance(document, RehydratedContent)
                for document in self.documents
            )
            or len({document.selection_ref for document in self.documents})
            != len(self.documents)
        ):
            raise ContentRehydrationContractError

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> ContentRehydrationResponse:
        _require_exact_fields(
            payload,
            {"version", "snapshot_token", "authority_token", "documents"},
        )
        raw_documents = payload["documents"]
        if not isinstance(raw_documents, list):
            raise ContentRehydrationContractError
        return cls(
            version=cast(Literal["memo-evidence-rehydration-v1"], payload["version"]),
            snapshot_token=cast(str, payload["snapshot_token"]),
            authority_token=cast(str, payload["authority_token"]),
            documents=tuple(
                RehydratedContent.from_dict(_require_mapping(item))
                for item in raw_documents
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "snapshot_token": self.snapshot_token,
            "authority_token": self.authority_token,
            "documents": [document.to_dict() for document in self.documents],
        }


def build_content_rehydration_request(
    query: AuthorizedRetrievalQuery,
    snapshot: DerivedCandidateSnapshot,
    candidates: tuple[DerivedMemoCandidate, ...],
    *,
    memos_authority_ref: str,
) -> ContentRehydrationRequest:
    """Bind exactly the already-authorized, already-eligible R5 selection."""

    if not isinstance(query, AuthorizedRetrievalQuery) or not isinstance(
        snapshot, DerivedCandidateSnapshot
    ) or not isinstance(candidates, tuple) or not candidates:
        raise ContentRehydrationContractError
    try:
        eligible = select_eligible_candidates(query, snapshot)
    except DerivedRetrievalContractError:
        raise ContentRehydrationContractError from None
    if candidates != eligible:
        raise ContentRehydrationContractError
    return ContentRehydrationRequest(
        snapshot_token=snapshot.snapshot_token,
        memos_authority_ref=memos_authority_ref,
        selections=tuple(
            ContentRehydrationSelection(
                selection_ref=f"rehydration-{index}",
                memo_uid=candidate.memo_uid,
                source_sequence=candidate.source_sequence,
                document_hash=candidate.document_hash,
            )
            for index, candidate in enumerate(candidates, start=1)
        ),
    )


def rehydrate_from_memos_authority(
    request: ContentRehydrationRequest,
    authority: MemosCurrentAuthoritySnapshot,
) -> ContentRehydrationResponse:
    """Return all requested current documents or disclose no partial result."""

    if not isinstance(request, ContentRehydrationRequest) or not isinstance(
        authority, MemosCurrentAuthoritySnapshot
    ) or request.memos_authority_ref != authority.memos_authority_ref:
        raise ContentRehydrationContractError
    by_uid = {document.memo_uid: document for document in authority.documents}
    if len(by_uid) != len(request.selections) or set(by_uid) != {
        selection.memo_uid for selection in request.selections
    }:
        raise ContentRehydrationContractError

    documents: list[RehydratedContent] = []
    for selection in request.selections:
        document = by_uid[selection.memo_uid]
        if (
            document.source_sequence != selection.source_sequence
            or document.document_hash != selection.document_hash
            or document.index_version != selection.index_version
        ):
            raise ContentRehydrationContractError
        documents.append(
            RehydratedContent(
                selection_ref=selection.selection_ref,
                document=document.document,
                source_sequence=document.source_sequence,
                document_hash=document.document_hash,
            )
        )
    return ContentRehydrationResponse(
        snapshot_token=request.snapshot_token,
        authority_token=authority.authority_token,
        documents=tuple(documents),
    )


def materialize_rehydrated_documents(
    query: AuthorizedRetrievalQuery,
    snapshot: DerivedCandidateSnapshot,
    candidates: tuple[DerivedMemoCandidate, ...],
    request: ContentRehydrationRequest,
    response: ContentRehydrationResponse,
    *,
    memos_authority_ref: str,
    current_snapshot_token: str,
) -> tuple[DerivedMemoDocument, ...]:
    """Recheck both authority projections before creating R5 documents."""

    expected_request = build_content_rehydration_request(
        query,
        snapshot,
        candidates,
        memos_authority_ref=memos_authority_ref,
    )
    if (
        request != expected_request
        or response.snapshot_token != request.snapshot_token
        or current_snapshot_token != request.snapshot_token
        or len(response.documents) != len(request.selections)
    ):
        raise ContentRehydrationContractError
    by_ref = {document.selection_ref: document for document in response.documents}
    if len(by_ref) != len(response.documents):
        raise ContentRehydrationContractError

    materialized: list[DerivedMemoDocument] = []
    for candidate, selection in zip(candidates, request.selections, strict=True):
        document = by_ref.get(selection.selection_ref)
        if document is None or (
            selection.memo_uid != candidate.memo_uid
            or document.source_sequence != selection.source_sequence
            or document.document_hash != selection.document_hash
            or document.index_version != selection.index_version
        ):
            raise ContentRehydrationContractError
        materialized.append(
            DerivedMemoDocument(
                record_key=candidate.record_key,
                memo_uid=candidate.memo_uid,
                document=document.document,
                source_sequence=document.source_sequence,
                document_hash=document.document_hash,
                rebuild_generation=candidate.rebuild_generation,
                index_version=document.index_version,
            )
        )
    return tuple(materialized)


def map_content_rehydration_failure(error: BaseException) -> ContentRehydrationFailure:
    """Collapse every future transport/authority failure to one safe projection."""

    del error
    return ContentRehydrationFailure()


def _require_document(document: object, document_hash: object) -> None:
    if (
        not isinstance(document, str)
        or not document.strip()
        or len(document) > MAX_DOCUMENT_CHARS
        or not isinstance(document_hash, str)
        or document_hash != hash_lifecycle_document(document)
    ):
        raise ContentRehydrationContractError


def _require_sequence_hash_version(
    source_sequence: object, document_hash: object, index_version: object
) -> None:
    if (
        type(source_sequence) is not int
        or source_sequence < 1
        or not isinstance(document_hash, str)
        or not _SHA256_PATTERN.fullmatch(document_hash)
        or index_version != MEMO_INDEX_VERSION
    ):
        raise ContentRehydrationContractError


def _require_memo_uid(memo_uid: object) -> None:
    if not isinstance(memo_uid, str) or not _MEMO_UID_PATTERN.fullmatch(memo_uid):
        raise ContentRehydrationContractError


def _require_opaque_id(value: object) -> None:
    if not isinstance(value, str) or not _OPAQUE_ID_PATTERN.fullmatch(value):
        raise ContentRehydrationContractError


def _require_exact_fields(
    payload: Mapping[str, object], expected: set[str]
) -> None:
    if not isinstance(payload, Mapping) or set(payload) != expected:
        raise ContentRehydrationContractError


def _require_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ContentRehydrationContractError
    return value
