#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/steps/core/base.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Base class for core data pipeline steps.
License: LGPL-3.0-or-later
"""

from ASOkai._pipeline.steps.base import Step


class CoreStep(Step):
    """Pipeline step that prepares, downloads, builds, or transforms core data."""
