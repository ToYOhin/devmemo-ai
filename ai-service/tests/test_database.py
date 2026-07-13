import sqlite3

from database import get_ai_note, get_memo_template, save_ai_note, save_memo_template


def test_ai_note_create_and_read(monkeypatch, tmp_path):
    database = tmp_path / "notes.db"
    monkeypatch.setenv("AI_NOTES_DB", str(database))

    saved = save_ai_note(
        "memo-1",
        "Docker 端口映射问题分析",
        ["Docker", "FastAPI"],
        "DevOps",
        suggested_tags=["docker", "network"],
        provider="deterministic",
    )

    note = get_ai_note("memo-1")
    assert note is not None
    assert note["id"] == saved["id"]
    assert note["summary"] == "Docker 端口映射问题分析"
    assert note["keywords"] == ["Docker", "FastAPI"]
    assert note["category"] == "DevOps"
    assert note["suggested_tags"] == ["docker", "network"]
    assert note["provider"] == "deterministic"
    assert note["created_at"] == saved["created_at"]


def test_missing_ai_note_returns_none(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "missing.db"))

    assert get_ai_note("missing") is None


def test_template_upsert_is_idempotent(monkeypatch, tmp_path):
    database = tmp_path / "templates.db"
    monkeypatch.setenv("AI_NOTES_DB", str(database))

    first = save_memo_template(
        "memo-1",
        "code",
        {"title": "First", "language": "Python", "code": "print(1)"},
        "raw v1",
    )
    second = save_memo_template(
        "memo-1",
        "code",
        {"title": "Updated", "language": "Python", "code": "print(2)"},
        "raw v2",
    )

    assert second["id"] == first["id"]
    assert get_memo_template("memo-1")["payload"]["title"] == "Updated"
    assert get_memo_template("memo-1")["raw_content"] == "raw v2"
    with sqlite3.connect(database) as connection:
        count = connection.execute("SELECT COUNT(*) FROM memo_templates").fetchone()[0]
    assert count == 1


def test_missing_template_returns_none(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_NOTES_DB", str(tmp_path / "missing.db"))

    assert get_memo_template("missing") is None
