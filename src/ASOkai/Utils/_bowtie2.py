#!/usr/bin/env python
"""
Filename: src/ASOkai/Utils/_bowtie2.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Subprocess wrappers for the Bowtie 2 command-line tools.
License: LGPL-3.0-or-later (this file only)

Bowtie 2 is third-party GPLv3 software. These wrappers invoke its executables
without bundling them. See https://bowtie-bio.sourceforge.net/bowtie2/manual.shtml.
"""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Literal, Sequence


logger = logging.getLogger(__name__)

ReadFormat = Literal["fastq", "fasta", "raw"]


class Bowtie2ExecutionError(RuntimeError):
    """A Bowtie 2 executable returned a nonzero exit status."""

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


class _Bowtie2Command:
    def __init__(self, executable: str) -> None:
        found = shutil.which(executable)
        if found is None:
            path = Path(executable)
            if path.is_file() and os.access(path, os.X_OK):
                found = str(path.resolve())
        if found is None:
            raise FileNotFoundError(
                f"Executable not found or not executable: {executable!r}"
            )
        self._executable = found

    @property
    def executable(self) -> str:
        """Return the resolved command path."""
        return self._executable

    @staticmethod
    def _path(path: str | Path) -> str:
        return str(Path(path).resolve())

    def _execute(
        self,
        args: list[str],
        *,
        cwd: str | Path | None,
        debug: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        cmd = [self.executable, *args]
        if debug:
            logger.debug("Bowtie 2 cmd: %s", shlex.join(cmd))
        result = subprocess.run(
            cmd,
            cwd=self._path(cwd) if cwd is not None else None,
            text=True,
            capture_output=not debug,
            check=False,
        )
        if check and result.returncode != 0:
            details = result.stderr or result.stdout or ""
            raise Bowtie2ExecutionError(
                f"{Path(self.executable).name} failed with exit code "
                f"{result.returncode}\n{details}",
                returncode=result.returncode,
                cmd=cmd,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        return result


class Bowtie2Build(_Bowtie2Command):
    """Run ``bowtie2-build`` with selected CLI options to create an index."""

    def __init__(self, executable: str = "bowtie2-build") -> None:
        super().__init__(executable)

    def run(
        self,
        reference: str | Path,
        index_base: str | Path,
        *,
        threads: int | None = None,
        large_index: bool = False,
        offrate: int | None = None,
        packed: bool = False,
        quiet: bool = False,
        additional_args: Sequence[str] = (),
        debug: bool = False,
        check: bool = True,
        cwd: str | Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Build an index from a FASTA file, optionally gzipped.

        ``index_base`` is a prefix, not one of the resulting ``.bt2`` files.
        Bowtie 2 chooses ``.bt2`` or ``.bt2l`` according to index size.
        """
        if threads is not None and (type(threads) is not int or threads < 1):
            raise ValueError("threads must be a positive integer")
        if offrate is not None and (type(offrate) is not int or offrate < 0):
            raise ValueError("offrate must be a non-negative integer")
        index = Path(index_base).resolve()
        index.parent.mkdir(parents=True, exist_ok=True)
        args = ["-f"]
        if threads is not None:
            args.extend(["--threads", str(threads)])
        if large_index:
            args.append("--large-index")
        if offrate is not None:
            args.extend(["--offrate", str(offrate)])
        if packed:
            args.append("--packed")
        if quiet:
            args.append("--quiet")
        args.extend(additional_args)
        args.extend([self._path(reference), str(index)])
        return self._execute(args, cwd=cwd, debug=debug, check=check)


class Bowtie2(_Bowtie2Command):
    """Run ``bowtie2`` with selected CLI options against an index prefix."""

    def __init__(self, executable: str = "bowtie2") -> None:
        super().__init__(executable)

    def run(
        self,
        index_base: str | Path,
        sam_output: str | Path,
        *,
        reads: str | Path | None = None,
        mate1: str | Path | None = None,
        mate2: str | Path | None = None,
        read_format: ReadFormat = "fastq",
        threads: int | None = None,
        local: bool = False,
        seed_length: int | None = None,
        seed_mismatches: int | None = None,
        max_alignments: int | None = None,
        all_alignments: bool = False,
        score_min: str | None = None,
        additional_args: Sequence[str] = (),
        debug: bool = False,
        check: bool = True,
        cwd: str | Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Align unpaired or paired reads and write SAM output.

        Short candidate sequences need an explicit seed length and scoring
        policy; Bowtie 2's presets target longer sequencing reads.
        """
        paired = mate1 is not None and mate2 is not None
        if (reads is None and not paired) or (reads is not None and (mate1 is not None or mate2 is not None)):
            raise ValueError("Supply reads or both mate1 and mate2")
        if read_format not in ("fastq", "fasta", "raw"):
            raise ValueError("read_format must be fastq, fasta, or raw")
        if threads is not None and (type(threads) is not int or threads < 1):
            raise ValueError("threads must be a positive integer")
        if seed_length is not None and (
            type(seed_length) is not int or seed_length < 1
        ):
            raise ValueError("seed_length must be a positive integer")
        if seed_mismatches is not None and (
            type(seed_mismatches) is not int or seed_mismatches not in (0, 1)
        ):
            raise ValueError("seed_mismatches must be 0 or 1")
        if max_alignments is not None and (
            type(max_alignments) is not int or max_alignments < 1
        ):
            raise ValueError("max_alignments must be a positive integer")
        if all_alignments and max_alignments is not None:
            raise ValueError("all_alignments and max_alignments are exclusive")

        output = Path(sam_output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        args = ["-x", self._path(index_base)]
        if reads is not None:
            args.extend(["-U", self._path(reads)])
        else:
            assert mate1 is not None and mate2 is not None
            args.extend(["-1", self._path(mate1), "-2", self._path(mate2)])
        args.append({"fastq": "-q", "fasta": "-f", "raw": "-r"}[read_format])
        if threads is not None:
            args.extend(["--threads", str(threads)])
        if local:
            args.append("--local")
        if seed_length is not None:
            args.extend(["-L", str(seed_length)])
        if seed_mismatches is not None:
            args.extend(["-N", str(seed_mismatches)])
        if max_alignments is not None:
            args.extend(["-k", str(max_alignments)])
        if all_alignments:
            args.append("-a")
        if score_min is not None:
            args.extend(["--score-min", score_min])
        args.extend(additional_args)
        args.extend(["-S", str(output)])
        return self._execute(args, cwd=cwd, debug=debug, check=check)


class Bowtie2Inspect(_Bowtie2Command):
    """Run ``bowtie2-inspect`` with selected CLI options on an index."""

    def __init__(self, executable: str = "bowtie2-inspect") -> None:
        super().__init__(executable)

    def run(
        self,
        index_base: str | Path,
        *,
        names: bool = False,
        summary: bool = False,
        output: str | Path | None = None,
        additional_args: Sequence[str] = (),
        debug: bool = False,
        check: bool = True,
        cwd: str | Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Return reference names, a summary, or reconstructed FASTA."""
        if names and summary:
            raise ValueError("names and summary are exclusive")
        args: list[str] = []
        if names:
            args.append("--names")
        if summary:
            args.append("--summary")
        if output is not None:
            destination = Path(output).resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            args.extend(["--output", str(destination)])
        args.extend(additional_args)
        args.append(self._path(index_base))
        return self._execute(args, cwd=cwd, debug=debug, check=check)
