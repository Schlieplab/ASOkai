#!/usr/bin/env python
"""
Filename: src/ASOkai/Utils/_kmc_tools/_base.py
Author: Kian Jalilian
Copyright: 2026, Alexander Schliep
Version: 0.1.1
Description: This file defines ASOkai base functionality.
License: LGPL-3.0-or-later
"""
from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Literal

OutputKind = Literal["kmc", "kff"]
ReadInputKind = Literal["a", "q"]
CalculationMode = Literal["min", "max", "sum", "diff", "left", "right"]

logger = logging.getLogger(__name__)


class KMCToolsExecutionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        returncode: int,
        cmd: list[str],
        stdout: str | None = None,
        stderr: str | None = None,
    ) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.cmd = cmd
        self.stdout = stdout
        self.stderr = stderr


class KMCTool:
    def __init__(self, kmc_tools_executable: str = "kmc_tools") -> None:
        self._kmc_tools = self._resolve_executable(kmc_tools_executable)
        self._argv: list[str] = []

    @property
    def executable(self) -> str:
        return self._kmc_tools

    @staticmethod
    def _resolve_executable(name_or_path: str) -> str:
        if found := shutil.which(name_or_path):
            return found
        path = Path(name_or_path)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path.resolve())
        raise FileNotFoundError(f"Executable not found or not executable: {name_or_path!r}")

    @staticmethod
    def _resolve_path(path: str | Path) -> str:
        return str(Path(path).resolve())

    @staticmethod
    def _build_cli_args(param_map: dict[str, Any]) -> list[str]:
        flags = []
        for prefix, value in param_map.items():
            if value is None or value is False:
                continue
            if value is True:
                flags.append(prefix)
            else:
                flags.append(f"{prefix}{value}")
        return flags

    def _execute(
        self,
        *,
        t: int | None = None,
        v: bool = False,
        hp: bool = False,
        debug: bool = True,
        check: bool = True,
        cwd: str | Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        param_map = {
            "-t": t,
            "-v": True if v else None,
            "-hp": True if hp else None,
        }
        global_flags = self._build_cli_args(param_map)

        self._argv[0:0] = [self.executable]
        self._argv[1:1] = global_flags

        resolved_cwd = str(Path(cwd).resolve()) if cwd is not None else None

        try:
            if debug:
                logger.debug("kmc_tools cmd: %s", " ".join(shlex.quote(a) for a in self._argv))
                if resolved_cwd is not None:
                    logger.debug("kmc_tools cwd: %s", resolved_cwd)

            proc = subprocess.run(
                self._argv,
                cwd=resolved_cwd,
                text=True,
                capture_output=not debug,
                check=False,
            )

            if check and proc.returncode != 0:
                raise KMCToolsExecutionError(
                    f"kmc_tools failed with exit code {proc.returncode}",
                    returncode=proc.returncode,
                    cmd=self._argv.copy(),
                    stdout=proc.stdout,
                    stderr=proc.stderr,
                )

            return proc

        finally:
            self._argv = []
