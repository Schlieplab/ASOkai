#!/usr/bin/env python
"""
Filename: src/ASOkai/Biochemistry/_mechanism_of_action.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: This file defines the base MechanismOfAction class.
License: LGPL-3.0-or-later
"""
from abc import ABC

from ..Utils import Serializable


class MechanismOfAction(Serializable, ABC):
    """Abstract base class for antisense mechanisms of action."""
