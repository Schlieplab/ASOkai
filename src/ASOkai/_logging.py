#!/usr/bin/env python
"""
Filename: src/ASOkai/_logging.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Shared context formatting for user-facing ASOkai logs.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from collections.abc import Generator, Sequence
from contextlib import contextmanager


_active_contexts: tuple[str, ...] = ()


def active_log_contexts() -> tuple[str, ...]:
    """Return the contexts applied to logs in the current CLI operation."""
    return _active_contexts


@contextmanager
def log_context(*contexts: str) -> Generator[None, None, None]:
    """Apply typed contexts to logs emitted inside one synchronous operation."""
    global _active_contexts

    previous = _active_contexts
    _active_contexts = tuple(contexts)
    try:
        yield
    finally:
        _active_contexts = previous


def prefix_log_lines(contexts: Sequence[str], message: str) -> str:
    """Prefix every non-empty physical line with the supplied contexts."""
    if not contexts:
        return message
    prefix = "".join(f"[{context}]" for context in contexts)
    return "\n".join(
        f"{prefix} {line}" if line else ""
        for line in message.split("\n")
    )
