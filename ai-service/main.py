"""DevMemo AI service entrypoint."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from database import (
    begin_webhook_retry,
    get_ai_note,
    get_memo_template,
    get_webhook_event,
    get_webhook_event_stats,
    list_webhook_events,
    save_ai_note,
    save_memo_template,
    save_webhook_event,
    update_webhook_event,
)
from llm import create_provider
from app.services.content_parser import parse_memo_content
from app.services.embedding_factory import build_embedding_service
from app.services.memo_indexing import MemoIndexDocument, index_memo
from app.services.retrieval_service import RetrievalService
from app.services.webhook_security import verify_signature
from app.domain.retrieval import RetrievalInputError, RetrievalUnavailableError
from app.settings import parse_env_bool


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


app = FastAPI(title="DevMemo AI Service", version="0.1.0")
provider = create_provider()
embedding_service = build_embedding_service()


def _cors_origins() -> list[str]:
    configured = os.getenv("AI_CORS_ORIGINS", "http://localhost:3001")
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
    return SummaryResponse(
        memo_id=request.memo_id,
        summary=summary,
        keywords=keywords,
        category=category,
        suggested_tags=suggested_tags,
        provider=result.provider if result.text else "deterministic-fallback",
        ai_note_id=note["id"],
        created_at=note["created_at"],
    )


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
) -> dict[str, object]:
    """Read recent Webhook outbox state without starting a worker."""

    if status is not None and status not in {"pending", "processed", "failed"}:
        raise HTTPException(status_code=422, detail="unsupported webhook event status")
    try:
        items = list_webhook_events(status=status, limit=limit)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"items": items, "count": len(items), **get_webhook_event_stats()}


@app.post("/api/ai/ops/outbox/{event_id}/retry")
async def retry_webhook_outbox(event_id: str) -> dict[str, object]:
    """Explicitly retry one failed Webhook event within its persisted limit."""

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
        if _webhook_index_enabled():
            memo_id = _memo_id_from_memo(request.memo)
            if memo_id is None:
                return {"code": 0, "message": "ignored deleted memo", "index_status": "skipped"}
            try:
                deleted = embedding_service.delete_memo(memo_id)
            except Exception:
                return {"code": 0, "message": "ignored deleted memo", "index_status": "failed"}
            return {
                "code": 0,
                "message": "ignored deleted memo",
                "index_status": "deleted" if deleted else "skipped",
            }
        return {"code": 0, "message": "ignored deleted memo"}

    memo = request.memo
    content = str(memo.get("content") or "")
    if not content.strip():
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
        if memo_id is not None:
            persisted = save_memo_template(memo_id, parsed.kind, asdict(parsed.template), content)
            response["template_id"] = persisted["id"]
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


def _webhook_event_id(request: MemoWebhookRequest, raw_body: bytes) -> str:
    if request.event_id and request.event_id.strip():
        return request.event_id.strip()
    digest = hashlib.sha256(raw_body).hexdigest()
    return f"body-{digest}"


def _webhook_index_enabled() -> bool:
    return parse_env_bool("AI_INDEX_ON_WEBHOOK", default=False)


def _deterministic_rag_answer(context: str) -> str:
    """Return a useful offline answer while preserving the citation markers."""

    return f"根据知识库检索结果：\n{context}"


def _memo_id_from_memo(memo: dict[str, object]) -> object:
    return memo.get("uid") or memo.get("name") or memo.get("id")


def _index_webhook_memo(
    memo_id: object,
    content: str,
    memo: dict[str, object],
    memo_type: str | None,
) -> dict[str, object]:
    if memo_id is None:
        return {"index_status": "skipped"}
    try:
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
