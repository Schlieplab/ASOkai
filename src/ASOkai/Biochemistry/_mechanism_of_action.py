#!/usr/bin/env python
"""
Filename: src/ASOkai/Biochemistry/_mechanism_of_action.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: This file defines the ID-only MechanismOfAction value.
License: LGPL-3.0-or-later
"""
from dataclasses import dataclass

from ..Utils import Serializable


@dataclass(frozen=True)
class MechanismOfAction(Serializable):
    """An antisense mechanism represented by its stable design ID."""

    id: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("Mechanism ID must be a non-empty string.")
