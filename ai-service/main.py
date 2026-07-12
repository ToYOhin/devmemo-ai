"""DevMemo AI service entrypoint."""

from __future__ import annotations

import json
import re
from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from database import get_memo_template, save_ai_note, save_memo_template
from llm import create_provider
from app.services.content_parser import parse_memo_content


class SummaryRequest(BaseModel):
    memo_id: str | int | None = None
    title: str = ""
    content: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)


class SummaryResponse(BaseModel):
    memo_id: str | int | None
    summary: str
    keywords: list[str]
    category: str
    suggested_tags: list[str]
    provider: str
    ai_note_id: int
    created_at: str


class MemoWebhookRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    activity_type: str = Field(alias="activityType")
    memo: dict[str, object] = Field(default_factory=dict)


app = FastAPI(title="DevMemo AI Service", version="0.1.0")
provider = create_provider()

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
    note = save_ai_note(request.memo_id, summary, keywords, category)
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


@app.get("/api/ai/templates/{memo_id}")
async def read_memo_template(memo_id: str) -> dict[str, object]:
    """Read a persisted structured Code Snippet or Bug Report."""

    template = get_memo_template(memo_id)
    if template is None:
        raise HTTPException(status_code=404, detail="memo template not found")
    return template


@app.post("/api/integrations/memos/webhook")
async def memos_webhook(request: MemoWebhookRequest) -> dict[str, object]:
    """Receive Memos create/update events without changing Memos core code."""

    if request.activity_type.endswith("deleted"):
        return {"code": 0, "message": "ignored deleted memo"}

    memo = request.memo
    content = str(memo.get("content") or "")
    if not content.strip():
        return {"code": 0, "message": "ignored empty memo", "memo_type": "plain"}

    memo_id = memo.get("uid") or memo.get("name") or memo.get("id")
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
    return response
