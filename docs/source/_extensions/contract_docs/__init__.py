#!/usr/bin/env python
"""
Filename: docs/source/_extensions/contract_docs/__init__.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Sphinx extension generating documentation from ASOkai contracts.
License: LGPL-3.0-or-later
"""

from .configuration import (
    collect_step_config_fields,
    collect_step_schema_rules,
    get_built_in_step,
    get_built_in_steps,
)
from .file_contracts import (
    append_serializable_contracts,
    serializable_contract_nodes,
)
from .steps import (
    ASOkaiStepList,
    ASOkaiStepReference,
    build_step_list,
    build_step_reference,
)

__all__ = [
    "ASOkaiStepList",
    "ASOkaiStepReference",
    "build_step_list",
    "build_step_reference",
    "collect_step_config_fields",
    "collect_step_schema_rules",
    "get_built_in_step",
    "get_built_in_steps",
    "serializable_contract_nodes",
]


def setup(app):
    """Register ASOkai's generated reference directives with Sphinx."""
    app.add_directive("asokai-step-list", ASOkaiStepList)
    app.add_directive("asokai-step-reference", ASOkaiStepReference)
    app.connect("doctree-read", append_serializable_contracts)
    return {
        "version": "0.4",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
