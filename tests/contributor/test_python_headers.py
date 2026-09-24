#!/usr/bin/env python
"""
Filename: tests/contributor/test_python_headers.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Check required header elements in tracked Python source files.
License: LGPL-3.0-or-later
"""

import ast
import subprocess
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).parents[2]
REQUIRED_HEADER_FIELDS = (
    "Filename",
    "Author",
    "Copyright",
    "Description",
    "License",
)


def _tracked_python_files() -> tuple[Path, ...]:
    result = subprocess.run(
        ["git", "ls-files", "--", "*.py"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(
        absolute_path
        for path in result.stdout.splitlines()
        if (absolute_path := REPOSITORY_ROOT / path).is_file()
    )


@pytest.mark.parametrize(
    "path",
    _tracked_python_files(),
    ids=lambda path: str(path.relative_to(REPOSITORY_ROOT)),
)
def test_tracked_python_file_has_required_header_elements(path: Path) -> None:
    """Require the structured, version-free header in each Python file."""
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()

    assert lines and lines[0] == "#!/usr/bin/env python"

    docstring = ast.get_docstring(ast.parse(source), clean=False)
    assert docstring is not None
    docstring_lines = docstring.splitlines()

    header = {}
    for field in REQUIRED_HEADER_FIELDS:
        prefix = f"{field}:"
        values = [
            line.removeprefix(prefix).strip()
            for line in docstring_lines
            if line.startswith(prefix)
        ]
        assert len(values) == 1
        assert values[0]
        header[field] = values[0]

    assert header["Filename"] == str(path.relative_to(REPOSITORY_ROOT))
    assert not any(
        line.strip().startswith("Version:") for line in docstring_lines
    )
