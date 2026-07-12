"""Structured Memo models used by the template parser."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


SUPPORTED_LANGUAGES = (
    "Python",
    "Go",
    "JavaScript",
    "TypeScript",
    "C++",
    "SQL",
)


@dataclass(frozen=True)
class CodeSnippet:
    title: str
    language: str
    code: str
    description: str = ""
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class BugReport:
    title: str
    environment: str = ""
    error: str = ""
    reproduction_steps: str = ""
    root_cause: str = ""
    solution: str = ""
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParsedMemo:
    kind: Literal["plain", "code", "bug"]
    template: CodeSnippet | BugReport | None = None
    errors: tuple[str, ...] = ()
