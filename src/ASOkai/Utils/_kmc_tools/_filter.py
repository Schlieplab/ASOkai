from __future__ import annotations

import subprocess
from pathlib import Path

from ._base import KMCTool, ReadInputKind


class Filter(KMCTool):
    def __init__(self, kmc_tools_executable: str = "kmc_tools") -> None:
        super().__init__(kmc_tools_executable)

    def run(
        self,
        kmc_input_db_path: str | Path,
        input_read_set_path: str | Path,
        output_read_set_path: str | Path,
        *,
        trim: bool = False,
        hm: bool = False,
        db_ci: int | None = None,
        db_cx: int | None = None,
        read_ci: int | float | None = None,
        read_cx: int | float | None = None,
        read_f: ReadInputKind | None = None,
        output_f: ReadInputKind | None = None,
        t: int | None = None,
        v: bool = False,
        hp: bool = False,
        debug: bool = True,
        check: bool = True,
        cwd: str | Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        self._argv = ["filter"]
        self._argv.extend(self._build_cli_args({
            "-t": True if trim else None,
            "-hm": True if hm else None,
        }))
        self._argv.append(self._resolve_path(kmc_input_db_path))
        self._argv.extend(self._build_cli_args({"-ci": db_ci, "-cx": db_cx}))
        self._argv.append(self._resolve_path(input_read_set_path))
        self._argv.extend(self._build_cli_args({"-ci": read_ci, "-cx": read_cx, "-f": read_f}))
        self._argv.append(self._resolve_path(output_read_set_path))
        self._argv.extend(self._build_cli_args({"-f": output_f}))
        return super().run(t=t, v=v, hp=hp, debug=debug, check=check, cwd=cwd)
