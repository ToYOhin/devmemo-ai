"""Deterministic Markdown report generation for the project-summary demo."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Protocol


PROJECT_SUMMARY = "project_summary"
ALLOWED_DEMO_TASKS = frozenset({PROJECT_SUMMARY})
MAX_REPORT_SOURCE_CHARS = 1200
PROVIDER_REPORT_VERSION = "agent-run-project-summary-v1"
MAX_PROVIDER_SUMMARY_CHARS = 1200
MAX_PROVIDER_BULLET_CHARS = 600
MAX_PROVIDER_LIMITATIONS = 3


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
    provider: str = "deterministic"
    fallback_reason: str | None = None


class ReportProviderResult(Protocol):
    @property
    def text(self) -> str: ...


class ReportProvider(Protocol):
    @property
    def name(self) -> str: ...

    async def generate(self, prompt: str) -> ReportProviderResult: ...


def build_markdown_report(task_kind: str, sources: tuple[ReportSource, ...]) -> MarkdownReport:
    if task_kind != PROJECT_SUMMARY or not 1 <= len(sources) <= 10:
        raise AgentRunReportError("invalid AgentRun report request")
    if any(not item.content.strip() for item in sources):
        raise AgentRunReportError("invalid AgentRun report request")
    return MarkdownReport("project-summary.md", _project_summary(sources))


async def build_agent_run_report(
    task_kind: str,
    sources: tuple[ReportSource, ...],
    provider: ReportProvider | None,
) -> MarkdownReport:
    deterministic = build_markdown_report(task_kind, sources)
    try:
        if provider is None or provider.name == "deterministic":
            return deterministic
        aliases = tuple(f"source-{index}" for index in range(1, len(sources) + 1))
        result = await provider.generate(_provider_prompt(task_kind, sources, aliases))
        return _provider_report(sources, aliases, provider.name, result)
    except Exception as error:
        return MarkdownReport(
            deterministic.file_name,
            _fallback_markdown(deterministic.markdown, _fallback_reason(error)),
            provider="deterministic",
            fallback_reason=_fallback_reason(error),
        )


def _provider_prompt(
    task_kind: str,
    sources: tuple[ReportSource, ...],
    aliases: tuple[str, ...],
) -> str:
    source_text = "\n\n".join(
        f"[{alias}]\n{source.content[:MAX_REPORT_SOURCE_CHARS]}" for alias, source in zip(aliases, sources, strict=True)
    )
    return (
        "Use only the supplied authorized Memo sources. Return one JSON object only, "
        "with exactly these fields: version, summary, bullets, limitations, citation_refs. "
        f'Set version to "{PROVIDER_REPORT_VERSION}". summary must be a non-empty string; '
        "bullets must be exactly three non-empty strings; limitations must contain one to "
        "three non-empty strings; citation_refs must exactly equal the supplied source aliases "
        "in order. Do not claim production deployment, real-user acceptance, unsupported "
        "metrics, or capabilities absent from the sources. Keep each bullet concise. Write in "
        "the primary language used by the supplied sources. "
        f"Task kind: {task_kind}. Required citation_refs: {json.dumps(aliases)}.\n\n"
        f"Sources:\n{source_text}"
    )


def _provider_report(
    sources: tuple[ReportSource, ...],
    aliases: tuple[str, ...],
    provider_name: str,
    result: ReportProviderResult,
) -> MarkdownReport:
    try:
        payload = json.loads(result.text)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise AgentRunReportError("invalid AgentRun provider report") from error
    if not isinstance(payload, dict) or set(payload) != {
        "version",
        "summary",
        "bullets",
        "limitations",
        "citation_refs",
    }:
        raise AgentRunReportError("invalid AgentRun provider report")
    bullets = payload["bullets"]
    limitations = payload["limitations"]
    if (
        payload["version"] != PROVIDER_REPORT_VERSION
        or not isinstance(bullets, list)
        or len(bullets) != 3
        or not isinstance(limitations, list)
        or not 1 <= len(limitations) <= MAX_PROVIDER_LIMITATIONS
        or payload["citation_refs"] != list(aliases)
    ):
        raise AgentRunReportError("invalid AgentRun provider report")
    summary = _bounded_plain_text(payload["summary"], MAX_PROVIDER_SUMMARY_CHARS)
    safe_bullets = tuple(_bounded_plain_text(item, MAX_PROVIDER_BULLET_CHARS) for item in bullets)
    safe_limitations = tuple(_bounded_plain_text(item, MAX_PROVIDER_BULLET_CHARS) for item in limitations)
    safe_provider = re.sub(r"[^A-Za-z0-9._-]", "", provider_name)[:32] or "external"
    markdown = "\n".join(
        (
            "# Project summary",
            "",
            f"> {safe_provider} draft generated from authorized Memo evidence; review before use.",
            "",
            summary,
            "",
            "## Key points",
            "",
            *(f"- {item}" for item in safe_bullets),
            "",
            "## Limitations",
            "",
            *(f"- {item}" for item in safe_limitations),
            "",
            "## Evidence",
            "",
            *(
                f"- `{alias}`: `{source.source_id}` at `{source.revision}`"
                for alias, source in zip(aliases, sources, strict=True)
            ),
            "",
        )
    )
    return MarkdownReport("project-summary.md", markdown, provider=safe_provider)


def _bounded_plain_text(value: object, max_chars: int) -> str:
    if not isinstance(value, str):
        raise AgentRunReportError("invalid AgentRun provider report")
    normalized = re.sub(r"\s+", " ", value).strip()
    if not normalized or len(normalized) > max_chars:
        raise AgentRunReportError("invalid AgentRun provider report")
    return re.sub(r"([\\`*_{}\[\]()<>#+|])", r"\\\1", normalized)


def _fallback_reason(error: Exception) -> str:
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, TimeoutError):
            return "provider_timeout"
        current = current.__cause__
    if isinstance(error, AgentRunReportError):
        return "invalid_provider_output"
    return "provider_unavailable"


def _fallback_markdown(markdown: str, reason: str) -> str:
    marker = f"> External Provider did not complete safely (`{reason}`); this artifact uses the deterministic fallback."
    lines = markdown.splitlines()
    lines[2:3] = [lines[2], "", marker]
    return "\n".join(lines).rstrip() + "\n"


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
