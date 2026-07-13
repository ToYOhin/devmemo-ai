# DevMemo AI 项目结构与边界

## Phase 3c 结构

~~~text
ai-service/
├── main.py                         # FastAPI routes and compatibility launcher
├── settings.py                     # environment-only composition settings
├── embedding.py                    # legacy list-based compatibility entry
├── app/domain/embeddings.py        # provider-neutral types and Protocol
├── app/services/embedding_service.py
│                                   # provider -> record -> store orchestration
├── app/services/embedding_factory.py
│                                   # memory/qdrant composition root
├── app/adapters/embedding.py       # deterministic provider
├── app/adapters/fastembed_embedding.py
│                                   # optional FastEmbed adapter
├── app/adapters/vector_store.py    # in-memory adapter
├── app/adapters/qdrant_vector_store.py
│                                   # optional qdrant-client adapter
├── app/services/memo_indexing.py
│                                   # one-Memo/one-vector index boundary
├── app/domain/retrieval.py         # provider-neutral citation/result contracts
├── app/services/retrieval_service.py
│                                   # query embedding -> search -> context/citations
├── scripts/smoke_qdrant.py         # opt-in real Qdrant lifecycle smoke
└── model-cache/                    # local generated cache, gitignored
~~~

## Qdrant adapter flow

~~~text
AI_VECTOR_STORE=qdrant
  -> AiSettings.from_env
  -> build_embedding_service
  -> QdrantVectorStore.from_url
  -> lazy qdrant-client import
  -> collection ensure
  -> upsert/query_points/delete
~~~

## Compose persistence

~~~text
qdrant-data:/qdrant/storage       -> Qdrant collection/point persistence
ai-model-cache:/app/model-cache   -> optional FastEmbed model cache
~~~

## Index health flow

~~~text
GET /api/ai/index/health
  -> current VectorStore.health()
  -> memory: local ready, no network
  -> qdrant: collection status/point_count
  -> adapter error: available=false, status=unavailable
~~~

## FastEmbed and indexing flow

~~~text
AI_EMBEDDING_PROVIDER=fastembed
  -> AiSettings.from_env
  -> build_embedding_service
  -> FastEmbedEmbeddingProvider.from_model_name
  -> MemoIndexDocument.from_memo
  -> EmbeddingService
  -> memory or Qdrant VectorStore
~~~

Phase 3c deliberately indexes the complete Memo as one document. Phase 4 adds
query embedding and retrieval for this whole-Memo path; chunking and reranking
remain deferred.

## Phase 4 RAG flow

~~~text
POST /api/ai/chat
  -> RetrievalService
  -> current EmbeddingProvider.embed(question)
  -> VectorStore.search(query, limit)
  -> Citation + context assembly
  -> deterministic/OpenAI/Ollama provider
  -> answer + citations + provider + retrieved_count
~~~

The index stores derived `content` metadata for server-side context assembly.
The API removes that internal field from public citation metadata.

## Webhook indexing flow

~~~text
AI_INDEX_ON_WEBHOOK=false -> summary/template flow only
AI_INDEX_ON_WEBHOOK=true
  -> memo.created/memo.updated -> stable embedding_id upsert
  -> memo.deleted -> stable embedding_id delete
  -> index failure -> index_status=failed, Webhook code=0
~~~

FastAPI/Pydantic 类型只存在 main.py 边界；domain 只使用 dataclass、Protocol、Mapping 和标准类型。qdrant-client 只存在 qdrant_vector_store.py，fastembed 只存在 fastembed_embedding.py。

## 迁移规则

1. 默认 memory 路径不得依赖网络、Qdrant 或模型下载。
2. 真实第三方依赖只通过 adapter 和 optional requirements 接入。
3. 先 fake contract，再做真实环境 smoke。
4. 不修改 Memos server/store/proto/web 核心。
