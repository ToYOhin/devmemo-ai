import pytest

from app.services.agent_run_report import (
    AgentRunReportError,
    ReportSource,
    build_markdown_report,
)


SOURCES = (
    ReportSource(
        source_id="memo-616263",
        revision="rev-1700000000",
        content="# DevMemo AI\nBuilt an authenticated AgentRun BFF.\nAdded bounded persistence.",
    ),
)


def test_project_summary_is_deterministic_and_evidence_bound() -> None:
    report = build_markdown_report("project_summary", SOURCES)

    assert report.file_name == "project-summary.md"
    assert "# Project summary" in report.markdown
    assert "Built an authenticated AgentRun BFF." in report.markdown
    assert "`memo-616263` at `rev-1700000000`" in report.markdown


def test_report_rejects_unknown_task_or_empty_content() -> None:
    with pytest.raises(AgentRunReportError):
        build_markdown_report("free_form", SOURCES)
    with pytest.raises(AgentRunReportError):
        build_markdown_report(
            "project_summary",
            (ReportSource("memo-616263", "rev-1700000000", "  "),),
        )
