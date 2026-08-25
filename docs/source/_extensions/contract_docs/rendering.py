#!/usr/bin/env python
"""
Filename: docs/source/_extensions/contract_docs/rendering.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Docutils helpers shared by ASOkai's generated references.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
import inspect
from pathlib import Path
from typing import Any

from docutils import nodes
from sphinx import addnodes

TableCell = tuple[str, bool] | nodes.Node
DetailValue = str | nodes.Node


def note_reference_dependencies(
    environment: Any,
    documented_objects: Iterable[object] = (),
    *,
    paths: Iterable[str | Path] = (),
) -> None:
    """Make Sphinx rebuild generated references when their sources change."""
    dependency_paths = set(Path(__file__).parent.glob("*.py"))
    dependency_paths.update(Path(path) for path in paths)
    for documented_object in documented_objects:
        source_object = (
            documented_object
            if inspect.isclass(documented_object)
            or inspect.ismodule(documented_object)
            or inspect.isfunction(documented_object)
            else type(documented_object)
        )
        source_path = inspect.getsourcefile(source_object)
        if source_path is not None:
            dependency_paths.add(Path(source_path))

    for dependency_path in sorted(dependency_paths):
        environment.note_dependency(str(dependency_path))


def document_link(
    target: str,
    label: str,
    *,
    refdoc: str,
) -> addnodes.pending_xref:
    """Return a Sphinx document link that warns when its target is missing."""
    link = addnodes.pending_xref(
        "",
        refdoc=refdoc,
        refdomain="std",
        reftype="doc",
        reftarget=f"/{target}",
        refexplicit=True,
        refwarn=True,
    )
    link += nodes.inline(text=label, classes=["xref", "std", "std-doc"])
    return link


def section(title: str, children: Sequence[nodes.Node]) -> nodes.section:
    """Return a document section with a real, linkable heading."""
    result = nodes.section(ids=[nodes.make_id(title)])
    result += nodes.title(text=title)
    result.extend(children)
    return result


def documented_section(title: str, documented_object: object) -> nodes.section | None:
    """Render ordinary paragraphs and bullet points from an object docstring."""
    docstring = inspect.getdoc(documented_object)
    if not docstring:
        return None

    children: list[nodes.Node] = []
    bullet_list = nodes.bullet_list()
    has_bullets = False
    paragraph_lines: list[str] = []
    for line in docstring.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            has_bullets = True
            item = nodes.list_item()
            item += nodes.paragraph(text=stripped[2:].replace("**", ""))
            bullet_list += item
        elif stripped and not stripped.endswith(":"):
            paragraph_lines.append(stripped)
    if paragraph_lines:
        children.append(nodes.paragraph(text=" ".join(paragraph_lines)))
    if has_bullets:
        children.append(bullet_list)
    return section(title, children)


def documented_items(documented_object: object) -> dict[str, str]:
    """Return named bullet descriptions from an object's docstring."""
    docstring = inspect.getdoc(documented_object)
    if not docstring:
        return {}

    result: dict[str, str] = {}
    for line in docstring.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- ") or ":" not in stripped:
            continue
        name, description = stripped[2:].replace("**", "").split(":", 1)
        if name.replace("_", "").isalnum():
            result[name] = description.strip()
    return result


def code_block(content: str, language: str) -> nodes.literal_block:
    """Return a code block with explicit syntax highlighting."""
    block = nodes.literal_block(content, content)
    block["language"] = language
    return block


def details(items: Sequence[tuple[str, DetailValue, bool]]) -> nodes.container:
    """Stack labelled values vertically inside one table cell."""
    result = nodes.container(classes=["asokai-reference-details"])
    for label, value, literal in items:
        paragraph = nodes.paragraph()
        paragraph += nodes.strong(text=f"{label}: ")
        if isinstance(value, nodes.Node):
            paragraph += value
        elif literal:
            paragraph += nodes.literal(value, value)
        else:
            paragraph += nodes.Text(value)
        result += paragraph
    return result


def table_entry(cell: TableCell) -> nodes.entry:
    """Return one table entry from text or a prepared node."""
    entry = nodes.entry()
    if isinstance(cell, nodes.Node):
        entry += cell
        return entry

    text, literal = cell
    paragraph = nodes.paragraph()
    if literal:
        paragraph += nodes.literal(text, text)
    else:
        paragraph += nodes.Text(text)
    entry += paragraph
    return entry


def table(
    headers: Sequence[str],
    rows: Sequence[Sequence[TableCell]],
    widths: Sequence[int],
    *,
    css_class: str,
) -> nodes.table:
    """Return a consistently formatted reference table."""
    result = nodes.table(classes=["asokai-reference-table", css_class])
    group = nodes.tgroup(cols=len(headers))
    result += group
    for width in widths:
        group += nodes.colspec(colwidth=width)

    head = nodes.thead()
    header_row = nodes.row()
    for header in headers:
        header_row += table_entry((header, False))
    head += header_row
    group += head

    body = nodes.tbody()
    for values in rows:
        row = nodes.row()
        for cell in values:
            row += table_entry(cell)
        body += row
    group += body
    return result
