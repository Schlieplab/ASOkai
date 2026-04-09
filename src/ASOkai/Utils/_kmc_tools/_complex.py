from __future__ import annotations

import subprocess
from pathlib import Path

from ._base import KMCTool


class Complex(KMCTool):
    def __init__(self, kmc_tools_executable: str = "kmc_tools") -> None:
        super().__init__(kmc_tools_executable)

    def run(
        self,
        operations_definition_file: str | Path,
        *,
        t: int | None = None,
        v: bool = False,
        hp: bool = False,
        debug: bool = True,
        check: bool = True,
        cwd: str | Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        self._argv = ["complex"]
        self._argv.append(self._resolve_path(operations_definition_file))
        return super().run(t=t, v=v, hp=hp, debug=debug, check=check, cwd=cwd)
