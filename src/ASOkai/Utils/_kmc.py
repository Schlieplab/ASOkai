#!/usr/bin/env python
"""
Filename: src/ASOkai/Utils/_kmc.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Subprocess wrapper for the KMC k-mer counter CLI.
License: LGPL-3.0-or-later (this file only)

KMC is GPLv3-only third-party software (https://github.com/refresh-bio/KMC). See README,
"Third-party software and licenses". Invoke ``kmc`` on PATH or via an explicit path.
"""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Literal, Sequence

InputFormat = Literal["fa", "fq", "fm", "fbam", "fkmc"]
OutputKind = Literal["kmc", "kff"]

logger = logging.getLogger(__name__)


class KMCExecutionError(RuntimeError):
    """Raised when ``kmc`` exits with a non-zero status (when ``check`` is True)."""

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


class KMC:
    """
    Runs the ``kmc`` executable. Options mirror KMC 3.2.x CLI.
    """

    def __init__(self, kmc_executable: str = "kmc") -> None:
        self._kmc = self._resolve_executable(kmc_executable)

    @property
    def executable(self) -> str:
        return self._kmc

    @staticmethod
    def _resolve_executable(name_or_path: str) -> str:
        if found := shutil.which(name_or_path):
            return found
        path = Path(name_or_path)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path.resolve())
        raise FileNotFoundError(
            f"Executable not found or not executable: {name_or_path!r}"
        )

    @staticmethod
    def _resolve_input(input_path: str | Path) -> str:
        """Resolves input path absolutely, respecting KMC's '@' list prefix."""
        s = str(input_path)
        if s.startswith("@"):
            return f"@{Path(s[1:]).resolve()}"
        return str(Path(s).resolve())

    @staticmethod
    def _build_cli_args(param_map: dict[str, Any]) -> list[str]:
        flags = []
        for prefix, value in param_map.items():
            if value is None or value is False:
                continue
            if value is True:
                flags.append(prefix)  # Flag, example: "-v"
            else:
                flags.append(f"{prefix}{value}")  # Flag + value, example: "-ci5"
        return flags

    def run(
        self,
        input_path: str | Path,
        output_db_prefix: str | Path,
        working_directory: str | Path,
        *,
        k: int = 25,
        m: int = 12,
        f: InputFormat = "fm",
        t: int | None = None,
        sm: bool = False,
        hc: bool = False,
        p: int | None = None,
        ci: int | None = None,
        cs: int | None = None,
        cx: int | None = None,
        b: bool = False,
        r: bool = False,
        n: int | None = None,
        sf: int | None = None,
        sp: int | None = None,
        sr: int | None = None,
        j: str | Path | None = None,
        w: bool = False,
        o: OutputKind | None = None,
        hp: bool = False,
        e: bool = False,
        opt_out_size: bool = False,
        v: bool = False,
        debug: bool = True,
        check: bool = True,
        additional_args: Sequence[str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """
        Execute ``kmc`` with the provided parameters.

        ``output_db_prefix`` retains KMC's native prefix behavior, except that
        a ``.kff`` suffix with ``o="kff"`` is treated as the final filename.
        """

        if not 1 <= k <= 256:
            raise ValueError(f"k must be between 1 and 256, got {k}")
        if not 2 <= m <= 1024:
            raise ValueError(f"memory_gb must be between 2 and 1024, got {m}")
        if p is not None:
            if not 5 <= p <= 11:
                raise ValueError(f"signature_length must be between 5 and 11, got {p}")
            if p > k:
                raise ValueError(
                    f"signature_length ({p}) cannot be greater than k ({k})"
                )

        work = Path(working_directory).resolve()
        work.mkdir(parents=True, exist_ok=True)
        output = Path(output_db_prefix).resolve()
        out_prefix = (
            output.with_suffix("") if o == "kff" and output.suffix == ".kff" else output
        )
        reported_output = Path(f"{out_prefix}.kff") if o == "kff" else out_prefix
        out_prefix.parent.mkdir(parents=True, exist_ok=True)

        # Build Arguments
        argv = [self._kmc, f"-k{k}", f"-m{m}", f"-{f}"]

        param_map = {
            "-sm": sm,
            "-hc": hc,
            "-b": b,
            "-r": r,
            "-w": w,
            "-hp": hp,
            "-e": e,
            "--opt-out-size": opt_out_size,
            "-v": v,
            "-t": t,
            "-p": p,
            "-ci": ci,
            "-cs": cs,
            "-cx": cx,
            "-n": n,
            "-sf": sf,
            "-sp": sp,
            "-sr": sr,
            "-o": o,
        }

        argv.extend(self._build_cli_args(param_map))

        if j:
            argv.append(f"-j{Path(j).resolve()}")
        if additional_args:
            argv.extend(additional_args)

        # Append positional args (input MUST be resolved before cwd shifts)
        argv.extend([self._resolve_input(input_path), str(out_prefix), str(work)])

        if debug:
            logger.debug("kmc cwd: %s", work)
            logger.debug("kmc cmd: %s", " ".join(shlex.quote(str(a)) for a in argv))
        else:
            logger.info("kmc building k=%s → %s", k, reported_output.name)

        # Execute
        proc = subprocess.run(
            argv,
            capture_output=not debug,
            text=True,
            check=False,
            cwd=str(work),
        )

        if not debug and proc.returncode == 0:
            logger.info("kmc done: %s", reported_output)

        if check and proc.returncode != 0:
            err_msg = proc.stderr or proc.stdout or ""
            if debug:
                # In debug mode, stdout/stderr are streamed to console, so they are None in `proc`.
                # We prompt the user to check the terminal output.
                err_msg = "Output streamed to terminal (see above)."

            raise KMCExecutionError(
                f"kmc failed with exit code {proc.returncode}\n{err_msg}",
                returncode=proc.returncode,
                cmd=argv,
                stdout=proc.stdout,
                stderr=proc.stderr,
            )

        return proc
