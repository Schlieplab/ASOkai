#!/usr/bin/env python
"""RNase-H1 antisense mechanism."""

from ._mechanism_of_action import MechanismOfAction


class RNaseH1Mechanism(MechanismOfAction):
    """Target-RNA cleavage mediated by RNase H1."""

    id = "rnase-h1"
