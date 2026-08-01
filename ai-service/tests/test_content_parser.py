from app.domain.models import BugReport, CodeSnippet
from app.services.content_parser import _sections, parse_memo_content


def test_parses_code_snippet_frontmatter_and_fence():
    result = parse_memo_content(
        """---
type: code
title: Docker port helper
language: Python
tags: [Docker, FastAPI]
---
Description: Resolve a container port.

```python
print('hello')
```
"""
    )

    assert result.kind == "code"
    assert isinstance(result.template, CodeSnippet)
    assert result.template.title == "Docker port helper"
    assert result.template.language == "Python"
    assert result.template.code == "print('hello')"
    assert result.template.description == "Resolve a container port."
    assert result.template.tags == ("Docker", "FastAPI")


def test_parses_bug_report_sections():
    result = parse_memo_content(
        """# Type: Bug Report
## Title
FastAPI startup failure
## Environment
Python 3.12 / Ubuntu 22
## Error
ModuleNotFoundError
## Reproduction Steps
1. Start the service
## Root Cause
Dependency was missing
## Solution
Install requirements
"""
    )

    assert result.kind == "bug"
    assert isinstance(result.template, BugReport)
    assert result.template.title == "FastAPI startup failure"
    assert result.template.error == "ModuleNotFoundError"
    assert result.template.solution == "Install requirements"


def test_invalid_code_template_falls_back_to_plain_memo():
    result = parse_memo_content(
        """---
type: code
language: Rust
---
```rust
fn main() {}
```
"""
    )

    assert result.kind == "plain"
    assert result.template is None
    assert "language must be one of" in result.errors[0]


def test_empty_or_unmarked_content_is_plain_memo():
    assert parse_memo_content("").kind == "plain"
    assert parse_memo_content("A normal development note").kind == "plain"


def test_section_parser_handles_long_non_matching_lines_without_regex_backtracking():
    long_line = "A" + " " * 20_000

    assert _sections(long_line) == {}
