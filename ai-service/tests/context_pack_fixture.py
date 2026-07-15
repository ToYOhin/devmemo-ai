import json
from pathlib import Path

from app.domain.context_pack import ContextPackMemo
from app.domain.memo_insight import MemoInsight


def context_pack_inputs():
    fixture_path = Path(__file__).resolve().parents[2] / "contracts" / "context-pack-v1.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    memos = {memo_id: ContextPackMemo(**memo) for memo_id, memo in fixture["memos"].items()}
    insights = {
        insight_id: MemoInsight(**{**insight, "source_refs": tuple(insight["source_refs"])})
        for insight_id, insight in fixture["insights"].items()
    }
    return memos, insights
