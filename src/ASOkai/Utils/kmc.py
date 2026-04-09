#!/usr/bin/env python
"""
Filename: src/ASOkai/Utils/kmc.py
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
import tempfile
from dataclasses import dataclass
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


@dataclass(frozen=True)
class KMCDatabase:
    """Handle for a KMC database, managing paths and build execution."""

    prefix_path: Path
    k: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "prefix_path", self.prefix_path.resolve())

    @property
    def pre_path(self) -> Path:
        return Path(f"{self.prefix_path}.kmc_pre")

    @property
    def suf_path(self) -> Path:
        return Path(f"{self.prefix_path}.kmc_suf")

    @property
    def exists(self) -> bool:
        return self.pre_path.is_file() and self.suf_path.is_file()

    @classmethod
    def resolve_prefix(
        cls,
        input_path: str | Path,
        output_dir: str | Path | None = None,
        **kwargs: Any,
    ) -> Path:
        """Resolves the output prefix appending db-altering arguments to the filename."""
        inp = Path(str(input_path).lstrip("@"))
        stem = inp.stem or inp.name or "kmc"
        directory = Path(output_dir) if output_dir else inp.parent

        k = int(kwargs.get("k", 25))
        ci = int(kwargs.get("ci", 2))
        cs = int(kwargs.get("cs", 255))
        cx = int(kwargs.get("cx", 1e9))
        hc = bool(kwargs.get("homopolymer_compressed", False))

        return (directory / f"{stem}.k{k}.ci{ci}.cs{cs}.cx{format(cx, ".0e").replace("e+", "e").replace("e0", "e")}{'.hc' if hc else ''}").resolve()

    @classmethod
    def build(
        cls,
        input_path: str | Path,
        kmc: "KMC | None" = None,
        working_dir: str | Path | None = None,
        output_dir: str | Path | None = None,
        force: bool = False,
        **kwargs: Any,
    ) -> "KMCDatabase | None":
        """
        Builds the KMC database if it doesn't already exist or if `force` is True.

        Args:
            input_path (str | Path): Path to the input sequence file or `@<list_file>`.
            kmc (KMC | None, optional): The KMC executable wrapper instance. Defaults to a new KMC() instance.
            working_dir (str | Path | None, optional): Scratch directory for KMC. If None, a temporary directory is created in the current working directory and deleted after.
            output_dir (str | Path | None, optional): Explicit directory for the output database. Defaults to the input file's directory.
            force (bool, optional): If True, forces a rebuild even if the database shards already exist. Defaults to False.

        Keyword Args (KMC Parameters):
            k (int): K-mer length, 1-256. Defaults to 25.
            m (int): Max RAM limit in GB, 1-1024. Defaults to 12.
            f (InputFormat): Sequence format ('fa', 'fq', 'fm', 'fbam', 'fkmc'). Defaults to 'fm'.
            t (int | None): Number of threads. Defaults to all CPU cores.
            sm (bool): Enforce strict RAM limit. Defaults to False.
            hc (bool): Compress homopolymer runs. Defaults to False.
            p (int | None): Signature length, 5-11. Defaults to 9.
            ci (int | None): Exclude k-mers occurring fewer times than this. Defaults to 2.
            cs (int | None): Maximum counter value. Defaults to 255.
            cx (int | None): Exclude k-mers occurring more times than this. Defaults to 1_000_000_000.
            b (bool): Use canonical k-mers. Defaults to True.
            r (bool): Keep all data in RAM. Defaults to False.
            n (int | None): Number of bins.
            sf (int | None): FASTQ reading threads.
            sp (int | None): Splitting threads.
            sr (int | None): 2nd-stage threads.
            j (str | Path | None): Write JSON summary to this file.
            w (bool): Skip writing database shards (`-w`). Defaults to False.
            o (OutputKind | None): Output format ('kmc' or 'kff').
            hp (bool): Suppress progress percentage output. Defaults to False.
            e (bool): Estimate histogram without counting (`-e`). Defaults to False.
            opt_out_size (bool): Reduce output file size. Defaults to False.
            v (bool): Pass `-v` to `kmc` for binary-level diagnostics. Defaults to False.
            debug (bool): Log cwd and full command at DEBUG; stream subprocess stdout/stderr to the terminal. Defaults to True.
            check (bool): Raise `KMCExecutionError` if `kmc` exits non-zero. Defaults to True.
            additional_args (Sequence[str] | None): Extra command-line arguments passed verbatim to `kmc`.

        Returns:
            KMCDatabase | None: The database handle if successful, or None if `w` or 
            `e` is used and no prior shards exist.

        Raises:
            KMCExecutionError: If `kmc` exits non-zero (when `check=True`), or if `kmc` succeeds 
            but the expected shard files (`.kmc_pre`, `.kmc_suf`) are missing.
        """
        if kmc is None:
            kmc = KMC()
        prefix = cls.resolve_prefix(input_path, output_dir, **kwargs)
        db = cls(prefix, int(kwargs.get("k", 25)))

        skip_output = kwargs.get("w") or kwargs.get("e")
        
        # Skip build if database already exists and force is off
        if db.exists and not force and not skip_output:
            logger.info("KMC database already exists, skipping build: %s", prefix)
            return db

        def _execute(work: Path) -> "KMCDatabase | None":
            proc = kmc.run(input_path, prefix, work, **kwargs)
            
            if skip_output:
                return db if db.exists else None
            
            if kwargs.get("check", True) and not db.exists:
                raise KMCExecutionError(
                    f"kmc succeeded but shard files are missing: {prefix}",
                    returncode=proc.returncode,
                    cmd=list(proc.args),
                    stdout=proc.stdout,
                    stderr=proc.stderr,
                )
            return db

        if working_dir:
            return _execute(Path(working_dir))
        
        # Create a temporary directory inside the current working directory
        # The 'with' context manager ensures it gets deleted after _execute completes.
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as td:
            return _execute(Path(td))

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
        raise FileNotFoundError(f"Executable not found or not executable: {name_or_path!r}")

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
        b: bool = True,
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
        """Execute ``kmc`` with the provided parameters."""
        
        if not 1 <= k <= 256:
            raise ValueError(f"k must be between 1 and 256, got {k}")
        if not 1 <= m <= 1024:
            raise ValueError(f"memory_gb must be between 1 and 1024, got {m}")
        if p is not None:
            if not 5 <= p <= 11:
                raise ValueError(f"signature_length must be between 5 and 11, got {p}")
            if p > k:
                raise ValueError(f"signature_length ({p}) cannot be greater than k ({k})")

        work = Path(working_directory).resolve()
        work.mkdir(parents=True, exist_ok=True)
        out_prefix = Path(output_db_prefix).resolve()
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
            logger.info("kmc building k=%s → %s", k, out_prefix.name)

        # Execute
        proc = subprocess.run(
            argv,
            capture_output=not debug,
            text=True,
            check=False,
            cwd=str(work),
        )

        if not debug and proc.returncode == 0:
            logger.info("kmc done: %s", out_prefix)

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