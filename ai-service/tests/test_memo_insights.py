from app.services.memo_insights import derive_memo_insights


def test_code_memo_derives_reviewable_fact_and_action():
    insights = derive_memo_insights(
        "memo-code",
        "Port helper",
        "---\ntype: code\nlanguage: Python\ntitle: Port helper\n---\n## Description\nReview before merge.\n```python\nprint(8080)\n```",
    )

    assert [item.insight_type for item in insights] == ["fact", "action"]
    assert insights[0].source_refs == ("template.title", "template.language", "template.code")
    assert all(item.status == "pending" for item in insights)
    assert all(0 < item.confidence <= 1 for item in insights)


def test_bug_memo_derives_problem_and_solution_action():
    insights = derive_memo_insights(
        "memo-bug",
        "",
        "---\ntype: bug\ntitle: Port failure\n---\nError: connection refused\nRoot cause: wrong port\nSolution: fix mapping",
    )

    assert [item.insight_type for item in insights] == ["bug", "action"]
    assert insights[0].summary == "wrong port"
    assert insights[1].summary == "fix mapping"


def test_plain_memo_only_derives_bounded_fact():
    insights = derive_memo_insights("memo-plain", "Docker note", "Docker port mapping needs review.")

    assert len(insights) == 1
    assert insights[0].insight_type == "fact"
    assert insights[0].summary == "Docker port mapping needs review"
