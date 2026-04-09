"""
Filename: src/ASOkai/pipeline/steps/download_genome.py
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
    description = "[core] Downloads genome DNA (primary assembly FASTA), cDNA (FASTA), and annotation (GTF) from Ensembl FTP."
    dependencies: list[str] = []
    config_map = {
        "assembly": "genome.assembly_id",
        "release":  "genome.ensembl_release",
        "species":  "genome.species",
    }

    @property
    def cwl_path(self) -> str:
        return str(files("cwl.steps").joinpath("download-genome.cwl"))

    def _genome_dir(self, config: dict) -> Path:
        return (
            Path(config["datadir"])
            / "genomes"
            / "ensembl"
            / config["genome"]["assembly_id"]
            / str(config["genome"]["ensembl_release"])
        )

    def outdir(self, config: dict) -> Path:
        return self._genome_dir(config)

    def output_paths(self, config: dict) -> dict[str, Path]:
        base = self._genome_dir(config)
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
        """Remove outputs before a forced re-run."""
        import shutil
        for p in self.output_paths(config).values():
            if p.exists():
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()


def main() -> int:
    """CLI entrypoint called by CWL baseCommand: download-genome."""
    parser = argparse.ArgumentParser(
        description="Download genome DNA, cDNA, and GTF from Ensembl.",
    )
    parser.add_argument("--assembly", required=True, help="Assembly ID (e.g. GRCh38).")
    parser.add_argument("--release", required=True, type=int, help="Ensembl release number.")
    parser.add_argument("--species", required=True, help="Species name (e.g. homo_sapiens).")
    parser.add_argument("--outdir", required=True, type=Path, help="Root directory for downloaded genomes.")

    args = parser.parse_args()

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
