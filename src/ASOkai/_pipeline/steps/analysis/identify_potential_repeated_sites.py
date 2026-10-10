#!/usr/bin/env python
"""
Filename: src/ASOkai/_pipeline/steps/analysis/identify_potential_repeated_sites.py
Authors: Arash Ayat, Kian Jalilian
Copyright: 2026, Alexander Schliep
Description: Definition of the identify-potential-repeated-sites step.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Mapping, cast

from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

from ASOkai.Analysis import SimilarSequenceAnalysis
from ASOkai.Analysis._similar_sequence import DEFAULT_ENERGY_PARAMETERS
from ASOkai._pipeline.contracts.file_types import FastaFile
from ASOkai._pipeline.contracts.files import FileInput, FileOutput
from ASOkai._pipeline.contracts.parameters import ScalarParam
from ASOkai._pipeline.contracts.paths import (
    OutputPathTemplate,
    TemplateField,
)
from ASOkai._pipeline.contracts.step_spec import StepSpec
from ASOkai._pipeline.steps.analysis.base import AnalysisStep
from ASOkai._pipeline.steps.core.create_target_gene import CreateTargetGeneStep

logger = logging.getLogger(__name__)


def _scalar(value: str) -> Any:
    """Return a model-argument value as an int or float when it is one."""
    for convert in (int, float):
        try:
            return convert(value)
        except ValueError:
            continue
    return value

_STEP_CONFIG = "parameters.analysis.potential_repeated_sites"

_PATH_FIELDS = {
    "assembly": TemplateField("parameters.genome.assembly"),
    "source": TemplateField("parameters.genome.source", default="ensembl"),
    "release": TemplateField("parameters.genome.release"),
    "target": TemplateField.first_of(
        "parameters.target.target_id",
        "parameters.target.target_name",
    ),
    "k": TemplateField("parameters.target.k"),
    "region": TemplateField("parameters.target.region"),
    "left": TemplateField("parameters.antisense.modality.design.left_wing_length"),
    "gap": TemplateField("parameters.antisense.modality.design.gap_length"),
    "right": TemplateField("parameters.antisense.modality.design.right_wing_length"),
    "max_ddg": TemplateField(f"{_STEP_CONFIG}.max_ddg", default=5.0),
    "tolerance": TemplateField(
        f"{_STEP_CONFIG}.ddg_tolerance",
        default=0.5,
    ),
}


class IdentifyPotentialRepeatedSitesStep(AnalysisStep):
    name = "identify-potential-repeated-sites"
    listed = False
    description = (
        "Searches potential repeated sites that each target site's own "
        "gapmer still binds."
    )
    analysis_cls = SimilarSequenceAnalysis
    target_gene_input = FileInput(
        "target_gene",
        source=CreateTargetGeneStep.target_gene_output,
        doc="Target gene whose sites are searched, from create-target-gene.",
    )
    potential_sites_output = FileOutput(
        "potential_repeated_sites",
        file_type=FastaFile(),
        destination=OutputPathTemplate(
            template=(
                "{assembly}/{source}/{release}/targets/{target}/"
                "analysis/repeated_sites/"
                "{target}_k{k}_{region}_gapmer_l{left}_g{gap}_r{right}_"
                "ddg{max_ddg}_tol{tolerance}_potential_repeated_sites.fa"
            ),
            fields=_PATH_FIELDS,
        ),
        doc=(
            "One FASTA record per potential repeated site, named by its "
            "target site and the substitutions applied to it."
        ),
    )
    spec = StepSpec(
        requirements={"WorkReuse": {"enableReuse": True}},
        params=[
            ScalarParam(
                "k",
                int,
                config="parameters.target.k",
                doc="Target-site length.",
            ),
            ScalarParam(
                "left_wing_length",
                int,
                config="parameters.antisense.modality.design.left_wing_length",
                doc="Nucleotides in the gapmer's left wing.",
            ),
            ScalarParam(
                "gap_length",
                int,
                config="parameters.antisense.modality.design.gap_length",
                doc="Nucleotides in the gapmer's central gap.",
            ),
            ScalarParam(
                "right_wing_length",
                int,
                config="parameters.antisense.modality.design.right_wing_length",
                doc="Nucleotides in the gapmer's right wing.",
            ),
            ScalarParam(
                "max_ddg",
                float,
                config=f"{_STEP_CONFIG}.max_ddg",
                default=5.0,
                doc="Largest reported binding-energy loss in kcal/mol.",
            ),
            ScalarParam(
                "ddg_tolerance",
                float,
                config=f"{_STEP_CONFIG}.ddg_tolerance",
                default=0.5,
                doc=(
                    "Extra binding-energy loss in kcal/mol that is still "
                    "explored but not reported."
                ),
            ),
            ScalarParam(
                "energy_parameters",
                str | None,
                config=f"{_STEP_CONFIG}.energy_parameters",
                default=None,
                doc=(
                    "Built-in ViennaRNA energy parameter set. The DNA sets "
                    "model a DNA duplex rather than the DNA-RNA hybrid a "
                    "gapmer forms, so they are an approximation too."
                ),
            ),
            ScalarParam(
                "energy_parameter_file",
                str | None,
                config=f"{_STEP_CONFIG}.energy_parameter_file",
                default=None,
                doc=(
                    "ViennaRNA parameter file to load instead of a named "
                    "set. It is read where it lies rather than staged, so a "
                    "run under CWL needs a path its job can reach."
                ),
            ),
            ScalarParam(
                "model_settings",
                str,
                config=f"{_STEP_CONFIG}.model_settings",
                default="",
                doc=(
                    "Extra ViennaRNA model arguments as comma-separated "
                    "name=value pairs, such as "
                    "'temperature=37.0,noGU=1'. Empty keeps every "
                    "ViennaRNA default."
                ),
            ),
        ],
        inputs=[target_gene_input],
        outputs=[potential_sites_output],
        compatible_with={
            "parameters.antisense.modality.type": ["aso"],
            "parameters.antisense.modality.mechanism": ["rnase-h1"],
            "parameters.antisense.modality.design.type": ["gapmer"],
        },
    )

    @staticmethod
    def _model_settings(value: str) -> dict[str, Any]:
        """Parse comma-separated name=value ViennaRNA model arguments."""
        settings: dict[str, Any] = {}
        for item in value.split(","):
            if not item.strip():
                continue
            name, separator, raw = item.partition("=")
            name = name.strip()
            if not separator or not name or not raw.strip():
                raise ValueError(
                    "model_settings must contain comma-separated name=value "
                    f"pairs; received {item.strip()!r}"
                )
            if name in settings:
                raise ValueError(f"model_settings repeats {name!r}")
            settings[name] = _scalar(raw.strip())
        return settings

    def validate_parameters(self, values: Mapping[str, object]) -> None:
        """Require a gapmer layout and energy parameters that can be used."""
        self._validate_energy_parameters(values)
        model_settings = values.get("model_settings")
        if isinstance(model_settings, str):
            self._model_settings(model_settings)
        for name in ("max_ddg", "ddg_tolerance"):
            value = values.get(name)
            if isinstance(value, (int, float)) and value < 0:
                raise ValueError(f"{name} must be non-negative")
        length_names = (
            "left_wing_length",
            "gap_length",
            "right_wing_length",
        )
        lengths = tuple(values.get(name) for name in length_names)
        if any(type(length) is not int or length < 1 for length in lengths):
            raise ValueError("gapmer segment lengths must be positive integers")
        target_site_length = values.get("k")
        if type(target_site_length) is not int:
            return
        design_length = sum(cast(tuple[int, int, int], lengths))
        if design_length != target_site_length:
            raise ValueError(
                "gapmer segment lengths must equal the target-site length "
                f"({target_site_length}); received {design_length}"
            )

    @staticmethod
    def _validate_energy_parameters(values: Mapping[str, object]) -> None:
        """Require one usable energy parameter selection."""
        named = values.get("energy_parameters", DEFAULT_ENERGY_PARAMETERS)
        parameter_file = values.get("energy_parameter_file")
        if parameter_file is None:
            return
        if named != DEFAULT_ENERGY_PARAMETERS:
            raise ValueError(
                "set either energy_parameters or energy_parameter_file, "
                "not both"
            )
        if not isinstance(parameter_file, str) or not parameter_file.strip():
            raise ValueError("energy_parameter_file must be a path")
        if not Path(parameter_file).expanduser().is_file():
            raise ValueError(
                f"energy_parameter_file is not a file: {parameter_file}"
            )

    def analysis_kwargs(self, args):
        """Build the search from the gapmer layout and energy thresholds."""
        return {
            "left_wing_length": args.left_wing_length,
            "gap_length": args.gap_length,
            "right_wing_length": args.right_wing_length,
            "max_ddg": args.max_ddg,
            "ddg_tolerance": args.ddg_tolerance,
            "model_settings": self._model_settings(args.model_settings),
            "energy_parameters": args.energy_parameters,
            "energy_parameter_file": args.energy_parameter_file,
        }

    def analysis_units(self, args):
        """Search every target site of the supplied target gene."""
        sites = args.target_gene.sites
        logger.info(
            "Searching %d target sites with %d worker(s); "
            "max_ddg=%s, ddg_tolerance=%s",
            len(sites),
            args.n_workers,
            args.max_ddg,
            args.ddg_tolerance,
        )
        return sites

    def write_results(self, args, analysis, results) -> None:
        """Write every result as one FASTA record named by its identifier."""
        with args.potential_repeated_sites_output.open(
            "w",
            encoding="utf-8",
        ) as stream:
            # The results stream in while the search runs, so they are counted
            # on the way past rather than measured up front.
            written = SeqIO.write(
                (
                    SeqRecord(Seq(sequence), id=identifier, description="")
                    for identifier, sequence in results
                ),
                stream,
                "fasta",
            )
        logger.info("Wrote %d potential repeated sites", written)
