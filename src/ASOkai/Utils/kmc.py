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
        ci = int(kwargs.get("min_count", 2))
        cs = int(kwargs.get("counter_max", 255))
        hc = bool(kwargs.get("homopolymer_compressed", False))

        return (directory / f"{stem}.k{k}.ci{ci}.cs{cs}{'.hc' if hc else ''}").resolve()

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
            memory_gb (int): Max RAM limit in GB, 1-1024. Defaults to 12.
            input_format (InputFormat): Sequence format ('fa', 'fq', 'fm', 'fbam', 'fkmc'). Defaults to 'fm'.
            threads (int | None): Number of threads. Defaults to all CPU cores.
            strict_memory (bool): Enforce strict RAM limit. Defaults to False.
            homopolymer_compressed (bool): Compress homopolymer runs. Defaults to False.
            signature_length (int | None): Signature length, 5-11. Defaults to 9.
            min_count (int | None): Exclude k-mers occurring fewer times than this. Defaults to 2.
            counter_max (int | None): Maximum counter value. Defaults to 255.
            max_count (int | None): Exclude k-mers occurring more times than this. Defaults to 1_000_000_000.
            canonical (bool): Use canonical k-mers. Defaults to True.
            ram_only (bool): Keep all data in RAM. Defaults to False.
            n_bins (int | None): Number of bins.
            sf (int | None): FASTQ reading threads.
            sp (int | None): Splitting threads.
            sr (int | None): 2nd-stage threads.
            json_summary (str | Path | None): Write JSON summary to this file.
            without_output (bool): Skip writing database shards (`-w`). Defaults to False.
            output_kind (OutputKind | None): Output format ('kmc' or 'kff').
            hide_progress (bool): Suppress progress percentage output. Defaults to False.
            estimate_histogram_only (bool): Estimate histogram without counting (`-e`). Defaults to False.
            optimize_output_size (bool): Reduce output file size. Defaults to False.
            verbose (bool): Pass `-v` to `kmc` for binary-level diagnostics. Defaults to False.
            debug (bool): Log cwd and full command at DEBUG; stream subprocess stdout/stderr to the terminal. Defaults to True.
            check (bool): Raise `KMCExecutionError` if `kmc` exits non-zero. Defaults to True.
            additional_args (Sequence[str] | None): Extra command-line arguments passed verbatim to `kmc`.

        Returns:
            KMCDatabase | None: The database handle if successful, or None if `without_output` or 
            `estimate_histogram_only` is used and no prior shards exist.

        Raises:
            KMCExecutionError: If `kmc` exits non-zero (when `check=True`), or if `kmc` succeeds 
            but the expected shard files (`.kmc_pre`, `.kmc_suf`) are missing.
        """
        if kmc is None:
            kmc = KMC()
        prefix = cls.resolve_prefix(input_path, output_dir, **kwargs)
        db = cls(prefix, int(kwargs.get("k", 25)))

        skip_output = kwargs.get("without_output") or kwargs.get("estimate_histogram_only")
        
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

    def run(
        self,
        input_path: str | Path,
        output_db_prefix: str | Path,
        working_directory: str | Path,
        *,
        k: int = 25,
        memory_gb: int = 12,
        input_format: InputFormat = "fm",
        threads: int | None = None,
        strict_memory: bool = False,
        homopolymer_compressed: bool = False,
        signature_length: int | None = None,
        min_count: int | None = None,
        counter_max: int | None = None,
        max_count: int | None = None,
        canonical: bool = True,
        ram_only: bool = False,
        n_bins: int | None = None,
        sf: int | None = None,
        sp: int | None = None,
        sr: int | None = None,
        json_summary: str | Path | None = None,
        without_output: bool = False,
        output_kind: OutputKind | None = None,
        hide_progress: bool = False,
        estimate_histogram_only: bool = False,
        optimize_output_size: bool = False,
        verbose: bool = False,
        debug: bool = True,
        check: bool = True,
        additional_args: Sequence[str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Execute ``kmc`` with the provided parameters."""
        
        if not 1 <= k <= 256:
            raise ValueError(f"k must be between 1 and 256, got {k}")
        if not 1 <= memory_gb <= 1024:
            raise ValueError(f"memory_gb must be between 1 and 1024, got {memory_gb}")
        if signature_length is not None:
            if not 5 <= signature_length <= 11:
                raise ValueError(f"signature_length must be between 5 and 11, got {signature_length}")
            if signature_length > k:
                raise ValueError(f"signature_length ({signature_length}) cannot be greater than k ({k})")

        work = Path(working_directory).resolve()
        work.mkdir(parents=True, exist_ok=True)
        out_prefix = Path(output_db_prefix).resolve()
        out_prefix.parent.mkdir(parents=True, exist_ok=True)

        # Build Arguments
        argv = [self._kmc, f"-k{k}", f"-m{memory_gb}", f"-{input_format}"]
        
        flag_map = {
            "-sm": strict_memory,
            "-hc": homopolymer_compressed,
            "-b": not canonical,
            "-r": ram_only,
            "-w": without_output,
            "-hp": hide_progress,
            "-e": estimate_histogram_only,
            "--opt-out-size": optimize_output_size,
            "-v": verbose,
        }
        argv.extend(flag for flag, active in flag_map.items() if active)

        param_map = {
            "-t": threads,
            "-p": signature_length,
            "-ci": min_count,
            "-cs": counter_max,
            "-cx": max_count,
            "-n": n_bins,
            "-sf": sf,
            "-sp": sp,
            "-sr": sr,
            "-o": output_kind,
        }
        argv.extend(f"{prefix}{val}" for prefix, val in param_map.items() if val is not None)

        if json_summary:
            argv.append(f"-j{Path(json_summary).resolve()}")
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