#!/usr/bin/env python
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Literal

OutputKind = Literal["kmc", "kff"]
ReadInputKind = Literal["a", "q"]
CalculationMode = Literal["min", "max", "sum", "diff", "left", "right"]

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
                flags.append(prefix)  # Flag, example: "-v"
            else:
                flags.append(f"{prefix}{value}")  # Flag + value, example: "-ci5"
        return flags

    def run(
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
                print(" ".join(shlex.quote(a) for a in self._argv))
                if resolved_cwd is not None:
                    print(f"cwd: {resolved_cwd}")

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
        

class KMCTransform(KMCTool):
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
    ) -> "KMCTransform":
        self._argv.append("sort")
        if output is not None:
            self._argv.append(self._resolve_path(output))
        param_map = {
            "-ci": ci,
            "-cx": cx,
            "-cs": cs,
            "-o": o,
        }
        self._argv.extend(self._build_cli_args(param_map))
        return self

    def reduce(
        self,
        output: str | Path | None = None,
        *,
        ci: int | None = None,
        cx: int | None = None,
        cs: int | None = None,
        o: OutputKind | None = None,
    ) -> "KMCTransform":
        self._argv.append("reduce")
        if output is not None:
            self._argv.append(self._resolve_path(output))
        param_map = {
            "-ci": ci,
            "-cx": cx,
            "-cs": cs,
            "-o": o,
        }
        self._argv.extend(self._build_cli_args(param_map))
        return self

    def compact(
        self,
        output: str | Path | None = None,
        *,
        o: OutputKind | None = None,
    ) -> "KMCTransform":
        self._argv.append("compact")
        if output is not None:
            self._argv.append(self._resolve_path(output))
        param_map = {
            "-o": o,
        }
        self._argv.extend(self._build_cli_args(param_map))
        return self

    def histogram(
        self,
        output: str | Path | None = None,
        *,
        ci: int | None = None,
        cx: int | None = None,
    ) -> "KMCTransform":
        self._argv.append("histogram")
        if output is not None:
            self._argv.append(self._resolve_path(output))
        param_map = {
            "-ci": ci,
            "-cx": cx,
        }
        self._argv.extend(self._build_cli_args(param_map))
        return self

    def dump(
        self,
        output: str | Path | None = None,
        *,
        s: bool = False,
    ) -> "KMCTransform":
        self._argv.append("dump")
        param_map = {
            "-s": True if s else None,
        }
        self._argv.extend(self._build_cli_args(param_map))
        if output is not None:
            self._argv.append(self._resolve_path(output))
        return self

    def set_counts(
        self,
        value: int,
        output: str | Path | None = None,
        *,
        o: OutputKind | None = None,
    ) -> "KMCTransform":
        self._argv.extend(["set_counts", str(value)])
        if output is not None:
            self._argv.append(self._resolve_path(output))
        param_map = {
            "-o": o,
        }
        self._argv.extend(self._build_cli_args(param_map))
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
        param_map = {
            "-ci": ci,
            "-cx": cx,
        }
        self._argv.extend(self._build_cli_args(param_map))
        self._argv.extend(operations)
        return super().run(t=t, v=v, hp=hp, debug=debug, check=check, cwd=cwd)

class KMCSimple(KMCTool):
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
    ) -> "KMCSimple":
        self._argv.extend([op, self._resolve_path(output)])
        param_map = {
            "-ci": ci,
            "-cx": cx,
            "-cs": cs,
            "-o": o,
            "-oc": oc,
        }
        self._argv.extend(self._build_cli_args(param_map))
        return self

    def intersect(self, output: str | Path, **kwargs: Any) -> "KMCSimple":
        return self._simple_operation("intersect", output, **kwargs)

    def union(self, output: str | Path, **kwargs: Any) -> "KMCSimple":
        return self._simple_operation("union", output, **kwargs)

    def kmers_subtract(self, output: str | Path, **kwargs: Any) -> "KMCSimple":
        return self._simple_operation("kmers_subtract", output, **kwargs)

    def counters_subtract(self, output: str | Path, **kwargs: Any) -> "KMCSimple":
        return self._simple_operation("counters_subtract", output, **kwargs)

    def reverse_kmers_subtract(self, output: str | Path, **kwargs: Any) -> "KMCSimple":
        return self._simple_operation("reverse_kmers_subtract", output, **kwargs)

    def reverse_counters_subtract(self, output: str | Path, **kwargs: Any) -> "KMCSimple":
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
        param_map = {
            "-ci": input1_ci,
            "-cx": input1_cx,
        }
        self._argv.extend(self._build_cli_args(param_map))
        
        self._argv.append(self._resolve_path(input2_path))
        param_map = {
            "-ci": input2_ci,
            "-cx": input2_cx,
        }
        self._argv.extend(self._build_cli_args(param_map))

        self._argv.extend(operations)
        return super().run(t=t, v=v, hp=hp, debug=debug, check=check, cwd=cwd)

class KMCComplex(KMCTool):
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

class KMCFilter(KMCTool):
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

        param_map = {
            "-t": True if trim else None,
            "-hm": True if hm else None,
        }
        self._argv.extend(self._build_cli_args(param_map))

        self._argv.append(self._resolve_path(kmc_input_db_path))
        param_map = {
            "-ci": db_ci,
            "-cx": db_cx,
        }
        self._argv.extend(self._build_cli_args(param_map))

        self._argv.append(self._resolve_path(input_read_set_path))
        param_map = {
            "-ci": read_ci,
            "-cx": read_cx,
            "-f": read_f,
        }
        self._argv.extend(self._build_cli_args(param_map))

        self._argv.append(self._resolve_path(output_read_set_path))
        param_map = {
            "-f": output_f,
        }
        self._argv.extend(self._build_cli_args(param_map))

        return super().run(t=t, v=v, hp=hp, debug=debug, check=check, cwd=cwd)