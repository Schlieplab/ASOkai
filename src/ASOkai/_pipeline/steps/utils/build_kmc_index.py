#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/steps/utils/build_kmc_index.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Reusable KMC index builder for a supplied FASTA reference.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal, Mapping, cast

from ASOkai.Utils import KMC
from ASOkai._pipeline.contracts.file_types import FastaFile, KffFile
from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.contracts.parameters import ScalarParam
from ASOkai._pipeline.contracts.paths import OutputPathTemplate, TemplateField
from ASOkai._pipeline.contracts.step_spec import StepSpec
from ASOkai._pipeline.steps.utils.base import UtilityStep

_KMC_OPTIONS = (
    ScalarParam(
        "f",
        Literal["fa", "fm"],
        config="parameters.kmc.f",
        default="fm",
        doc="FASTA input format.",
    ),
    ScalarParam("sm", bool, config="parameters.kmc.sm", doc="Use strict memory mode."),
    ScalarParam(
        "hc",
        bool,
        config="parameters.kmc.hc",
        doc="Count homopolymer-compressed k-mers.",
    ),
    ScalarParam(
        "p",
        int | None,
        config="parameters.kmc.p",
        default=None,
        doc="Signature length.",
    ),
    ScalarParam(
        "ci",
        int,
        config="parameters.kmc.ci",
        default=1,
        doc="Minimum count to retain.",
    ),
    ScalarParam(
        "cs",
        int | None,
        config="parameters.kmc.cs",
        default=None,
        doc="Maximum stored count.",
    ),
    ScalarParam(
        "cx",
        int | None,
        config="parameters.kmc.cx",
        default=None,
        doc="Maximum count to retain.",
    ),
    ScalarParam("b", bool, config="parameters.kmc.b", doc="Disable canonical k-mers."),
    ScalarParam("r", bool, config="parameters.kmc.r", doc="Use RAM-only mode."),
    ScalarParam(
        "n",
        int | None,
        config="parameters.kmc.n",
        default=None,
        doc="Number of bins.",
    ),
    ScalarParam(
        "sf",
        int | None,
        config="parameters.kmc.sf",
        default=None,
        doc="Input-reading threads (KMC -sf).",
    ),
    ScalarParam(
        "sp",
        int | None,
        config="parameters.kmc.sp",
        default=None,
        doc="Splitting threads.",
    ),
    ScalarParam(
        "sr",
        int | None,
        config="parameters.kmc.sr",
        default=None,
        doc="Second-stage threads.",
    ),
    ScalarParam(
        "opt_out_size",
        bool,
        config="parameters.kmc.opt_out_size",
        doc="Optimize output database size.",
    ),
)

_KMC_FILENAME_OPTIONS = {
    "f",
    "hc",
    "ci",
    "cs",
    "cx",
    "b",
    "opt_out_size",
}

_KMC_PATH_FIELDS = {
    "assembly": TemplateField("parameters.genome.assembly"),
    "source": TemplateField("parameters.genome.source"),
    "release": TemplateField("parameters.genome.release"),
    "k": TemplateField("parameters.target.k"),
    **{
        param.name: TemplateField(
            cast(str, param.config),
            default="na" if param.default is None else param.default,
        )
        for param in _KMC_OPTIONS
        if param.name in _KMC_FILENAME_OPTIONS
    },
}


class BuildKMCIndexStep(UtilityStep):
    """Build one reusable KFF index from a supplied FASTA reference."""

    name = "build-kmc-index"
    description = "Builds a reusable KMC KFF index from a FASTA reference."
    supports_multiple_workers = True
    consumes_memory_mb = True
    reference_input = FileInput(
        "reference",
        file_type=FastaFile(gzip=None),
        doc="Plain or gzip-compressed FASTA reference to count.",
    )
    kmc_index_output = FileOutput(
        "kmc_index",
        file_type=KffFile(),
        destination=OutputPathTemplate(
            "{assembly}/{source}/{release}/indexes/kmc/"
            "index.k{k}.f{f}.hc{hc}.ci{ci}.cs{cs}.cx{cx}."
            "b{b}.opt_out_size{opt_out_size}.kff",
            fields=_KMC_PATH_FIELDS,
        ),
        doc="Reference k-mer counts in KFF format.",
    )
    spec = StepSpec(
        requirements={"WorkReuse": {"enableReuse": True}},
        params=[
            ScalarParam(
                "k",
                int,
                config="parameters.target.k",
                doc="K-mer length used to build the reference index.",
            ),
            *_KMC_OPTIONS,
        ],
        inputs=[reference_input],
        outputs=[kmc_index_output],
    )

    def validate_parameters(self, values: Mapping[str, object]) -> None:
        """Require a k-mer size supported by KMC."""
        k = values.get("k")
        if type(k) is not int or not 1 <= k <= 256:
            raise ValueError("k must be between 1 and 256")
        p = values.get("p")
        if p is not None and (type(p) is not int or not 5 <= p <= 11 or p > k):
            raise ValueError("p must be between 5 and 11 and no greater than k")
        for name in ("ci", "cs", "cx", "n", "sf", "sp", "sr"):
            value = values.get(name)
            if value is not None and (type(value) is not int or value < 1):
                raise ValueError(f"{name} must be a positive integer")
        ci = values.get("ci")
        cx = values.get("cx")
        if isinstance(ci, int) and isinstance(cx, int) and ci > cx:
            raise ValueError("ci must be no greater than cx")

    def validate_resources(self, values: Mapping[str, object]) -> None:
        memory_mb = values.get("memory_mb")
        if type(memory_mb) is not int or not 2048 <= memory_mb <= 1048576:
            raise ValueError("memory_mb must be between 2048 and 1048576 for KMC")

    def run_from_args(self, args) -> int:
        """Count reference k-mers and write one KFF index."""
        output = Path(args.kmc_index_output)
        with TemporaryDirectory(
            prefix="asokai-kmc-",
            dir=Path.cwd(),
        ) as working_directory:
            KMC().run(
                args.reference,
                output,
                working_directory,
                k=args.k,
                m=args.memory_mb // 1024,
                f=args.f,
                t=args.n_workers,
                sm=args.sm,
                hc=args.hc,
                p=args.p,
                ci=args.ci,
                cs=args.cs,
                cx=args.cx,
                b=args.b,
                r=args.r,
                n=args.n,
                sf=args.sf,
                sp=args.sp,
                sr=args.sr,
                opt_out_size=args.opt_out_size,
                o="kff",
                hp=True,
                debug=False,
            )

        return 0
