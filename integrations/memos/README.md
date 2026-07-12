# Memos integration

Configure a Memos user webhook with:

```text
http://ai-service:8000/api/integrations/memos/webhook
```

The endpoint accepts `memos.memo.created`, `memos.memo.updated`, and acknowledges deleted events without indexing them. Deterministic mode is the default, so the integration can be tested without an LLM key.

The next hardening step is a shared secret or HMAC signature. The current Memos webhook payload has no project-specific authentication field, so this Docker-network URL must not be exposed directly to the public internet.
