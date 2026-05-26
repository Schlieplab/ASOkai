"""
Filename: src/pipeline/steps/download_genome.py
Description: Definition and CLI entrypoint for the download-genome step.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from importlib.resources import files
from GenomeUtils.Downloaders import EnsemblGenomeDownloader


class DownloadGenomeStep:
    name = "download-genome"
    description = "[core] Downloads genome DNA (primary assembly FASTA), cDNA (FASTA), and annotation (GTF)."
    cli_module = "pipeline.steps.download_genome"
    dependencies: list[str] = []
    config_map = {
        "assembly": "genome.assembly_id",
        "release":  "genome.ensembl_release",
        "source":   "genome.source",
        "species":  "genome.species",
    }
    input_overrides: dict[str, str] = {}

    @property
    def cwl_path(self) -> str:
        return str(files("cwl.steps").joinpath("download-genome.cwl"))


    def outdir(self, config: dict) -> Path:
        return (
            Path(config["datadir"])
            / config["genome"]["assembly_id"]
            / "genomes"
            / config["genome"]["source"]
            / str(config["genome"]["ensembl_release"])
        )

    def output_paths(self, config: dict) -> dict[str, Path]:
        base = self.outdir(config)
        parts = config["genome"]["species"].split("_")
        species_cap = parts[0].capitalize() + "_" + "_".join(p.lower() for p in parts[1:])
        assembly = config["genome"]["assembly_id"]
        release = config["genome"]["ensembl_release"]
        return {
            "dna":        base / f"{species_cap}.{assembly}.dna.primary_assembly.fa.gz",
            "cdna":       base / f"{species_cap}.{assembly}.cdna.all.fa.gz",
            "annotation": base / f"{species_cap}.{assembly}.{release}.gtf.gz",
        }

    def outputs_exist(self, config: dict) -> bool:
        return all(p.exists() for p in self.output_paths(config).values())

    def cleanup(self, config: dict) -> None:
        for p in self.output_paths(config).values():
            if p.exists():
                p.unlink()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download genome DNA, cDNA, and GTF.",
    )
    parser.add_argument("--assembly", required=True, help="Assembly ID (e.g. GRCh38).")
    parser.add_argument("--release", required=True, type=int, help="Ensembl release number.")
    parser.add_argument("--source", required=True, help="Genome data source.")
    parser.add_argument("--species", required=True, help="Species name (e.g. homo_sapiens).")
    parser.add_argument("--outdir", required=True, type=Path, help="Root directory for downloaded genomes.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint called by CWL baseCommand: download-genome."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.source != "ensembl":
        parser.error(f"Unsupported genome source: {args.source}")

    downloader = EnsemblGenomeDownloader(
        assembly_id=args.assembly,
        ensembl_release=args.release,
        species=args.species.lower().replace(" ", "_"),
        genomes_root_dir=args.outdir,
    )
    paths = downloader.download(force=True)

    for key in ("dna", "cdna", "annotation"):
        print(f"{key}\t{paths[key]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
