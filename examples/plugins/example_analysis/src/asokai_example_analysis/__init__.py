#!/usr/bin/env python
"""
Filename: examples/plugins/example_analysis/src/asokai_example_analysis/__init__.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Package metadata exposed to ASOkai plugin discovery.
License: LGPL-3.0-or-later
"""

from pathlib import Path


CONFIG_SCHEMA_PATH = Path(__file__).with_name("config.schema.yaml")

__all__ = ["CONFIG_SCHEMA_PATH"]
