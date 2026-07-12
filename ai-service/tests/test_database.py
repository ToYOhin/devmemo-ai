import sqlite3

from database import get_memo_template, save_memo_template


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
