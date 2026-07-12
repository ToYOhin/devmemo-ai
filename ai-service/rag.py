"""RAG service boundary reserved for the Qdrant phase."""

from __future__ import annotations


def build_context(memos: list[dict[str, str]]) -> str:
    """Format retrieved memos into a prompt-ready context block."""

    return "\n\n".join(
        f"[{memo.get('title', 'Memo')}]\n{memo.get('content', '')}" for memo in memos
    )
