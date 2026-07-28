from database import (
    save_ai_note,
    save_chunk_index_state,
    save_memo_insights,
    save_memo_template,
    save_webhook_event,
    update_memo_insight_status,
)
from lifecycle_report import build_devmemory_lifecycle_report


def test_lifecycle_report_handles_a_missing_database(tmp_path):
    report = build_devmemory_lifecycle_report(tmp_path / "missing.db")

    assert report["database_exists"] is False
    assert report["derived_records"]["memo_insights"] == 0
    assert report["insights"]["by_status"] == {}


def test_lifecycle_report_aggregates_derived_state_without_writing(monkeypatch, tmp_path):
    database = tmp_path / "ai_notes.db"
    monkeypatch.setenv("AI_NOTES_DB", str(database))
    save_ai_note("memo-1", "Safe summary", ["port"], "Development")
    save_memo_template("memo-1", "bug", {"title": "Port mapping"}, "raw memo content")
    saved = save_memo_insights(
        [
            {
                "insight_id": "insight-accepted",
                "memo_id": "memo-1",
                "insight_type": "bug",
                "title": "Port mapping",
                "summary": "Use the correct host port.",
                "confidence": 0.9,
                "source_refs": ["template.root_cause"],
            },
            {
                "insight_id": "insight-rejected",
                "memo_id": "memo-2",
                "insight_type": "action",
                "title": "Add a smoke check",
                "summary": "Verify the port mapping before release.",
                "confidence": 0.8,
                "source_refs": ["template.solution"],
            },
        ]
    )
    update_memo_insight_status("insight-accepted", saved[0]["version"], "accepted")
    update_memo_insight_status("insight-rejected", saved[1]["version"], "rejected")
    save_chunk_index_state("memo-1", "memo-chunk-v1", ("chunk-1",))
    save_webhook_event("event-1", "memo.updated", {"content": "must remain private"})
    modified_before = database.stat().st_mtime_ns

    report = build_devmemory_lifecycle_report(database)

    assert database.stat().st_mtime_ns == modified_before
    assert report["database_exists"] is True
    assert report["derived_records"] == {
        "ai_notes": 1,
        "memo_templates": 1,
        "memo_insights": 2,
        "memo_chunk_index_state": 1,
    }
    assert report["insights"] == {
        "by_status": {"accepted": 1, "rejected": 1},
        "version_range": {"min": 2, "max": 2},
    }
    assert report["webhook_events"]["by_status"] == {"pending": 1}
    assert "raw memo content" not in str(report)
    assert "must remain private" not in str(report)
