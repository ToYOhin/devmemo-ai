from app.services.memo_indexing import MemoIndexDocument, index_memo


def test_memo_index_document_keeps_one_full_memo_as_the_index_unit():
    document = MemoIndexDocument.from_memo(
        memo_id="memo-1",
        content="Docker port mapping",
        metadata={"title": "Docker", "tags": ["network"]},
    )

    assert document.memo_id == "memo-1"
    assert document.content == "Docker port mapping"
    assert document.metadata == {
        "title": "Docker",
        "tags": ["network"],
        "content": "Docker port mapping",
        "source_type": "memo",
        "index_version": "memo-v1",
    }
    assert "chunk_id" not in document.metadata


def test_index_memo_delegates_to_configured_embedding_service():
    class FakeEmbeddingService:
        def embed_memo(self, memo_id, content, metadata):
            return {"memo_id": memo_id, "content": content, "metadata": metadata}

    document = MemoIndexDocument.from_memo("memo-1", "content")

    result = index_memo(FakeEmbeddingService(), document)

    assert result["memo_id"] == "memo-1"
    assert result["content"] == "content"
    assert result["metadata"]["index_version"] == "memo-v1"
