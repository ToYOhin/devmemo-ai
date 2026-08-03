"""Unwired contracts for lifecycle-safe durable complete-Memo retrieval.

The types in this module carry no provider, HTTP, vector-store, or runtime
dependency.  Derived candidates deliberately contain no Memo document or
arbitrary citation metadata so visibility and lifecycle checks can run before
document materialization.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal

from app.domain.agent_lifecycle import (
    MAX_DOCUMENT_CHARS,
    MEMO_INDEX_VERSION,
    MemoLifecycleState,
    hash_lifecycle_document,
    is_retrieval_eligible,
)


DURABLE_RETRIEVAL_VERSION: Literal["durable-authorized-retrieval-v1"] = "durable-authorized-retrieval-v1"
MAX_AUTHORIZED_MEMO_UIDS = 1_000
MAX_QUERY_CHARS = 4_000
MAX_RETRIEVAL_LIMIT = 10

_MEMO_UID_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,34}[A-Za-z0-9])?$"
)
_OPAQUE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class AuthorizedRetrievalContractError(ValueError):
    """Reject an invalid Memos-authority query without echoing its values."""

    def __init__(self) -> None:
        super().__init__("invalid authorized retrieval query")


class DerivedRetrievalContractError(ValueError):
    """Reject inconsistent derived state without exposing store data."""

    def __init__(self) -> None:
        super().__init__("invalid derived retrieval state")


@dataclass(frozen=True)
class AuthorizedRetrievalQuery:
    """Memos-authorized complete-Memo UID capability for one bounded search."""

    question: str
    limit: int
    authorized_memo_uids: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.question, str)
            or not self.question.strip()
            or len(self.question.strip()) > MAX_QUERY_CHARS
        ):
            raise AuthorizedRetrievalContractError
        if type(self.limit) is not int or not 1 <= self.limit <= MAX_RETRIEVAL_LIMIT:
            raise AuthorizedRetrievalContractError
        if not isinstance(self.authorized_memo_uids, tuple):
            raise AuthorizedRetrievalContractError
        if len(self.authorized_memo_uids) > MAX_AUTHORIZED_MEMO_UIDS:
            raise AuthorizedRetrievalContractError
        if any(
            not isinstance(uid, str) or not _MEMO_UID_PATTERN.fullmatch(uid)
            for uid in self.authorized_memo_uids
        ):
            raise AuthorizedRetrievalContractError
        if len(set(self.authorized_memo_uids)) != len(self.authorized_memo_uids):
            raise AuthorizedRetrievalContractError
        object.__setattr__(self, "question", self.question.strip())

    @property
    def authorized_uid_set(self) -> frozenset[str]:
        return frozenset(self.authorized_memo_uids)


@dataclass(frozen=True)
class DerivedMemoCandidate:
    """Content-free ranked record joined with its derived A4 ledger state."""

    record_key: str
    memo_uid: str
    score: float
    source_sequence: int
    document_hash: str
    rebuild_generation: str
    index_version: str
    lifecycle_state: MemoLifecycleState | None
    failure_quarantined: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.record_key, str) or not _OPAQUE_ID_PATTERN.fullmatch(
            self.record_key
        ):
            raise DerivedRetrievalContractError
        if not isinstance(self.memo_uid, str) or not _MEMO_UID_PATTERN.fullmatch(
            self.memo_uid
        ):
            raise DerivedRetrievalContractError
        if (
            isinstance(self.score, bool)
            or not isinstance(self.score, (int, float))
            or not math.isfinite(self.score)
        ):
            raise DerivedRetrievalContractError
        if type(self.source_sequence) is not int or self.source_sequence < 1:
            raise DerivedRetrievalContractError
        if not isinstance(self.document_hash, str) or not _SHA256_PATTERN.fullmatch(
            self.document_hash
        ):
            raise DerivedRetrievalContractError
        if not isinstance(
            self.rebuild_generation, str
        ) or not _OPAQUE_ID_PATTERN.fullmatch(self.rebuild_generation):
            raise DerivedRetrievalContractError
        if not isinstance(self.index_version, str) or not self.index_version:
            raise DerivedRetrievalContractError
        if self.lifecycle_state is not None and not isinstance(
            self.lifecycle_state, MemoLifecycleState
        ):
            raise DerivedRetrievalContractError
        if type(self.failure_quarantined) is not bool:
            raise DerivedRetrievalContractError


@dataclass(frozen=True)
class DerivedCandidateSnapshot:
    """One content-free repository snapshot with its currently active generation."""

    active_generation: str | None
    snapshot_token: str
    candidates: tuple[DerivedMemoCandidate, ...]

    def __post_init__(self) -> None:
        if self.active_generation is not None and (
            not isinstance(self.active_generation, str)
            or not _OPAQUE_ID_PATTERN.fullmatch(self.active_generation)
        ):
            raise DerivedRetrievalContractError
        if not isinstance(self.snapshot_token, str) or not _OPAQUE_ID_PATTERN.fullmatch(
            self.snapshot_token
        ):
            raise DerivedRetrievalContractError
        if not isinstance(self.candidates, tuple) or any(
            not isinstance(candidate, DerivedMemoCandidate)
            for candidate in self.candidates
        ):
            raise DerivedRetrievalContractError
        if len(self.candidates) > MAX_AUTHORIZED_MEMO_UIDS:
            raise DerivedRetrievalContractError


@dataclass(frozen=True)
class DerivedMemoDocument:
    """A complete Memo document loaded only after authorization and eligibility."""

    record_key: str
    memo_uid: str
    document: str
    source_sequence: int
    document_hash: str
    rebuild_generation: str
    index_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.record_key, str) or not _OPAQUE_ID_PATTERN.fullmatch(
            self.record_key
        ):
            raise DerivedRetrievalContractError
        if not isinstance(self.memo_uid, str) or not _MEMO_UID_PATTERN.fullmatch(
            self.memo_uid
        ):
            raise DerivedRetrievalContractError
        if (
            not isinstance(self.document, str)
            or not self.document.strip()
            or len(self.document) > MAX_DOCUMENT_CHARS
        ):
            raise DerivedRetrievalContractError
        if type(self.source_sequence) is not int or self.source_sequence < 1:
            raise DerivedRetrievalContractError
        if not isinstance(self.document_hash, str) or not _SHA256_PATTERN.fullmatch(
            self.document_hash
        ):
            raise DerivedRetrievalContractError
        if self.document_hash != hash_lifecycle_document(self.document):
            raise DerivedRetrievalContractError
        if not isinstance(
            self.rebuild_generation, str
        ) or not _OPAQUE_ID_PATTERN.fullmatch(self.rebuild_generation):
            raise DerivedRetrievalContractError
        if not isinstance(self.index_version, str) or not self.index_version:
            raise DerivedRetrievalContractError


@dataclass(frozen=True)
class ServerOwnedCitation:
    """Allowlisted citation created by this service, never by a Provider/store."""

    memo_uid: str
    source_sequence: int
    index_version: Literal["memo-v1"] = MEMO_INDEX_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.memo_uid, str) or not _MEMO_UID_PATTERN.fullmatch(
            self.memo_uid
        ):
            raise DerivedRetrievalContractError
        if type(self.source_sequence) is not int or self.source_sequence < 1:
            raise DerivedRetrievalContractError
        if self.index_version != MEMO_INDEX_VERSION:
            raise DerivedRetrievalContractError

    def to_dict(self) -> dict[str, object]:
        return {
            "memo_uid": self.memo_uid,
            "source_sequence": self.source_sequence,
            "index_version": self.index_version,
        }


@dataclass(frozen=True)
class AuthorizedRetrievalEvidence:
    """Internal evidence with a request-local reference and server citation."""

    reference: str
    document: str
    citation: ServerOwnedCitation

    def __post_init__(self) -> None:
        if not isinstance(self.reference, str) or not re.fullmatch(
            r"evidence-[1-9][0-9]*", self.reference
        ):
            raise DerivedRetrievalContractError
        if not isinstance(self.document, str) or not self.document.strip():
            raise DerivedRetrievalContractError
        if not isinstance(self.citation, ServerOwnedCitation):
            raise DerivedRetrievalContractError


@dataclass(frozen=True)
class AuthorizedRetrievalResult:
    """Internal result; only ``safe_observation`` is content-free/observable."""

    evidence: tuple[AuthorizedRetrievalEvidence, ...]
    version: Literal["durable-authorized-retrieval-v1"] = DURABLE_RETRIEVAL_VERSION

    def __post_init__(self) -> None:
        if self.version != DURABLE_RETRIEVAL_VERSION:
            raise DerivedRetrievalContractError
        if not isinstance(self.evidence, tuple) or any(
            not isinstance(item, AuthorizedRetrievalEvidence) for item in self.evidence
        ):
            raise DerivedRetrievalContractError
        expected_references = tuple(
            f"evidence-{index}" for index in range(1, len(self.evidence) + 1)
        )
        if tuple(item.reference for item in self.evidence) != expected_references:
            raise DerivedRetrievalContractError

    @property
    def context(self) -> str:
        return "\n\n".join(
            f"[{item.reference}]\n{item.document}" for item in self.evidence
        )

    @property
    def protected_context_fragments(self) -> tuple[str, ...]:
        return tuple(item.document for item in self.evidence)

    def safe_observation(self) -> dict[str, object]:
        return {
            "version": self.version,
            "retrieved_count": len(self.evidence),
            "references": [item.reference for item in self.evidence],
        }


def select_eligible_candidates(
    query: AuthorizedRetrievalQuery,
    snapshot: DerivedCandidateSnapshot,
) -> tuple[DerivedMemoCandidate, ...]:
    """Intersect visibility before selecting any record for document loading."""

    if not query.authorized_memo_uids or snapshot.active_generation is None:
        return ()

    authorized = query.authorized_uid_set
    scoped = tuple(
        candidate for candidate in snapshot.candidates if candidate.memo_uid in authorized
    )
    if len({item.record_key for item in scoped}) != len(scoped):
        raise DerivedRetrievalContractError
    if len({item.memo_uid for item in scoped}) != len(scoped):
        raise DerivedRetrievalContractError

    eligible: list[DerivedMemoCandidate] = []
    for candidate in scoped:
        state = candidate.lifecycle_state
        if state is not None and (
            state.memo_uid != candidate.memo_uid
            or state.index_version != MEMO_INDEX_VERSION
        ):
            raise DerivedRetrievalContractError
        if candidate.index_version != MEMO_INDEX_VERSION:
            continue
        if candidate.rebuild_generation != snapshot.active_generation:
            continue
        if candidate.failure_quarantined:
            continue
        if not is_retrieval_eligible(
            state,
            vector_source_sequence=candidate.source_sequence,
            vector_document_hash=candidate.document_hash,
        ):
            continue
        eligible.append(candidate)
        if len(eligible) == query.limit:
            break
    return tuple(eligible)


def project_authorized_result(
    query: AuthorizedRetrievalQuery,
    candidates: tuple[DerivedMemoCandidate, ...],
    documents: tuple[DerivedMemoDocument, ...],
) -> AuthorizedRetrievalResult:
    """Cross-check documents and anchor final identity to Memos authority."""

    if len(documents) != len(candidates):
        raise DerivedRetrievalContractError
    authoritative_uids = {uid: uid for uid in query.authorized_memo_uids}
    by_key: dict[str, DerivedMemoDocument] = {}
    for candidate_document in documents:
        if candidate_document.record_key in by_key:
            raise DerivedRetrievalContractError
        by_key[candidate_document.record_key] = candidate_document

    evidence: list[AuthorizedRetrievalEvidence] = []
    for index, candidate in enumerate(candidates, start=1):
        authoritative_uid = authoritative_uids.get(candidate.memo_uid)
        document = by_key.get(candidate.record_key)
        if authoritative_uid is None or document is None or any(
            (
                document.memo_uid != candidate.memo_uid,
                document.source_sequence != candidate.source_sequence,
                document.document_hash != candidate.document_hash,
                document.rebuild_generation != candidate.rebuild_generation,
                document.index_version != candidate.index_version,
            )
        ):
            raise DerivedRetrievalContractError
        evidence.append(
            AuthorizedRetrievalEvidence(
                reference=f"evidence-{index}",
                document=document.document,
                citation=ServerOwnedCitation(
                    memo_uid=authoritative_uid,
                    source_sequence=candidate.source_sequence,
                ),
            )
        )
    return AuthorizedRetrievalResult(tuple(evidence))
