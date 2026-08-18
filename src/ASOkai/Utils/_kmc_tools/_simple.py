#!/usr/bin/env python
"""
Filename: src/ASOkai/Utils/_kmc_tools/_simple.py
Author: Kian Jalilian
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: This file defines ASOkai simple functionality.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from ._base import KMCTool, CalculationMode, OutputKind


class Simple(KMCTool):
    def __init__(self, kmc_tools_executable: str = "kmc_tools") -> None:
        super().__init__(kmc_tools_executable)

    def _simple_operation(
        self,
        op: str,
        output: str | Path,
        *,
        ci: int | None = None,
        cx: int | None = None,
        cs: int | None = None,
        o: OutputKind | None = None,
        oc: CalculationMode | None = None,
    ) -> "Simple":
        self._argv.extend([op, self._resolve_path(output)])
        self._argv.extend(self._build_cli_args({"-ci": ci, "-cx": cx, "-cs": cs, "-o": o, "-oc": oc}))
        return self

    def intersect(self, output: str | Path, **kwargs: Any) -> "Simple":
        return self._simple_operation("intersect", output, **kwargs)

    def union(self, output: str | Path, **kwargs: Any) -> "Simple":
        return self._simple_operation("union", output, **kwargs)

    def kmers_subtract(self, output: str | Path, **kwargs: Any) -> "Simple":
        return self._simple_operation("kmers_subtract", output, **kwargs)

    def counters_subtract(self, output: str | Path, **kwargs: Any) -> "Simple":
        return self._simple_operation("counters_subtract", output, **kwargs)

    def reverse_kmers_subtract(self, output: str | Path, **kwargs: Any) -> "Simple":
        return self._simple_operation("reverse_kmers_subtract", output, **kwargs)

    def reverse_counters_subtract(self, output: str | Path, **kwargs: Any) -> "Simple":
        return self._simple_operation("reverse_counters_subtract", output, **kwargs)

    def run(
        self,
        input1_path: str | Path,
        input2_path: str | Path,
        *,
        input1_ci: int | None = None,
        input1_cx: int | None = None,
        input2_ci: int | None = None,
        input2_cx: int | None = None,
        t: int | None = None,
        v: bool = False,
        hp: bool = False,
        debug: bool = True,
        check: bool = True,
        cwd: str | Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        operations = self._argv[:]
        self._argv = ["simple"]
        self._argv.append(self._resolve_path(input1_path))
        self._argv.extend(self._build_cli_args({"-ci": input1_ci, "-cx": input1_cx}))
        self._argv.append(self._resolve_path(input2_path))
        self._argv.extend(self._build_cli_args({"-ci": input2_ci, "-cx": input2_cx}))
        self._argv.extend(operations)
        return self._execute(t=t, v=v, hp=hp, debug=debug, check=check, cwd=cwd)
