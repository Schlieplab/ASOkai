#!/usr/bin/env python
"""
Filename: src/ASOkai/Targets/__init__.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: This file initializes the targets module.
License: LGPL-3.0-or-later
"""
from ._create_target_gene import create_target_gene
from ._target_gene import TargetGene

__all__ = [
    "create_target_gene",
    "TargetGene",
]

