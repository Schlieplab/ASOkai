#!/usr/bin/env python
"""
Filename: src/ASOkai/Utils/kmc_tools.py
Description: Subprocess wrapper for the KMC Tools CLI.
License: LGPL-3.0-or-later (this file only)

KMC Tools is GPLv3-only third-party software distributed with KMC:
https://github.com/refresh-bio/KMC

This wrapper invokes ``kmc_tools`` on PATH or via an explicit path.
"""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Sequence


logger = logging.getLogger(__name__)


TransformOperationName = Literal[
    "sort",
    "reduce",
    "compact",
    "histogram",
    "dump",
    "set_counts",
]

OutputKind = Literal["kmc", "kff"]


class KMCToolsExecutionError(RuntimeError):
    """Raised when ``kmc_tools`` exits with a non-zero status (when ``check`` is True)."""

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


@dataclass(frozen=True)
class TransformInputParams:
    """Optional filters applied to the transform"""

    min_count: int | None = None
    max_count: int | None = None

    def validate(self) -> None:
        if self.min_count is not None and self.min_count < 1:
            raise ValueError(f"min_count must be >= 1, got {self.min_count}")
        if self.max_count is not None and self.max_count < 1:
            raise ValueError(f"max_count must be >= 1, got {self.max_count}")
        if (
            self.min_count is not None
            and self.max_count is not None
            and self.min_count > self.max_count
        ):
            raise ValueError(
                f"min_count ({self.min_count}) cannot be greater than max_count ({self.max_count})"
            )

    def to_argv(self) -> list[str]:
        self.validate()
        argv: list[str] = []
        if self.min_count is not None:
            argv.append(f"-ci{self.min_count}")
        if self.max_count is not None:
            argv.append(f"-cx{self.max_count}")
        return argv


@dataclass(frozen=True)
class TransformStep:
    """
    One transform step in:

        kmc_tools transform <input> [input_params]
            <oper1 [oper_params1] output1 [output_params1]>
            [<oper2 [oper_params2] output2 [output_params2]>...]

    Supported operations:
      - sort
      - reduce
      - compact
      - histogram
      - dump
      - set_counts
    """

    operation: TransformOperationName
    output: str | Path

    # Shared optional params, only for certain operations.
    min_count: int | None = None
    max_count: int | None = None
    counter_max: int | None = None
    output_kind: OutputKind | None = None

    # dump-specific
    sorted_output: bool = False

    # set_counts-specific
    set_count_value: int | None = None

    additional_args: Sequence[str] | None = field(default=None)

    def __post_init__(self) -> None:
        object.__setattr__(self, "output", Path(self.output).resolve())

    def validate(self) -> None:
        allowed_by_operation: dict[str, set[str]] = {
            "sort": {"min_count", "max_count", "counter_max", "output_kind"},
            "reduce": {"min_count", "max_count", "counter_max", "output_kind"},
            "compact": {"output_kind"},
            "histogram": {"min_count", "max_count"},
            "dump": {"sorted_output"},
            "set_counts": {"set_count_value", "output_kind"},
        }

        if self.operation not in allowed_by_operation:
            raise ValueError(f"Unsupported transform operation: {self.operation!r}")

        provided: set[str] = set()
        if self.min_count is not None:
            provided.add("min_count")
        if self.max_count is not None:
            provided.add("max_count")
        if self.counter_max is not None:
            provided.add("counter_max")
        if self.output_kind is not None:
            provided.add("output_kind")
        if self.sorted_output:
            provided.add("sorted_output")
        if self.set_count_value is not None:
            provided.add("set_count_value")

        illegal = provided - allowed_by_operation[self.operation]
        if illegal:
            raise ValueError(
                f"Invalid parameter(s) for transform operation '{self.operation}': "
                f"{', '.join(sorted(illegal))}"
            )

        if self.min_count is not None and self.min_count < 1:
            raise ValueError(f"min_count must be >= 1, got {self.min_count}")
        if self.max_count is not None and self.max_count < 1:
            raise ValueError(f"max_count must be >= 1, got {self.max_count}")
        if self.counter_max is not None and self.counter_max < 1:
            raise ValueError(f"counter_max must be >= 1, got {self.counter_max}")
        if (
            self.min_count is not None
            and self.max_count is not None
            and self.min_count > self.max_count
        ):
            raise ValueError(
                f"min_count ({self.min_count}) cannot be greater than max_count ({self.max_count})"
            )

        if self.output_kind is not None and self.output_kind not in {"kmc", "kff"}:
            raise ValueError(
                f"output_kind must be 'kmc' or 'kff', got {self.output_kind!r}"
            )

        if self.operation == "set_counts":
            if self.set_count_value is None:
                raise ValueError("set_counts requires set_count_value")
            if self.set_count_value < 0:
                raise ValueError(
                    f"set_count_value must be >= 0, got {self.set_count_value}"
                )
        elif self.set_count_value is not None:
            raise ValueError(
                f"set_count_value is only valid for operation 'set_counts', not '{self.operation}'"
            )

    def to_argv(self) -> list[str]:
        self.validate()

        argv: list[str] = [self.operation]

        # Operation parameters
        if self.operation == "dump" and self.sorted_output:
            argv.append("-s")
        if self.operation == "set_counts":
            argv.append(str(self.set_count_value))

        # Output path
        argv.append(str(self.output))

        # Output parameters
        if self.min_count is not None:
            argv.append(f"-ci{self.min_count}")
        if self.max_count is not None:
            argv.append(f"-cx{self.max_count}")
        if self.counter_max is not None:
            argv.append(f"-cs{self.counter_max}")
        if self.output_kind is not None:
            argv.append(f"-o{self.output_kind}")

        if self.additional_args:
            argv.extend(self.additional_args)

        return argv


class KMCTools:
    """
    Runs the ``kmc_tools`` executable.

    Currently implemented:
      - transform
    """

    def __init__(self, kmc_tools_executable: str = "kmc_tools") -> None:
        self._kmc_tools = self._resolve_executable(kmc_tools_executable)

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
        raise FileNotFoundError(
            f"Executable not found or not executable: {name_or_path!r}"
        )

    @staticmethod
    def _resolve_path(path: str | Path) -> str:
        return str(Path(path).resolve())

    def _run(
        self,
        argv: list[str],
        *,
        cwd: str | Path | None = None,
        debug: bool = True,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        workdir = str(Path(cwd).resolve()) if cwd is not None else None

        if debug:
            logger.debug(
                "kmc_tools cmd: %s",
                " ".join(shlex.quote(str(a)) for a in argv),
            )
            if workdir is not None:
                logger.debug("kmc_tools cwd: %s", workdir)
        else:
            logger.info("Running kmc_tools: %s", Path(argv[0]).name)

        proc = subprocess.run(
            argv,
            capture_output=not debug,
            text=True,
            check=False,
            cwd=workdir,
        )

        if check and proc.returncode != 0:
            err_msg = proc.stderr or proc.stdout or ""
            if debug:
                err_msg = "Output streamed to terminal (see above)."

            raise KMCToolsExecutionError(
                f"kmc_tools failed with exit code {proc.returncode}\n{err_msg}",
                returncode=proc.returncode,
                cmd=argv,
                stdout=proc.stdout,
                stderr=proc.stderr,
            )

        return proc

    def transform(
        self,
        input_db: str | Path,
        steps: Sequence[TransformStep],
        *,
        input_params: TransformInputParams | None = None,
        threads: int | None = None,
        verbose: bool = False,
        hide_progress: bool = False,
        debug: bool = True,
        check: bool = True,
        cwd: str | Path | None = None,
        additional_global_args: Sequence[str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """
        Run:

            kmc_tools [global params] transform <input> [input_params]
                      <oper1 [oper_params1] output1 [output_params1]>
                      [<oper2 [oper_params2] output2 [output_params2]> ...]

        Args:
            input_db:
                Path to input KMC database prefix.
            steps:
                One or more TransformStep objects.
            input_params:
                Optional TransformInputParams for input-side -ci/-cx.
            threads:
                Global -t<value>.
            verbose:
                Global -v.
            hide_progress:
                Global -hp.
            debug:
                If True, stream stdout/stderr directly to terminal and log full command.
            check:
                If True, raise KMCToolsExecutionError on non-zero exit.
            cwd:
                Optional working directory.
            additional_global_args:
                Extra global args passed before 'transform'.

        Returns:
            subprocess.CompletedProcess[str]

        Raises:
            ValueError:
                For invalid Python-side arguments or missing required fields.
            KMCToolsExecutionError:
                If kmc_tools exits non-zero and check=True.
        """
        if not steps:
            raise ValueError("transform requires at least one TransformStep")

        if threads is not None and threads < 1:
            raise ValueError(f"threads must be >= 1, got {threads}")

        resolved_input = self._resolve_path(input_db)

        if input_params is None:
            input_params = TransformInputParams()
        input_params.validate()

        validated_steps = list(steps)
        for i, step in enumerate(validated_steps, start=1):
            if not isinstance(step, TransformStep):
                raise TypeError(
                    f"All steps must be TransformStep instances; "
                    f"item {i} has type {type(step).__name__}"
                )
            step.validate()

        argv: list[str] = [self._kmc_tools]

        # Global params
        if threads is not None:
            argv.append(f"-t{threads}")
        if verbose:
            argv.append("-v")
        if hide_progress:
            argv.append("-hp")
        if additional_global_args:
            argv.extend(additional_global_args)

        # Main operation
        argv.extend(["transform", resolved_input])

        # Input params
        argv.extend(input_params.to_argv())

        # Transform steps
        for step in validated_steps:
            argv.extend(step.to_argv())

        print(f"argv: {argv} , cwd: {cwd} , debug: {debug} , check: {check}")

        return self._run(argv, cwd=cwd, debug=debug, check=check)




__all__ = [
    "KMCTools",
    "KMCToolsExecutionError",
    "TransformInputParams",
    "TransformStep",
]