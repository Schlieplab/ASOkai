#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/steps/utils/base.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Base class for reusable utility steps.
License: LGPL-3.0-or-later
"""

from ASOkai._pipeline.steps.base import Step


class UtilityStep(Step):
    """Pipeline step that provides a reusable supporting operation."""
