import hashlib

import pytest

from app.adapters.agent_run_artifact_store import (
    AgentRunArtifactStoreError,
    SQLiteAgentRunArtifactStore,
    StoredMarkdownArtifact,
)


def _artifact(markdown: str = "# Project summary\n") -> StoredMarkdownArtifact:
    return StoredMarkdownArtifact(
        artifact_id="artifact-demo-001",
        run_id="run-demo-001",
        storage_ref="storage-demo-001",
        file_name="project-summary.md",
        markdown=markdown,
        digest=hashlib.sha256(markdown.encode()).hexdigest(),
    )


def test_markdown_artifact_store_round_trips_idempotently(tmp_path) -> None:
    store = SQLiteAgentRunArtifactStore(tmp_path / "agent-runs.db")
    artifact = _artifact()

    store.put(artifact)
    store.put(artifact)

    assert store.get(artifact.storage_ref) == artifact


def test_markdown_artifact_store_rejects_conflicting_replay(tmp_path) -> None:
    store = SQLiteAgentRunArtifactStore(tmp_path / "agent-runs.db")
    store.put(_artifact())

    with pytest.raises(AgentRunArtifactStoreError, match="conflicts"):
        store.put(_artifact("# Different\n"))
