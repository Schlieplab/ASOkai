#!/usr/bin/env python
"""
Filename: tests/unit/test_types.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Tests for shared ASOkai types.
License: LGPL-3.0-or-later
"""

from types import NoneType
from typing import get_args

from ASOkai import Types
from ASOkai.Types import Scalar, Strand, TargetRegion


def test_types_module_is_available_through_both_public_import_styles():
    assert Types.__name__ == "ASOkai.Types"
    assert Types.Scalar is Scalar
    assert Types.Strand is Strand
    assert Types.TargetRegion is TargetRegion


def test_shared_type_aliases_define_the_supported_values():
    assert set(get_args(Scalar)) == {str, int, float, bool, NoneType}
    assert set(get_args(Strand)) == {"+", "-"}
    assert set(get_args(TargetRegion)) == {
        "exonic",
        "pre-mrna",
        "transcriptomic",
    }
