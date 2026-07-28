from dataclasses import replace

import pytest

from app.domain.memo_chunking import (
    CHUNK_INDEX_MODE,
    CHUNK_INDEX_VERSION,
    MemoChunk,
    chunk_ids_for_memo,
    chunk_memo,
    ensure_unique_chunk_ids,
)


def test_chunk_memo_preserves_markdown_and_emits_versioned_metadata():
    content = "# Docker\n\n端口映射需要同时检查 compose 和宿主机。\n"

    chunks = chunk_memo("memo-docker", content, max_chars=18)

    assert chunks
    assert "".join(chunk.content for chunk in chunks) == content
    assert all(len(chunk.content) <= 18 for chunk in chunks)
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.index_version == CHUNK_INDEX_VERSION for chunk in chunks)
    assert all(chunk.index_mode == CHUNK_INDEX_MODE for chunk in chunks)
    assert all(chunk.metadata["source_type"] == "memo_chunk" for chunk in chunks)
    assert all(chunk.metadata["content"] == chunk.content for chunk in chunks)


def test_chunk_ids_are_stable_for_same_memo_version_and_position():
    first = chunk_memo("memo-1", "alpha\nbeta\ngamma", max_chars=6)
    second = chunk_memo("memo-1", "alpha\nbeta\ngamma", max_chars=6)

    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert all(chunk.chunk_id.startswith(f"{CHUNK_INDEX_VERSION}:") for chunk in first)


def test_chunk_ids_separate_memos_and_index_versions():
    memo_ids = chunk_ids_for_memo("memo-1", 2)
    other_memo_ids = chunk_ids_for_memo("memo-2", 2)
    other_version_ids = chunk_ids_for_memo("memo-1", 2, index_version="memo-chunk-v2")

    assert memo_ids == [chunk_memo("memo-1", "123456789", max_chars=5)[i].chunk_id for i in range(2)]
    assert set(memo_ids).isdisjoint(other_memo_ids)
    assert set(memo_ids).isdisjoint(other_version_ids)


def test_chunk_memo_hard_splits_long_markdown_line():
    content = "x" * 25

    chunks = chunk_memo("memo-long", content, max_chars=10)

    assert [chunk.content for chunk in chunks] == ["x" * 10, "x" * 10, "x" * 5]


def test_empty_or_whitespace_memo_produces_no_chunks():
    assert chunk_memo("memo-empty", "") == ()
    assert chunk_memo("memo-empty", " \n\t ") == ()
    assert chunk_ids_for_memo("memo-empty", 0) == []


def test_update_keeps_position_ids_and_refreshes_chunk_content():
    old_chunks = chunk_memo("memo-1", "alpha\nbeta", max_chars=6)
    new_chunks = chunk_memo("memo-1", "alpha\nBETA", max_chars=6)

    assert [chunk.chunk_id for chunk in old_chunks] == [chunk.chunk_id for chunk in new_chunks]
    assert [chunk.content for chunk in new_chunks] == ["alpha\n", "BETA"]
    assert chunk_ids_for_memo("memo-1", len(old_chunks)) == [chunk.chunk_id for chunk in old_chunks]


def test_shorter_update_exposes_stale_ids_for_explicit_delete():
    old_chunks = chunk_memo("memo-1", "abcdefghij", max_chars=4)
    new_chunks = chunk_memo("memo-1", "abcd", max_chars=4)

    old_ids = {chunk.chunk_id for chunk in old_chunks}
    new_ids = {chunk.chunk_id for chunk in new_chunks}

    all_old_ids = chunk_ids_for_memo("memo-1", len(old_chunks))
    assert old_ids - new_ids == set(all_old_ids[len(new_chunks) :])


def test_duplicate_chunk_ids_are_rejected_before_future_upsert():
    chunks = chunk_memo("memo-1", "abcdefgh", max_chars=4)
    duplicated = (chunks[0], replace(chunks[1], chunk_id=chunks[0].chunk_id))

    with pytest.raises(ValueError, match="duplicate chunk_id"):
        ensure_unique_chunk_ids(duplicated)


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda: chunk_memo(" ", "content"), "memo_id"),
        (lambda: chunk_memo("memo", "content", max_chars=0), "max_chars"),
        (lambda: chunk_memo("memo", "content", index_version=" "), "index_version"),
        (lambda: chunk_ids_for_memo("memo", -1), "chunk_count"),
    ],
)
def test_chunking_rejects_invalid_boundary_inputs(call, message):
    with pytest.raises(ValueError, match=message):
        call()


def test_memo_chunk_is_provider_neutral_and_does_not_mutate_source_metadata():
    source_metadata = {"title": "Docker", "tags": ["docker"]}
    chunks = chunk_memo("memo-1", "content", metadata=source_metadata)

    assert source_metadata == {"title": "Docker", "tags": ["docker"]}
    assert chunks[0].metadata["title"] == "Docker"
    assert chunks[0].metadata["tags"] == ["docker"]
    assert isinstance(chunks[0], MemoChunk)
