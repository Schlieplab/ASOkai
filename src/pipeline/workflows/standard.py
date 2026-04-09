"""
Filename: src/ASOkai/pipeline/workflows/standard.py
Description: Standard ASOkai workflow definition.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

from pathlib import Path
from importlib.resources import files


class StandardWorkflow:
    name = "standard"
    description = "Full ASOkai pipeline: genome download, target gene creation, and intrinsic features analysis."
    dependencies: list[str] = []
    config_map = {
        "assembly":    "genome.assembly_id",
        "release":     "genome.ensembl_release",
        "species":     "genome.species",
        "target_id":   "target.target_id",
        "target_name": "target.target_name",
        "k":           "target.k",
        "region":      "target.region",
    }

    @property
    def cwl_path(self) -> str:
        return str(files("cwl.workflows").joinpath("standard.cwl"))

    def outdir(self, config: dict) -> Path:
        return Path(config["datadir"]).resolve()

    def _effective_target_id(self, config: dict) -> str:
        return config["target"].get("target_id") or config["target"].get("target_name")

    def output_paths(self, config: dict) -> dict[str, Path]:
        target_id = self._effective_target_id(config)
        assembly = config["genome"]["assembly_id"]
        target_dir = Path(config["datadir"]) / "targets" / "gene" / target_id
        analysis_dir = Path(config["datadir"]) / "analysis" / "intrinsic" / target_id
        return {
            "target_gene":        target_dir / f"{assembly}_{target_id}.json",
            "intrinsic_features": analysis_dir / f"{assembly}_{target_id}_intrinsic.json",
        }

    def outputs_exist(self, config: dict) -> bool:
        return all(p.exists() for p in self.output_paths(config).values())

    def cleanup(self, config: dict) -> None:
        for p in self.output_paths(config).values():
            if p.exists():
                p.unlink()
