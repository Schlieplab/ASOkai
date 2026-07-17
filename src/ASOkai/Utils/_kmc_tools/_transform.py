#!/usr/bin/env python
"""
Filename: src/ASOkai/Utils/_kmc_tools/_transform.py
Author: Kian Jalilian
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: This file defines ASOkai transform functionality.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from ._base import KMCTool, OutputKind


class Transform(KMCTool):
    def __init__(self, kmc_tools_executable: str = "kmc_tools") -> None:
        super().__init__(kmc_tools_executable)

    def sort(
        self,
        output: str | Path | None = None,
        *,
        ci: int | None = None,
        cx: int | None = None,
        cs: int | None = None,
        o: OutputKind | None = None,
    ) -> "Transform":
        self._argv.append("sort")
        if output is not None:
            self._argv.append(self._resolve_path(output))
        self._argv.extend(self._build_cli_args({"-ci": ci, "-cx": cx, "-cs": cs, "-o": o}))
        return self

    def reduce(
        self,
        output: str | Path | None = None,
        *,
        ci: int | None = None,
        cx: int | None = None,
        cs: int | None = None,
        o: OutputKind | None = None,
    ) -> "Transform":
        self._argv.append("reduce")
        if output is not None:
            self._argv.append(self._resolve_path(output))
        self._argv.extend(self._build_cli_args({"-ci": ci, "-cx": cx, "-cs": cs, "-o": o}))
        return self

    def compact(
        self,
        output: str | Path | None = None,
        *,
        o: OutputKind | None = None,
    ) -> "Transform":
        self._argv.append("compact")
        if output is not None:
            self._argv.append(self._resolve_path(output))
        self._argv.extend(self._build_cli_args({"-o": o}))
        return self

    def histogram(
        self,
        output: str | Path | None = None,
        *,
        ci: int | None = None,
        cx: int | None = None,
    ) -> "Transform":
        self._argv.append("histogram")
        if output is not None:
            self._argv.append(self._resolve_path(output))
        self._argv.extend(self._build_cli_args({"-ci": ci, "-cx": cx}))
        return self

    def dump(
        self,
        output: str | Path | None = None,
        *,
        s: bool = False,
    ) -> "Transform":
        self._argv.append("dump")
        self._argv.extend(self._build_cli_args({"-s": True if s else None}))
        if output is not None:
            self._argv.append(self._resolve_path(output))
        return self

    def set_counts(
        self,
        value: int,
        output: str | Path | None = None,
        *,
        o: OutputKind | None = None,
    ) -> "Transform":
        self._argv.extend(["set_counts", str(value)])
        if output is not None:
            self._argv.append(self._resolve_path(output))
        self._argv.extend(self._build_cli_args({"-o": o}))
        return self

    def run(
        self,
        input_path: str | Path,
        *,
        ci: int | None = None,
        cx: int | None = None,
        t: int | None = None,
        v: bool = False,
        hp: bool = False,
        debug: bool = True,
        check: bool = True,
        cwd: str | Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        operations = self._argv[:]
        self._argv = ["transform", self._resolve_path(input_path)]
        self._argv.extend(self._build_cli_args({"-ci": ci, "-cx": cx}))
        self._argv.extend(operations)
        return self._execute(t=t, v=v, hp=hp, debug=debug, check=check, cwd=cwd)
