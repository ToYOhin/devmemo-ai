import pytest

from app.domain.retrieval import Citation, RetrievalResult
from app.domain.retrieval_evaluation import RetrievalEvaluationCase
from app.adapters.embedding import DeterministicEmbeddingProvider
from app.adapters.vector_store import InMemoryVectorStore
from app.services.embedding_service import EmbeddingService
from app.services.memo_indexing import MemoIndexDocument, index_memo
from app.services.retrieval_evaluator import RetrievalEvaluator
from app.services.retrieval_service import RetrievalService


class FakeRetrievalService:
    MAX_LIMIT = 10

    def __init__(self, memo_ids: tuple[str, ...]):
        self.memo_ids = memo_ids

    def retrieve(self, question: str, limit: int = 5) -> RetrievalResult:
        return RetrievalResult(
            context=f"context for {question}",
            citations=tuple(
                Citation(
                    memo_id=memo_id,
                    embedding_id=f"embedding-{memo_id}",
                    score=1.0 - index / 10,
                    metadata={},
                )
                for index, memo_id in enumerate(self.memo_ids[:limit])
            ),
        )


def test_evaluator_reports_recall_and_first_relevant_rank():
    evaluator = RetrievalEvaluator(FakeRetrievalService(("memo-noise", "memo-docker")))

    result = evaluator.evaluate_case(
        RetrievalEvaluationCase("docker-1", "Docker port issue", ("memo-docker",), limit=2)
    )

    assert result.case_id == "docker-1"
    assert result.retrieved_memo_ids == ("memo-noise", "memo-docker")
    assert result.relevant_memo_ids == ("memo-docker",)
    assert result.recall_at_k == 1.0
    assert result.first_relevant_rank == 2


def test_evaluator_runs_multiple_cases_without_network_or_provider_sdk():
    evaluator = RetrievalEvaluator(FakeRetrievalService(("memo-docker", "memo-fastapi")))

    results = evaluator.evaluate(
        [
            RetrievalEvaluationCase("docker", "Docker", ("memo-docker",)),
            RetrievalEvaluationCase("fastapi", "FastAPI", ("memo-fastapi",)),
        ]
    )

    assert [result.case_id for result in results] == ["docker", "fastapi"]
    assert [result.recall_at_k for result in results] == [1.0, 1.0]


def test_evaluator_uses_existing_deterministic_retrieval_contract():
    embedding_service = EmbeddingService(
        DeterministicEmbeddingProvider(), InMemoryVectorStore(8)
    )
    index_memo(
        embedding_service,
        MemoIndexDocument.from_memo("memo-docker", "Docker port mapping", {"title": "Docker"}),
    )

    result = RetrievalEvaluator(RetrievalService(embedding_service)).evaluate_case(
        RetrievalEvaluationCase("docker", "Docker port", ("memo-docker",))
    )

    assert result.recall_at_k == 1.0
    assert result.first_relevant_rank == 1


@pytest.mark.parametrize(
    ("case", "message"),
    [
        (RetrievalEvaluationCase("", "question", ("memo",)), "case_id"),
        (RetrievalEvaluationCase("case", " ", ("memo",)), "question"),
        (RetrievalEvaluationCase("case", "question", ()), "expected_memo_ids"),
        (RetrievalEvaluationCase("case", "question", ("memo", "memo")), "unique"),
        (RetrievalEvaluationCase("case", "question", ("memo",), limit=11), "between 1 and 10"),
    ],
)
def test_evaluator_rejects_invalid_cases(case, message):
    with pytest.raises(ValueError, match=message):
        RetrievalEvaluator(FakeRetrievalService(("memo",))).evaluate_case(case)
