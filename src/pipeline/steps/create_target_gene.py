"""
Filename: src/pipeline/steps/create_target_gene.py
Description: Definition and CLI entrypoint for the create-target-gene step.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from importlib.resources import files


class CreateTargetGeneStep:
    name = "create-target-gene"
    description = "[core] Creates a target gene object from genome data and extracts ASO target sites."
    cli_module = "pipeline.steps.create_target_gene"
    dependencies: list[str] = ["download-genome"]
    config_map = {
        "target_id":   "target.target_id",
        "target_name": "target.target_name",
        "k":           "target.k",
        "region":      "target.region",
        "assembly":    "genome.assembly_id",
        "release":     "genome.ensembl_release",
        "species":     "genome.species",
    }
    input_overrides: dict[str, str] = {
        "dna":        "genome.dna_path",
        "cdna":       "genome.cdna_path",
        "annotation": "genome.annotation_path",
    }

    @property
    def cwl_path(self) -> str:
        return str(files("cwl.steps").joinpath("create-target-gene.cwl"))

    def _effective_target_id(self, config: dict) -> str:
        """Return target_id if present, fall back to target_name."""
        return (
            config["target"].get("target_id")
            or config["target"].get("target_name")
        )

    def _target_dir(self, config: dict) -> Path:
        assembly = config["genome"]["assembly_id"]
        target_id = self._effective_target_id(config)
        return Path(config["datadir"]) / assembly / "targets" / target_id

    def outdir(self, config: dict) -> Path:
        return self._target_dir(config)

    def output_paths(self, config: dict) -> dict[str, Path]:
        base = self._target_dir(config)
        target_id = self._effective_target_id(config)
        k = config["target"]["k"]
        region = config["target"]["region"]
        return {
            "target_gene": base / f"{target_id}_k{k}_{region}.json",
        }

    def outputs_exist(self, config: dict) -> bool:
        return all(p.exists() for p in self.output_paths(config).values())

    def cleanup(self, config: dict) -> None:
        for p in self.output_paths(config).values():
            if p.exists():
                p.unlink()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a target gene object and extract ASO target sites.",
    )
    parser.add_argument("--target-id",   default=None, help="Ensembl gene ID (e.g. ENSG00000133703). Takes priority over --target-name.")
    parser.add_argument("--target-name", default=None, help="Gene name (e.g. KRAS). Used if --target-id is not provided.")
    parser.add_argument("--k",           required=True, type=int, help="ASO length.")
    parser.add_argument("--region",      required=True, choices=["exonic_only", "pre-mrna", "transcriptomic"], help="Target region type.")
    parser.add_argument("--dna",         required=True, type=Path, help="Path to primary assembly FASTA.")
    parser.add_argument("--cdna",        required=True, type=Path, help="Path to cDNA FASTA.")
    parser.add_argument("--annotation",  required=True, type=Path, help="Path to GTF annotation file.")
    parser.add_argument("--assembly",    required=True, help="Assembly ID (e.g. GRCh38).")
    parser.add_argument("--release",     required=True, type=int, help="Ensembl release number.")
    parser.add_argument("--species",     required=True, help="Species name (e.g. Homo_sapiens).")
    parser.add_argument("--output",      required=True, type=Path, help="Full path for the output JSON file.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint called by CWL baseCommand: create-target-gene."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    if not args.target_id and not args.target_name:
        parser.error("Either --target-id or --target-name is required.")

    from GenomeUtils.Genome import GenomeBuilder
    from ASOkai.Targets import TargetGeneCreator

    genome, _ = (
        GenomeBuilder(
            id=args.assembly,
            species=args.species.replace("_", " "),
            name=args.assembly,
        )
        .with_dna_fasta(args.dna)
        .with_cdna_fasta(args.cdna)
        .with_gtf_file(args.annotation)
        .build()
    )

    target_gene = TargetGeneCreator.from_genome(
        genome,
        target_id=args.target_id,
        target_name=args.target_name,
        k=args.k,
        region=args.region,
    )

    target_gene.to_file(str(args.output))

    return 0


if __name__ == "__main__":
    sys.exit(main())
