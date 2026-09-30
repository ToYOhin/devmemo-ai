from dataclasses import dataclass
import json

import pytest

from app.services.agent_run_report import (
    AgentRunReportError,
    PROVIDER_REPORT_VERSION,
    ReportSource,
    build_agent_run_report,
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


@dataclass(frozen=True)
class _Result:
    text: str


class _Provider:
    name = "openai"

    def __init__(self, response: str | Exception) -> None:
        self._response = response

    async def generate(self, _prompt: str) -> _Result:
        if isinstance(self._response, Exception):
            raise self._response
        return _Result(self._response)


@pytest.mark.asyncio
async def test_provider_report_is_strictly_validated_and_server_rendered() -> None:
    response = json.dumps(
        {
            "version": PROVIDER_REPORT_VERSION,
            "summary": "Implemented a bounded AgentRun product path with <script> and [link](bad).",
            "bullets": ["Authenticated BFF", "Bounded runtime", "Evidence artifact"],
            "limitations": ["No production acceptance claim"],
            "citation_refs": ["source-1"],
        }
    )

    report = await build_agent_run_report("project_summary", SOURCES, _Provider(response))

    assert report.provider == "openai"
    assert report.fallback_reason is None
    assert "Authenticated BFF" in report.markdown
    assert r"\<script\>" in report.markdown
    assert r"\[link\]\(bad\)" in report.markdown
    assert "<script>" not in report.markdown
    assert "`source-1`: `memo-616263` at `rev-1700000000`" in report.markdown
    assert response not in report.markdown


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "reason"),
    [
        ('{"summary":"missing contract"}', "invalid_provider_output"),
        (TimeoutError("synthetic timeout"), "provider_timeout"),
        (RuntimeError("synthetic upstream failure"), "provider_unavailable"),
    ],
)
async def test_provider_failure_uses_explicit_deterministic_fallback(response, reason) -> None:
    report = await build_agent_run_report("project_summary", SOURCES, _Provider(response))

    assert report.provider == "deterministic"
    assert report.fallback_reason == reason
    assert f"`{reason}`" in report.markdown
    assert "deterministic fallback" in report.markdown
    assert "synthetic upstream failure" not in report.markdown
