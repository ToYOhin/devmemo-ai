"""Deterministic Markdown report generation for the project-summary demo."""

from __future__ import annotations

from dataclasses import dataclass
import re


PROJECT_SUMMARY = "project_summary"
ALLOWED_DEMO_TASKS = frozenset({PROJECT_SUMMARY})
MAX_REPORT_SOURCE_CHARS = 1200


class AgentRunReportError(ValueError):
    """Raised when a deterministic report request is outside the demo contract."""


@dataclass(frozen=True)
class ReportSource:
    source_id: str
    revision: str
    content: str


@dataclass(frozen=True)
class MarkdownReport:
    file_name: str
    markdown: str


def build_markdown_report(task_kind: str, sources: tuple[ReportSource, ...]) -> MarkdownReport:
    if task_kind != PROJECT_SUMMARY or not 1 <= len(sources) <= 10:
        raise AgentRunReportError("invalid AgentRun report request")
    if any(not item.content.strip() for item in sources):
        raise AgentRunReportError("invalid AgentRun report request")
    return MarkdownReport("project-summary.md", _project_summary(sources))


def _project_summary(sources: tuple[ReportSource, ...]) -> str:
    sections = [
        "# Project summary",
        "",
        f"> Deterministic draft generated from {len(sources)} authorized Memo source(s).",
    ]
    for index, source in enumerate(sources, start=1):
        lines = _meaningful_lines(source.content)
        title = lines[0][:80] if lines else f"Memo {index}"
        body = "\n".join(lines[1:] or lines[:1])[:MAX_REPORT_SOURCE_CHARS]
        sections.extend(("", f"## {index}. {title}", "", body))
    sections.extend(("", "## Evidence", ""))
    sections.extend(f"- `{item.source_id}` at `{item.revision}`" for item in sources)
    return "\n".join(sections).rstrip() + "\n"


def _meaningful_lines(content: str) -> list[str]:
    lines: list[str] = []
    for raw in content.splitlines():
        normalized = re.sub(r"^[\s#>*+-]+", "", raw).strip()
        normalized = re.sub(r"\s+", " ", normalized)
        if normalized:
            lines.append(normalized[:MAX_REPORT_SOURCE_CHARS])
    return lines
