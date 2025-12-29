#!/usr/bin/env python
"""
Filename: src/ASOKai/Targets.py
Author: Arash Ayat
Copyright: 2025, Alexander Schliep
Version: 0.1.0
Description: This file imports and exposes target-related classes.
License: LGPL-3.0-or-later
"""
from .targets import TargetGene
from .targets import TargetGeneCreator

__all__ = [
    "TargetGene",
    "TargetGeneCreator",
]