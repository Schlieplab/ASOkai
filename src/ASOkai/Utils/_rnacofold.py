#!/usr/bin/env python
"""
Filename: src/ASOkai/Utils/_rnacofold.py
Author: Kian Jalilian
Copyright: 2026, Alexander Schliep
Description: Duplex binding free energies computed with ViennaRNA.
License: LGPL-3.0-or-later

ViennaRNA is third-party software distributed under its own license. See
https://www.tbi.univie.ac.at/RNA/.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Mapping

import RNA

#: Model settings accepted as extra arguments, as ``name=value`` pairs.
ModelSettings = Mapping[str, Any]

_SETTINGS_KEY = tuple[tuple[str, Any], ...]


def _settings_key(model_settings: ModelSettings | None) -> _SETTINGS_KEY:
    """Return one hashable, order-independent key for model settings."""
    if not model_settings:
        return ()
    return tuple(sorted(model_settings.items()))


@lru_cache(maxsize=None)
def _model_details(settings: _SETTINGS_KEY) -> Any:
    """Return ViennaRNA model details carrying the supplied settings.

    Raises:
        ValueError: If a setting is not a ViennaRNA model-detail field.
    """
    model_details = RNA.md()
    for name, value in settings:
        if name.startswith("_") or not hasattr(model_details, name):
            raise ValueError(
                f"Unknown ViennaRNA model setting: {name!r}. Accepted "
                "settings are the fields of RNA.md(), such as 'temperature', "
                "'dangles', 'noGU', 'noLP', or 'salt'."
            )
        setattr(model_details, name, value)
    return model_details


@lru_cache(maxsize=65536)
def _monomer_mfe(sequence: str, settings: _SETTINGS_KEY) -> float:
    """Return the minimum free energy of one folded strand."""
    _structure, mfe = RNA.fold_compound(
        sequence,
        _model_details(settings),
    ).mfe()
    return mfe


def binding_dg(
    first_sequence: str,
    second_sequence: str,
    *,
    constraint: str | None = None,
    model_settings: ModelSettings | None = None,
) -> float:
    """Return the binding free energy of two strands in kcal/mol.

    The binding energy is ``MFE(first&second) - (MFE(first) + MFE(second))``.

    Args:
        first_sequence: First strand, 5' to 3'.
        second_sequence: Second strand, 5' to 3'.
        constraint: Optional dot-bracket constraint for the joined duplex
            ``first&second``. Its base pairs are enforced.
        model_settings: Extra arguments passed to ViennaRNA's folding model,
            given as field names of ``RNA.md()`` mapped to values. Common
            fields are ``temperature`` in degrees Celsius, ``dangles``,
            ``noGU``, ``noLP``, and ``salt``. ViennaRNA's own defaults apply
            to every field left out, including a temperature of 37 degrees.

    Raises:
        ValueError: If a sequence is empty, a model setting is unknown, or
            the constraint cannot be met.
    """
    if not first_sequence or not second_sequence:
        raise ValueError("Binding energy requires two non-empty sequences.")
    settings = _settings_key(model_settings)
    duplex = RNA.fold_compound(
        f"{first_sequence}&{second_sequence}",
        _model_details(settings),
    )
    if constraint is not None:
        duplex.hc_add_from_db(
            constraint,
            RNA.CONSTRAINT_DB_DEFAULT | RNA.CONSTRAINT_DB_ENFORCE_BP,
        )
    _structure, duplex_mfe = duplex.mfe()
    if duplex_mfe >= 1e4:
        raise ValueError(
            f"The duplex constraint {constraint!r} cannot be satisfied."
        )
    return duplex_mfe - (
        _monomer_mfe(first_sequence, settings)
        + _monomer_mfe(second_sequence, settings)
    )
