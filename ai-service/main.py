"""DevMemo AI service entrypoint."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from database import (
    begin_webhook_retry,
    database_path,
    delete_memo_ai_state,
    get_ai_note,
    get_memo_insights,
    get_memo_template,
    get_webhook_event,
    get_webhook_event_stats,
    delete_webhook_retention_candidates,
    list_webhook_cleanup_audits,
    list_webhook_events,
    list_webhook_retention_candidates,
    save_ai_note,
    save_memo_insights,
    save_memo_template,
    save_webhook_event,
    update_webhook_event,
    update_memo_insight_status,
    webhook_retention_cutoff,
)
from llm import create_provider
from app.adapters.agent_observability import BoundedInMemoryObservabilityAdapter
from app.adapters.chunk_state import SqliteChunkIndexStateStore
from app.services.content_parser import parse_memo_content
from app.services.embedding_factory import (
    build_chunk_lifecycle_coordinator,
    build_embedding_service,
)
from app.services.memo_indexing import MemoIndexDocument, index_memo
from app.services.memo_insights import derive_memo_insights
from app.services.ops_security import summarize_error, verify_ops_token
from app.services.public_chunk_retrieval import build_public_chunk_response
from app.services.retrieval_service import RetrievalService
from app.services.agent_delegation import (
    INTERNAL_ANSWER_PATH,
    AgentDelegationError,
    AgentDelegationHeaders,
)
from app.services.evidence_answer_agent import AgentProviderError, EvidenceAnswerAgent
from app.services.durable_rehydration_runtime import (
    build_durable_rehydration_orchestrator,
)
from app.services.evidence_rehydration_http_client import (
    evidence_rehydration_client_lifespan,
)
from app.services.agent_lifecycle_http_adapter import (
    INTERNAL_LIFECYCLE_ACTIVATION_PATH,
    LifecycleHTTPResponse,
    MemoLifecycleHTTPAdapter,
)
from app.services.agent_lifecycle_runtime import build_memo_lifecycle_runtime
from app.services.agent_observability_runtime import (
    AnswerObservabilityOutcome,
    record_answer_observation,
)
from app.services.agent_lifecycle_transport import (
    INTERNAL_LIFECYCLE_PATH,
    LIFECYCLE_NONCE_HEADER,
    LIFECYCLE_SIGNATURE_HEADER,
    LIFECYCLE_TIMESTAMP_HEADER,
    LifecycleTransportHeaders,
)
from app.services.webhook_security import verify_signature
from app.domain.retrieval import RetrievalInputError, RetrievalUnavailableError
from app.settings import AiSettings, parse_env_bool


class SummaryRequest(BaseModel):
    memo_id: str | int | None = None
    title: str = ""
    content: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)


class EmbedRequest(BaseModel):
    memo_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    metadata: dict[str, object] = Field(default_factory=dict)


class EmbedResponse(BaseModel):
    embedding_id: str
    memo_id: str
    dimension: int
    provider: str


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=10)


class PublicChunkSearchRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=10)
    visible_memo_ids: list[str] = Field(min_length=1, max_length=100)


class RetentionCleanupRequest(BaseModel):
    approval_id: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,120}$")
    cutoff: str = Field(min_length=1, max_length=64)
    candidate_ids: list[str] = Field(min_length=1, max_length=100)
    preview_limit: int = Field(ge=1, le=100)
    confirm: bool = False
    dry_run: bool = True


class CitationResponse(BaseModel):
    memo_id: str
    embedding_id: str
    score: float
    metadata: dict[str, object]


class ChatResponse(BaseModel):
    answer: str
    citations: list[CitationResponse]
    provider: str
    retrieved_count: int


class SummaryResponse(BaseModel):
    memo_id: str | int | None
    summary: str
    keywords: list[str]
    category: str
    suggested_tags: list[str]
    provider: str
    ai_note_id: int
    created_at: str
    memo_type: str = "plain"
    template_id: int | None = None


class InsightPreviewRequest(BaseModel):
    memo_id: str = Field(min_length=1)
    title: str = ""
    content: str = Field(min_length=1)
    summary: str = ""


class InsightStatusRequest(BaseModel):
    status: Literal["accepted", "rejected"]
    version: int = Field(ge=1)


class MemoInsightResponse(BaseModel):
    insight_id: str
    memo_id: str
    insight_type: Literal["fact", "decision", "action", "bug"]
    title: str
    summary: str
    confidence: float
    status: Literal["pending", "accepted", "rejected"]
    source_refs: list[str]
    version: int
    created_at: str
    updated_at: str


class AiNoteResponse(BaseModel):
    memo_id: str
    summary: str
    keywords: list[str]
    category: str
    suggested_tags: list[str]
    provider: str
    created_at: str


class MemoWebhookRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    activity_type: str = Field(alias="activityType")
    event_id: str | None = Field(default=None, alias="eventId")
    memo: dict[str, object] = Field(default_factory=dict)


settings = AiSettings.from_env()


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    async with evidence_rehydration_client_lifespan(settings) as client:
        application.state.evidence_rehydration_client = client
        application.state.durable_rehydration_orchestrator = None
        application.state.memo_lifecycle_http_adapter = None
        application.state.agent_observability = None
        try:
            if settings.agent_enabled:
                application.state.agent_observability = (
                    BoundedInMemoryObservabilityAdapter(256)
                )
            lifecycle_runtime = build_memo_lifecycle_runtime(
                settings,
                embedding_service,
                database=database_path(),
            )
            if lifecycle_runtime is not None:
                if settings.agent_lifecycle_secret is None:
                    raise RuntimeError("memo lifecycle runtime is unavailable")
                application.state.memo_lifecycle_http_adapter = (
                    MemoLifecycleHTTPAdapter(
                        lifecycle_runtime,
                        settings.agent_lifecycle_secret,
                    )
                )
            application.state.durable_rehydration_orchestrator = (
                build_durable_rehydration_orchestrator(
                    settings,
                    embedding_service,
                    client,
                    database=database_path(),
                )
            )
            yield
        finally:
            application.state.agent_observability = None
            application.state.memo_lifecycle_http_adapter = None
            application.state.durable_rehydration_orchestrator = None
            application.state.evidence_rehydration_client = None


app = FastAPI(title="DevMemo AI Service", version="0.1.0", lifespan=lifespan)
provider = create_provider()
embedding_service = build_embedding_service(settings)
chunk_lifecycle_coordinator = build_chunk_lifecycle_coordinator(
    settings,
    provider=embedding_service.provider,
    state_store=SqliteChunkIndexStateStore(),
)


def _cors_origins() -> list[str]:
    configured = os.getenv(
        "AI_CORS_ORIGINS",
        "http://localhost:3001,http://127.0.0.1:3001",
    )
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["Accept", "Content-Type"],
)

KNOWN_KEYWORDS = {
    "FastAPI": "fastapi",
    "Docker": "docker",
    "Go": "golang",
    "Python": "python",
    "JavaScript": "javascript",
    "TypeScript": "typescript",
    "SQL": "sql",
    "Kubernetes": "kubernetes",
    "Network": "network",
}
CATEGORY_RULES = {
    "DevOps": ("docker", "kubernetes", "deploy", "ubuntu", "linux"),
    "Backend": ("fastapi", "golang", "python", "api", "server"),
    "Frontend": ("javascript", "typescript", "react", "vue", "css"),
    "Database": ("sql", "sqlite", "postgres", "mysql", "database"),
    "Testing": ("test", "pytest", "unittest", "ci"),
    "AI": ("embedding", "llm", "rag", "ollama", "openai"),
}


def deterministic_summary(request: SummaryRequest) -> tuple[str, list[str], str, list[str]]:
    text = f"{request.title} {request.content} {' '.join(request.tags)}".lower()
    keywords = list(request.tags[:5])
    for label, token in KNOWN_KEYWORDS.items():
        if token in text and label not in keywords:
            keywords.append(label)
    category = "Development"
    for candidate, tokens in CATEGORY_RULES.items():
        if any(re.search(rf"\b{re.escape(token)}\b", text) for token in tokens):
            category = candidate
            break
    if "docker" in text and ("port" in text or "端口" in text):
        summary = "Docker 容器端口映射问题分析"
    else:
        summary = request.content.strip().split(".", 1)[0].strip()[:160]
    return summary, keywords[:8], category, keywords[:5]


def parse_llm_json(raw_text: str, request: SummaryRequest) -> tuple[str, list[str], str, list[str]]:
    cleaned = raw_text.strip().removeprefix("```json").removesuffix("```").strip()
    try:
        payload = json.loads(cleaned)
        return (
            str(payload["summary"]),
            [str(value) for value in payload["keywords"]],
            str(payload["category"]),
            [str(value) for value in payload.get("suggested_tags", [])],
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return deterministic_summary(request)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "devmemo-ai", "provider": provider.name}


@app.get("/api/ai/index/health")
async def index_health() -> dict[str, object]:
    """Return read-only vector-store status without changing default composition."""

    return asdict(embedding_service.store.health())


@app.get("/api/ai/index/chunk-health")
async def chunk_index_health() -> dict[str, object]:
    """Report the explicit chunk index without changing complete-Memo chat."""

    return asdict(chunk_lifecycle_coordinator.health())


@app.post("/api/ai/v1/chunks/search")
async def search_public_chunks(
    request: PublicChunkSearchRequest,
    raw_request: Request,
    signature: str | None = Header(default=None, alias="X-DevMemo-Chunk-Signature"),
) -> dict[str, object]:
    """Return gateway-authorized, redacted chunk citations behind an opt-in flag."""

    _require_public_chunk_access(await raw_request.body(), signature)
    visible_memo_ids = _normalize_visible_memo_ids(request.visible_memo_ids)
    health = chunk_lifecycle_coordinator.health()
    if not health.available or health.status != "ready":
        raise HTTPException(status_code=503, detail="public chunk retrieval is unavailable")
    try:
        # The internal retrieval contract caps candidates at ten; dedupe occurs after authorization.
        result = chunk_lifecycle_coordinator.retrieve(request.question, limit=10)
        response = build_public_chunk_response(
            citations=result.citations,
            provider=chunk_lifecycle_coordinator.provider.name,
            visible_memo_ids=visible_memo_ids,
            limit=request.limit,
        )
    except RetrievalInputError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RetrievalUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return response.to_dict()


@app.post("/api/ai/summarize", response_model=SummaryResponse)
async def summarize(request: SummaryRequest) -> SummaryResponse:
    """Summarization contract; deterministic mode is safe for local MVP demos."""

    prompt = (
        "Return JSON with summary, keywords, category, and suggested_tags. "
        f"Title: {request.title}\nContent: {request.content}\nTags: {request.tags}"
    )
    result = await provider.generate(prompt)
    if provider.name == "deterministic":
        summary, keywords, category, suggested_tags = deterministic_summary(request)
    else:
        summary, keywords, category, suggested_tags = parse_llm_json(result.text, request)
    note = save_ai_note(
        request.memo_id,
        summary,
        keywords,
        category,
        suggested_tags=suggested_tags,
        provider=result.provider if result.text else "deterministic-fallback",
    )
    parsed = parse_memo_content(request.content)
    template_id: int | None = None
    if request.memo_id is not None and parsed.template is not None:
        template = save_memo_template(
            request.memo_id,
            parsed.kind,
            asdict(parsed.template),
            request.content,
        )
        template_id = int(template["id"])
    if request.memo_id is not None:
        insights = derive_memo_insights(
            str(request.memo_id), request.title, request.content, summary=summary
        )
        save_memo_insights([asdict(insight) for insight in insights])
    return SummaryResponse(
        memo_id=request.memo_id,
        summary=summary,
        keywords=keywords,
        category=category,
        suggested_tags=suggested_tags,
        provider=result.provider if result.text else "deterministic-fallback",
        ai_note_id=note["id"],
        created_at=note["created_at"],
        memo_type=parsed.kind,
        template_id=template_id,
    )


@app.post("/api/ai/insights/preview", response_model=list[MemoInsightResponse])
async def preview_memo_insights(request: InsightPreviewRequest) -> list[MemoInsightResponse]:
    """Preview deterministic insights without persisting or changing a Memo."""

    insights = derive_memo_insights(
        request.memo_id,
        request.title,
        request.content,
        summary=request.summary,
    )
    return [MemoInsightResponse(**asdict(insight)) for insight in insights]


@app.get("/api/ai/insights/{memo_id}", response_model=list[MemoInsightResponse])
async def read_memo_insights(
    memo_id: str,
    status: Literal["pending", "accepted", "rejected"] | None = None,
) -> list[MemoInsightResponse]:
    return [MemoInsightResponse(**item) for item in get_memo_insights(memo_id, status=status)]


@app.post("/api/ai/insights/{insight_id}/status", response_model=MemoInsightResponse)
async def change_memo_insight_status(
    insight_id: str,
    request: InsightStatusRequest,
) -> MemoInsightResponse:
    try:
        updated = update_memo_insight_status(insight_id, request.version, request.status)
    except ValueError as error:
        if "stale" in str(error):
            raise HTTPException(status_code=409, detail=str(error)) from error
        raise HTTPException(status_code=422, detail=str(error)) from error
    if updated is None:
        raise HTTPException(status_code=404, detail="memo insight not found")
    return MemoInsightResponse(**updated)


@app.post("/api/ai/embed", response_model=EmbedResponse)
async def embed_memo(request: EmbedRequest) -> EmbedResponse:
    """Create or replace one Memo vector using the configured provider/store."""

    try:
        document = MemoIndexDocument.from_memo(
            memo_id=request.memo_id,
            content=request.content,
            metadata=request.metadata,
        )
        result = index_memo(embedding_service, document)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return EmbedResponse(
        embedding_id=result.embedding_id,
        memo_id=result.memo_id,
        dimension=result.dimension,
        provider=result.provider,
    )


@app.post("/api/ai/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Retrieve whole Memos and answer with explicit source citations."""

    try:
        retrieved = RetrievalService(embedding_service).retrieve(request.question, request.limit)
    except RetrievalInputError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RetrievalUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    citations = [
        CitationResponse(
            memo_id=citation.memo_id,
            embedding_id=citation.embedding_id,
            score=citation.score,
            metadata=dict(citation.metadata),
        )
        for citation in retrieved.citations
    ]
    if not citations:
        return ChatResponse(
            answer="知识库中没有找到相关 Memo。",
            citations=[],
            provider=provider.name,
            retrieved_count=0,
        )

    prompt = (
        "Answer the question using only the knowledge-base context below. "
        "Cite sources with [1], [2] using the supplied context order, and state uncertainty "
        "when the context is insufficient.\n"
        f"Question: {request.question.strip()}\n"
        f"Context:\n{retrieved.context}"
    )
    try:
        result = await provider.generate(prompt)
    except Exception as error:
        raise HTTPException(status_code=502, detail="LLM provider failed") from error

    answer = _deterministic_rag_answer(retrieved.context) if provider.name == "deterministic" else result.text.strip()
    if not answer:
        raise HTTPException(status_code=502, detail="LLM provider returned an empty answer")
    return ChatResponse(
        answer=answer,
        citations=citations,
        provider=result.provider,
        retrieved_count=len(citations),
    )


@app.post(INTERNAL_ANSWER_PATH)
async def answer_delegated_agent_request(
    raw_request: Request,
    signature: str | None = Header(default=None, alias="X-DevMemo-Agent-Signature"),
    timestamp: str | None = Header(default=None, alias="X-DevMemo-Agent-Timestamp"),
) -> dict[str, object]:
    """Execute one Memos-signed Agent request without exposing a browser API."""

    if not settings.agent_enabled or settings.agent_internal_secret is None:
        raise HTTPException(status_code=404, detail="not found")

    recorder = getattr(raw_request.app.state, "agent_observability", None)
    outcome: AnswerObservabilityOutcome = "unavailable"
    try:
        durable_retrieval = None
        if settings.agent_rehydration_enabled:
            durable_retrieval = getattr(
                raw_request.app.state,
                "durable_rehydration_orchestrator",
                None,
            )
            if durable_retrieval is None:
                raise RetrievalUnavailableError("Agent retrieval unavailable")
        result = await EvidenceAnswerAgent(
            RetrievalService(embedding_service),
            provider,
            durable_retrieval,
        ).run_delegated(
            await raw_request.body(),
            AgentDelegationHeaders(signature or "", timestamp or ""),
            settings.agent_internal_secret,
            datetime.now(timezone.utc),
        )
        response = result.to_dict()
        outcome = (
            "no_context"
            if result.trace.terminal_state == "no_context"
            else "success"
        )
        return response
    except AgentDelegationError as error:
        outcome = "invalid"
        raise HTTPException(status_code=401, detail="invalid Agent delegation") from error
    except RetrievalInputError as error:
        outcome = "invalid"
        raise HTTPException(status_code=400, detail="invalid Agent request") from error
    except RetrievalUnavailableError as error:
        raise HTTPException(status_code=503, detail="Agent retrieval unavailable") from error
    except AgentProviderError as error:
        raise HTTPException(status_code=502, detail="Agent provider unavailable") from error
    finally:
        record_answer_observation(recorder, outcome)


@app.post(INTERNAL_LIFECYCLE_PATH)
async def apply_memo_lifecycle_event(
    raw_request: Request,
    signature: str | None = Header(default=None, alias=LIFECYCLE_SIGNATURE_HEADER),
    timestamp: str | None = Header(default=None, alias=LIFECYCLE_TIMESTAMP_HEADER),
    nonce: str | None = Header(default=None, alias=LIFECYCLE_NONCE_HEADER),
) -> Response:
    """Apply one authenticated Memos-owned lifecycle event when opted in."""

    adapter = getattr(raw_request.app.state, "memo_lifecycle_http_adapter", None)
    if not isinstance(adapter, MemoLifecycleHTTPAdapter):
        return _memo_lifecycle_response(LifecycleHTTPResponse(404))
    if not _memo_lifecycle_envelope_is_exact(raw_request):
        return _memo_lifecycle_response(LifecycleHTTPResponse(404))
    result = adapter.handle_event(
        method=raw_request.method,
        path=raw_request.url.path,
        body=await raw_request.body(),
        headers=LifecycleTransportHeaders(
            signature or "", timestamp or "", nonce or ""
        ),
        now=datetime.now(timezone.utc),
    )
    return _memo_lifecycle_response(result)


@app.post(INTERNAL_LIFECYCLE_ACTIVATION_PATH)
async def activate_memo_lifecycle_generation(
    raw_request: Request,
    signature: str | None = Header(default=None, alias=LIFECYCLE_SIGNATURE_HEADER),
    timestamp: str | None = Header(default=None, alias=LIFECYCLE_TIMESTAMP_HEADER),
    nonce: str | None = Header(default=None, alias=LIFECYCLE_NONCE_HEADER),
) -> Response:
    """Activate only an authenticated, reconciled rebuild generation."""

    adapter = getattr(raw_request.app.state, "memo_lifecycle_http_adapter", None)
    if not isinstance(adapter, MemoLifecycleHTTPAdapter):
        return _memo_lifecycle_response(LifecycleHTTPResponse(404))
    if not _memo_lifecycle_envelope_is_exact(raw_request):
        return _memo_lifecycle_response(LifecycleHTTPResponse(404))
    result = adapter.handle_activation(
        method=raw_request.method,
        path=raw_request.url.path,
        body=await raw_request.body(),
        headers=LifecycleTransportHeaders(
            signature or "", timestamp or "", nonce or ""
        ),
        now=datetime.now(timezone.utc),
    )
    return _memo_lifecycle_response(result)


def _memo_lifecycle_response(result: LifecycleHTTPResponse) -> Response:
    return Response(
        content=result.body,
        status_code=result.status_code,
        media_type=result.content_type,
        headers={"Cache-Control": "no-store"},
    )


def _memo_lifecycle_envelope_is_exact(request: Request) -> bool:
    return (
        not request.url.query
        and request.headers.get("content-type", "").strip().lower()
        == "application/json"
        and not request.headers.get("content-encoding")
    )


@app.get("/api/ai/notes/{memo_id}", response_model=AiNoteResponse)
async def read_ai_note(memo_id: str) -> AiNoteResponse:
    """Read a persisted AI summary without touching Memos storage."""

    note = get_ai_note(memo_id)
    if note is None:
        raise HTTPException(status_code=404, detail="AI note not found")
    return AiNoteResponse(**note)


@app.get("/api/ai/templates/{memo_id}")
async def read_memo_template(memo_id: str) -> dict[str, object]:
    """Read a persisted structured Code Snippet or Bug Report."""

    template = get_memo_template(memo_id)
    if template is None:
        raise HTTPException(status_code=404, detail="memo template not found")
    return template


@app.get("/api/ai/ops/outbox")
async def read_webhook_outbox(
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    ops_token: str | None = Header(default=None, alias="X-DevMemo-Ops-Token"),
) -> dict[str, object]:
    """Read recent Webhook outbox state without starting a worker."""

    _require_ops_access(ops_token)
    if status is not None and status not in {"pending", "processed", "failed"}:
        raise HTTPException(status_code=422, detail="unsupported webhook event status")
    try:
        items = list_webhook_events(status=status, limit=limit)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    stats = get_webhook_event_stats()
    return {
        "items": [_public_webhook_event(event) for event in items],
        "count": len(items),
        "by_status": stats["by_status"],
        "exhausted_count": stats["exhausted_count"],
        "recent_errors": [
            {
                **error,
                "last_error": summarize_error(error["last_error"]),
            }
            for error in stats["recent_errors"]
        ],
    }


@app.get("/api/ai/ops/outbox/retention-preview")
async def preview_webhook_retention(
    older_than_days: int = Query(default=30, ge=1, le=3650),
    limit: int = Query(default=100, ge=1, le=100),
    ops_token: str | None = Header(default=None, alias="X-DevMemo-Ops-Token"),
) -> dict[str, object]:
    """Preview inactive terminal events without deleting or mutating them."""

    _require_ops_access(ops_token)
    try:
        cutoff = webhook_retention_cutoff(older_than_days)
        candidates = list_webhook_retention_candidates(older_than_days, limit, cutoff)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "older_than_days": older_than_days,
        "cutoff": cutoff,
        "preview_limit": limit,
        "count": len(candidates),
        "candidate_ids": [str(candidate["event_id"]) for candidate in candidates],
        "candidates": [_public_webhook_event(event) for event in candidates],
    }


@app.get("/api/ai/ops/alerts")
async def read_webhook_alerts(
    ops_token: str | None = Header(default=None, alias="X-DevMemo-Ops-Token"),
) -> dict[str, object]:
    """Export a bounded failure summary for external read-only alert polling."""

    _require_ops_access(ops_token)
    stats = get_webhook_event_stats()
    alerts = [
        {
            **error,
            "severity": "critical"
            if error["attempts"] >= error["max_attempts"]
            else "warning",
            "last_error": summarize_error(error["last_error"]),
        }
        for error in stats["recent_errors"]
    ]
    failed_count = stats["by_status"]["failed"]
    return {
        "has_alert": failed_count > 0,
        "failed_count": failed_count,
        "exhausted_count": stats["exhausted_count"],
        "alert_count": len(alerts),
        "alerts": alerts,
    }


@app.post("/api/ai/ops/outbox/retention-cleanup")
async def cleanup_webhook_retention(
    request: RetentionCleanupRequest,
    ops_token: str | None = Header(default=None, alias="X-DevMemo-Ops-Token"),
    ops_actor: str | None = Header(default=None, alias="X-DevMemo-Ops-Actor"),
) -> dict[str, object]:
    """Delete an unchanged preview set only after explicit confirmation."""

    _require_ops_access(ops_token)
    if request.dry_run:
        return {
            "code": 0,
            "message": "dry-run only; explicit confirmation required",
            "executed": False,
            "dry_run": True,
            "requires_confirmation": True,
            "approval_id": request.approval_id,
            "candidate_count": len(request.candidate_ids),
            "deleted_count": 0,
        }
    if not request.confirm:
        raise HTTPException(status_code=409, detail="explicit cleanup confirmation required")
    try:
        audit = delete_webhook_retention_candidates(
            request.approval_id,
            request.candidate_ids,
            request.cutoff,
            _ops_actor_digest(ops_actor),
            request.preview_limit,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {
        "code": 0,
        "message": "webhook retention cleanup completed",
        "executed": True,
        "dry_run": False,
        "replayed": audit["replayed"],
        **_public_cleanup_audit(audit),
    }


@app.get("/api/ai/ops/outbox/cleanup-audits")
async def read_webhook_cleanup_audits(
    limit: int = Query(default=50, ge=1, le=100),
    ops_token: str | None = Header(default=None, alias="X-DevMemo-Ops-Token"),
) -> dict[str, object]:
    """Read cleanup execution records without exposing secrets or payloads."""

    _require_ops_access(ops_token)
    try:
        audits = list_webhook_cleanup_audits(limit)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "items": [_public_cleanup_audit(audit) for audit in audits],
        "count": len(audits),
    }


@app.post("/api/ai/ops/outbox/{event_id}/retry")
async def retry_webhook_outbox(
    event_id: str,
    ops_token: str | None = Header(default=None, alias="X-DevMemo-Ops-Token"),
) -> dict[str, object]:
    """Explicitly retry one failed Webhook event within its persisted limit."""

    _require_ops_access(ops_token)
    try:
        event = begin_webhook_retry(event_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if event is None:
        raise HTTPException(status_code=404, detail="webhook event not found")

    try:
        request = MemoWebhookRequest.model_validate(event["payload"])
        response = await _process_memos_webhook(request)
    except Exception as error:
        failed = update_webhook_event(event_id, "failed", str(error))
        return {
            "code": 0,
            "message": "webhook retry failed",
            "event_id": event_id,
            "outbox_status": failed["status"],
            "attempts": failed["attempts"],
            "max_attempts": failed["max_attempts"],
        }

    processed = update_webhook_event(event_id, "processed")
    return {
        "code": 0,
        "message": "webhook retried",
        "event_id": event_id,
        "outbox_status": processed["status"],
        "attempts": processed["attempts"],
        "max_attempts": processed["max_attempts"],
        "result": response,
    }


@app.post("/api/integrations/memos/webhook")
async def memos_webhook(
    request: MemoWebhookRequest,
    raw_request: Request,
    signature: str | None = Header(default=None, alias="X-DevMemo-Signature"),
) -> dict[str, object]:
    """Receive Memos create/update events without changing Memos core code."""

    if not verify_signature(
        await raw_request.body(),
        signature,
        os.getenv("AI_WEBHOOK_SECRET", "").strip(),
    ):
        raise HTTPException(status_code=401, detail="invalid webhook signature")

    raw_body = await raw_request.body()
    event_id = _webhook_event_id(request, raw_body)
    existing = _read_or_enqueue_webhook_event(request, event_id)
    if existing["is_duplicate"]:
        return {
            "code": 0,
            "message": "duplicate webhook ignored",
            "event_id": event_id,
            "outbox_status": existing["event"]["status"],
        }

    try:
        response = await _process_memos_webhook(request)
    except Exception as error:
        failed = update_webhook_event(event_id, "failed", str(error))
        return {
            "code": 0,
            "message": "webhook processing failed",
            "event_id": event_id,
            "outbox_status": failed["status"],
        }
    update_webhook_event(event_id, "processed")
    return response


async def _process_memos_webhook(request: MemoWebhookRequest) -> dict[str, object]:
    """Run the legacy Webhook business flow after idempotent enqueue."""

    if request.activity_type.endswith("deleted"):
        memo_id = _memo_id_from_memo(request.memo)
        if memo_id is None:
            return {"code": 0, "message": "ignored deleted memo", "index_status": "skipped"}
        if _webhook_index_enabled():
            try:
                if _webhook_index_mode() == "chunk":
                    result = chunk_lifecycle_coordinator.delete_memo(str(memo_id))
                    derived_cleanup = delete_memo_ai_state(str(memo_id))
                    return {
                        "code": 0,
                        "message": "ignored deleted memo",
                        "index_status": "deleted" if result.deleted_count else "skipped",
                        "index_mode": result.index_mode,
                        "deleted_chunk_count": result.deleted_count,
                        "derived_cleanup": derived_cleanup,
                    }
                deleted = embedding_service.delete_memo(memo_id)
            except Exception:
                derived_cleanup = delete_memo_ai_state(str(memo_id))
                return {
                    "code": 0,
                    "message": "ignored deleted memo",
                    "index_status": "failed",
                    "derived_cleanup": derived_cleanup,
                }
            derived_cleanup = delete_memo_ai_state(str(memo_id))
            return {
                "code": 0,
                "message": "ignored deleted memo",
                "index_status": "deleted" if deleted else "skipped",
                "derived_cleanup": derived_cleanup,
            }
        derived_cleanup = delete_memo_ai_state(str(memo_id))
        return {"code": 0, "message": "ignored deleted memo", "derived_cleanup": derived_cleanup}

    memo = request.memo
    content = str(memo.get("content") or "")
    if not content.strip():
        if _webhook_index_enabled() and _webhook_index_mode() == "chunk":
            memo_id = _memo_id_from_memo(memo)
            if memo_id is not None:
                try:
                    result = chunk_lifecycle_coordinator.upsert_memo(
                        str(memo_id), "", metadata={"memo_type": "plain"}
                    )
                    if result.deleted_count:
                        return {
                            "code": 0,
                            "message": "ignored empty memo",
                            "memo_type": "plain",
                            "index_status": "deleted",
                            "index_mode": result.index_mode,
                            "deleted_chunk_count": result.deleted_count,
                        }
                except Exception:
                    return {
                        "code": 0,
                        "message": "ignored empty memo",
                        "memo_type": "plain",
                        "index_status": "failed",
                    }
        return {"code": 0, "message": "ignored empty memo", "memo_type": "plain"}

    memo_id = _memo_id_from_memo(memo)
    parsed = parse_memo_content(content)
    result = await summarize(
        SummaryRequest(
            memo_id=memo_id,
            title=str(memo.get("name") or ""),
            content=content,
            tags=[str(tag) for tag in memo.get("tags", []) if tag],
        )
    )
    response: dict[str, object] = {
        "code": 0,
        "message": "accepted",
        "ai_note_id": result.ai_note_id,
        "memo_type": parsed.kind,
    }
    if parsed.template is not None:
        response["template"] = asdict(parsed.template)
        if result.template_id is not None:
            response["template_id"] = result.template_id
    if parsed.errors:
        response["parse_errors"] = list(parsed.errors)
    if _webhook_index_enabled():
        response.update(_index_webhook_memo(memo_id, content, memo, parsed.kind))
    else:
        response["index_status"] = "skipped"
    return response


def _read_or_enqueue_webhook_event(
    request: MemoWebhookRequest,
    event_id: str,
) -> dict[str, object]:
    existing = get_webhook_event(event_id)
    if existing is not None:
        return {"is_duplicate": True, "event": existing}
    payload = request.model_dump(mode="json", by_alias=True, exclude_none=True)
    return {
        "is_duplicate": False,
        "event": save_webhook_event(event_id, request.activity_type, payload),
    }


def _require_ops_access(provided_token: str | None) -> None:
    if not verify_ops_token(provided_token, os.getenv("AI_OPS_TOKEN", "")):
        raise HTTPException(status_code=401, detail="invalid ops token")


def _require_public_chunk_access(raw_body: bytes, signature: str | None) -> None:
    if not parse_env_bool("AI_PUBLIC_CHUNK_RETRIEVAL", default=False):
        raise HTTPException(status_code=503, detail="public chunk retrieval is disabled")
    secret = os.getenv("AI_PUBLIC_CHUNK_SECRET", "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="public chunk retrieval is unavailable")
    if not verify_signature(raw_body, signature, secret):
        raise HTTPException(status_code=401, detail="invalid public chunk signature")


def _normalize_visible_memo_ids(raw_ids: list[str]) -> frozenset[str]:
    normalized = frozenset(memo_id.strip() for memo_id in raw_ids if memo_id.strip())
    if not normalized or len(normalized) != len(raw_ids):
        raise HTTPException(status_code=422, detail="visible_memo_ids must contain unique non-empty values")
    return normalized


def _ops_actor_digest(provided_actor: str | None) -> str:
    actor = (provided_actor or "anonymous").strip() or "anonymous"
    return hashlib.sha256(actor[:200].encode("utf-8")).hexdigest()


def _public_webhook_event(event: dict[str, object]) -> dict[str, object]:
    """Expose operational metadata without returning the raw Webhook payload."""

    return {
        "event_id": event["event_id"],
        "event_type": event["event_type"],
        "status": event["status"],
        "attempts": event["attempts"],
        "max_attempts": event["max_attempts"],
        "last_error": summarize_error(event["last_error"]),
        "created_at": event["created_at"],
        "updated_at": event["updated_at"],
    }


def _public_cleanup_audit(audit: dict[str, object]) -> dict[str, object]:
    return {
        "approval_id": audit["approval_id"],
        "actor_digest": audit["actor_digest"],
        "cutoff": audit["cutoff"],
        "candidate_ids": audit["candidate_ids"],
        "preview_limit": audit["preview_limit"],
        "candidate_count": audit["candidate_count"],
        "deleted_count": audit["deleted_count"],
        "created_at": audit["created_at"],
    }


def _webhook_event_id(request: MemoWebhookRequest, raw_body: bytes) -> str:
    if request.event_id and request.event_id.strip():
        return request.event_id.strip()
    digest = hashlib.sha256(raw_body).hexdigest()
    return f"body-{digest}"


def _webhook_index_enabled() -> bool:
    return parse_env_bool("AI_INDEX_ON_WEBHOOK", default=False)


def _webhook_index_mode() -> str:
    mode = os.getenv("AI_INDEX_MODE", "memo").strip().lower()
    if mode not in {"memo", "chunk"}:
        raise ValueError("AI_INDEX_MODE must be memo or chunk")
    return mode


def _deterministic_rag_answer(context: str) -> str:
    """Return a useful offline answer while preserving the citation markers."""

    return f"根据知识库检索结果：\n{context}"


def _memo_id_from_memo(memo: dict[str, object]) -> object:
    uid = str(memo.get("uid") or "").strip()
    if uid:
        return uid

    name = str(memo.get("name") or "").strip()
    if name:
        # Memos webhooks identify current Memos as `memos/<uid>`, while the
        # detail UI queries AI state with that terminal uid.
        if name.startswith("memos/"):
            resource_uid = name.removeprefix("memos/").strip()
            if resource_uid and "/" not in resource_uid:
                return resource_uid
        return name

    return memo.get("id")


def _index_webhook_memo(
    memo_id: object,
    content: str,
    memo: dict[str, object],
    memo_type: str | None,
) -> dict[str, object]:
    if memo_id is None:
        return {"index_status": "skipped"}
    try:
        if _webhook_index_mode() == "chunk":
            result = chunk_lifecycle_coordinator.upsert_memo(
                str(memo_id),
                content,
                metadata={
                    "title": str(memo.get("name") or ""),
                    "tags": [str(tag) for tag in memo.get("tags", []) if tag],
                    "memo_type": memo_type or "plain",
                },
            )
            return {
                "index_status": "indexed",
                "index_mode": result.index_mode,
                "index_version": result.index_version,
                "chunk_count": result.chunk_count,
                "deleted_chunk_count": result.deleted_count,
                "embedding_provider": result.provider,
            }
        document = MemoIndexDocument.from_memo(
            memo_id=str(memo_id),
            content=content,
            metadata={
                "title": str(memo.get("name") or ""),
                "tags": [str(tag) for tag in memo.get("tags", []) if tag],
                "memo_type": memo_type or "plain",
            },
        )
        result = index_memo(embedding_service, document)
    except Exception:
        return {"index_status": "failed"}
    return {
        "index_status": "indexed",
        "embedding_id": result.embedding_id,
        "embedding_provider": result.provider,
    }
