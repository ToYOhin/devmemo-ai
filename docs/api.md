# API

Base URL: `http://localhost:8000`

## `GET /health`

Returns service status and the active provider.

## `POST /api/ai/summarize`

Request:

```json
{
  "memo_id": "memo-42",
  "title": "Docker port issue",
  "content": "FastAPI deployment failed because the Docker port mapping was wrong.",
  "tags": ["FastAPI", "Docker"]
}
```

Response includes `summary`, `keywords`, `category`, `suggested_tags`, `provider`, `ai_note_id`, and `created_at`.

## `GET /api/ai/templates/{memo_id}`

Returns the AI Service-owned structured template for a Code Snippet or Bug Report. The response includes `memo_id`, `kind`, `payload`, `raw_content`, `created_at`, and `updated_at`. Missing templates return `404`.

`payload` is derived data; `raw_content` is retained so the parser can be upgraded or the record rebuilt later.

## `POST /api/integrations/memos/webhook`

Accepts the Memos user webhook payload for `memos.memo.created` and `memos.memo.updated`. Deleted and empty events are acknowledged and ignored. The response uses Memos' expected `{ "code": 0, "message": "..." }` contract.

For an opted-in structured Memo, the response also contains `memo_type` and `template`:

```json
{
  "code": 0,
  "message": "accepted",
  "memo_type": "code",
  "template": {
    "title": "Port check",
    "language": "Go",
    "code": "fmt.Println(8080)",
    "description": "",
    "tags": []
  }
}
```

Supported template markers are `type: code`, `type=code`, `type: bug`, and `type=bug`. A Code Snippet accepts Python, Go, JavaScript, TypeScript, C++, and SQL. Invalid or unmarked content falls back to `memo_type: plain` and does not block Memo saving.

## Planned APIs

- `POST /api/ai/embed` — Phase 3 model-backed embedding and Qdrant indexing.
- `POST /api/ai/chat` — Phase 3 retrieval-augmented knowledge-base Q&A.
