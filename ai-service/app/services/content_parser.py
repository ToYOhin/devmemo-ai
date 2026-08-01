"""Parse opt-in developer Memo templates without blocking ordinary Memos."""

from __future__ import annotations

import json
import re

from app.domain.models import BugReport, CodeSnippet, ParsedMemo, SUPPORTED_LANGUAGES

_FENCE_PATTERN = re.compile(r"```([^\n`]*)\n(.*?)```", re.DOTALL)
_TYPE_PATTERN = re.compile(
    r"(?:memo[_ -]?type|type)\s*[:=]\s*(code(?:\s*snippet)?|bug(?:\s*report)?)",
    re.IGNORECASE,
)
_LANGUAGE_ALIASES = {
    "py": "Python",
    "python": "Python",
    "go": "Go",
    "golang": "Go",
    "js": "JavaScript",
    "javascript": "JavaScript",
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "c++": "C++",
    "cpp": "C++",
    "sql": "SQL",
}


def parse_memo_content(content: str) -> ParsedMemo:
    """Return a structured template only when the Memo opts in explicitly."""

    if not content.strip():
        return ParsedMemo(kind="plain")

    metadata, body = _parse_frontmatter(content)
    memo_type = _detect_type(metadata, body)
    if memo_type == "code":
        return _parse_code_snippet(metadata, body)
    if memo_type == "bug":
        return _parse_bug_report(metadata, body)
    return ParsedMemo(kind="plain")


def _parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, content
    try:
        end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration:
        return {}, content

    metadata: dict[str, str] = {}
    for line in lines[1:end]:
        key, separator, value = line.partition(":")
        if separator:
            metadata[key.strip().lower()] = value.strip().strip("'\"")
    return metadata, "\n".join(lines[end + 1 :])


def _detect_type(metadata: dict[str, str], body: str) -> str | None:
    raw_type = metadata.get("type") or metadata.get("memo_type")
    if not raw_type:
        match = _TYPE_PATTERN.search("\n".join(body.splitlines()[:12]))
        raw_type = match.group(1) if match else ""
    normalized = raw_type.lower().replace("_", " ").strip()
    if normalized.startswith("code"):
        return "code"
    if normalized.startswith("bug"):
        return "bug"
    return None


def _parse_code_snippet(metadata: dict[str, str], body: str) -> ParsedMemo:
    sections = _sections(body)
    fence = _FENCE_PATTERN.search(body)
    fenced_language = fence.group(1).strip() if fence else ""
    code = _value(metadata, sections, "code")
    if not code and fence:
        code = fence.group(2).rstrip()
    language = _canonical_language(_value(metadata, sections, "language") or fenced_language)
    errors: list[str] = []
    if not language:
        errors.append("language must be one of: " + ", ".join(SUPPORTED_LANGUAGES))
    if not code.strip():
        errors.append("code is required for a Code Snippet")
    if errors:
        return ParsedMemo(kind="plain", errors=tuple(errors))
    snippet = CodeSnippet(
        title=_value(metadata, sections, "title") or "Untitled Code Snippet",
        language=language,
        code=code,
        description=_value(metadata, sections, "description"),
        tags=_tags(metadata.get("tags", "")),
    )
    return ParsedMemo(kind="code", template=snippet)


def _parse_bug_report(metadata: dict[str, str], body: str) -> ParsedMemo:
    sections = _sections(body)
    report = BugReport(
        title=_value(metadata, sections, "title") or "Untitled Bug Report",
        environment=_value(metadata, sections, "environment"),
        error=_value(metadata, sections, "error"),
        reproduction_steps=_value(metadata, sections, "reproduction_steps", "reproduction steps"),
        root_cause=_value(metadata, sections, "root_cause", "root cause", "cause"),
        solution=_value(metadata, sections, "solution", "fix"),
        tags=_tags(metadata.get("tags", "")),
    )
    return ParsedMemo(kind="bug", template=report)


def _sections(body: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in body.splitlines():
        heading = _heading_value(line)
        if heading is not None:
            current = _normalize_key(heading)
            sections.setdefault(current, [])
        else:
            inline = _inline_field(line)
            if inline and not current:
                sections[_normalize_key(inline[0])] = [inline[1]]
                continue
        if current and heading is None:
            sections[current].append(line)
    return {key: "\n".join(value).strip() for key, value in sections.items()}


def _heading_value(line: str) -> str | None:
    """Parse an ATX heading without a backtracking regular expression."""
    indent = len(line) - len(line.lstrip(" \t"))
    if indent > 3:
        return None
    candidate = line[indent:]
    marker_count = len(candidate) - len(candidate.lstrip("#"))
    if not 1 <= marker_count <= 6 or len(candidate) == marker_count:
        return None
    if not candidate[marker_count].isspace():
        return None
    value = candidate[marker_count:].strip()
    return value or None


def _inline_field(line: str) -> tuple[str, str] | None:
    """Parse a simple field line without regex work proportional to backtracking."""
    candidate = line.strip()
    key, separator, value = candidate.partition(":")
    if not separator or not key or not key[0].isalpha():
        return None
    if not all(character.isalpha() or character in " _-" for character in key):
        return None
    return key, value.strip()


def _value(metadata: dict[str, str], sections: dict[str, str], *keys: str) -> str:
    for key in keys:
        normalized = _normalize_key(key)
        if metadata.get(normalized):
            return metadata[normalized]
        if sections.get(normalized):
            return sections[normalized]
    return ""


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _canonical_language(value: str) -> str:
    return _LANGUAGE_ALIASES.get(value.lower().strip(), "")


def _tags(value: str) -> tuple[str, ...]:
    if not value.strip():
        return ()
    normalized = value.strip()
    try:
        parsed = json.loads(normalized) if normalized.startswith("[") else None
    except json.JSONDecodeError:
        parsed = None
    if not isinstance(parsed, list) and normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]
    values = parsed if isinstance(parsed, list) else normalized.split(",")
    return tuple(str(tag).strip() for tag in values if str(tag).strip())
