#!/usr/bin/env python
"""
Filename: src/ASOkai/Biochemistry/_rnase_h1.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: RNase-H1 antisense mechanism.
License: LGPL-3.0-or-later
"""

from ._mechanism_of_action import MechanismOfAction


class RNaseH1Mechanism(MechanismOfAction):
    """Target-RNA cleavage mediated by RNase H1."""

    id = "rnase-h1"
