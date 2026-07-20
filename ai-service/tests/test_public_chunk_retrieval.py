import json
from pathlib import Path

from app.domain.retrieval import ChunkCitation
from app.services.public_chunk_retrieval import build_public_chunk_response


def _fixture():
    path = Path(__file__).resolve().parents[2] / "contracts" / "public-chunk-v1.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_public_chunk_response_deduplicates_authorizes_sorts_and_redacts():
    fixture = _fixture()
    response = build_public_chunk_response(
        citations=(
            ChunkCitation(
                memo_id="memo-a",
                chunk_id="memo-chunk-v1:a:0000",
                chunk_index=0,
                index_version="memo-chunk-v1",
                score=0.91,
                metadata={"title": "Docker ports", "content": "private first chunk", "payload": "private"},
            ),
            ChunkCitation(
                memo_id="memo-a",
                chunk_id="memo-chunk-v1:a:0001",
                chunk_index=1,
                index_version="memo-chunk-v1",
                score=0.92,
                metadata={"title": "Docker ports", "content": "private best chunk", "secret": "private"},
            ),
            ChunkCitation(
                memo_id="memo-b",
                chunk_id="memo-chunk-v1:b:0000",
                chunk_index=0,
                index_version="memo-chunk-v1",
                score=0.8,
                metadata={"title": "Proxy setup", "content": "private second memo"},
            ),
            ChunkCitation(
                memo_id="memo-hidden",
                chunk_id="memo-chunk-v1:hidden:0000",
                chunk_index=0,
                index_version="memo-chunk-v1",
                score=0.99,
                metadata={"title": "Hidden", "content": "must not be returned"},
            ),
        ),
        provider="deterministic",
        visible_memo_ids=frozenset(fixture["request"]["visible_memo_ids"]),
        limit=fixture["request"]["limit"],
    )

    assert response.to_dict() == fixture["response"]
    assert "private" not in json.dumps(response.to_dict())
    assert "memo-hidden" not in json.dumps(response.to_dict())
