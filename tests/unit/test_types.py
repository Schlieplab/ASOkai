#!/usr/bin/env python
"""
Filename: tests/unit/test_types.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: Tests for shared ASOkai types.
License: LGPL-3.0-or-later
"""

from typing import get_args

from ASOkai import Types


def test_types_namespace_is_available_from_package_root():
    assert Types.__name__ == "ASOkai._types"


def test_scalar_contains_supported_scalar_values():
    for value in ("text", 1, 1.0, True, None):
        assert isinstance(value, Types.Scalar)


def test_shared_domain_types_are_available_from_types_namespace():
    assert set(get_args(Types.Strand)) == {"+", "-"}
    assert set(get_args(Types.TargetRegion)) == {
        "exonic",
        "pre-mrna",
        "transcriptomic",
    }
