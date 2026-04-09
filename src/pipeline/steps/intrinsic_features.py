"""
Filename: src/ASOkai/pipeline/steps/intrinsic_features.py
Description: Definition and CLI entrypoint for the intrinsic-features step.
License: LGPL-3.0-or-later
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from importlib.resources import files


class IntrinsicFeaturesStep:
    name = "intrinsic-features"
    description = "[analysis] Computes intrinsic features (GC content, T-runs, AT-runs) for each ASO target site."
    dependencies: list[str] = ["create-target-gene"]
    config_map = {
        "target_id":   "target.target_id",
        "target_name": "target.target_name",
        "k":           "target.k",
        "assembly":    "genome.assembly_id",
    }

    @property
    def cwl_path(self) -> str:
        return str(files("cwl.steps").joinpath("intrinsic-features.cwl"))

    def _effective_target_id(self, config: dict) -> str:
        return config["target"].get("target_id") or config["target"].get("target_name")

    def _analysis_dir(self, config: dict) -> Path:
        return (
            Path(config["datadir"])
            / "analysis"
            / "intrinsic"
            / self._effective_target_id(config)
        )

    def outdir(self, config: dict) -> Path:
        return self._analysis_dir(config)

    def output_paths(self, config: dict) -> dict[str, Path]:
        base = self._analysis_dir(config)
        target_id = self._effective_target_id(config)
        assembly = config["genome"]["assembly_id"]
        return {
            "intrinsic_features": base / f"{assembly}_{target_id}_intrinsic.json",
        }

    def outputs_exist(self, config: dict) -> bool:
        return all(p.exists() for p in self.output_paths(config).values())

    def cleanup(self, config: dict) -> None:
        for p in self.output_paths(config).values():
            if p.exists():
                p.unlink()


def main() -> int:
    """CLI entrypoint called by CWL baseCommand: intrinsic-features."""
    parser = argparse.ArgumentParser(
        description="Compute intrinsic features for ASO target sites.",
    )
    parser.add_argument("--target-gene", required=True, type=Path, help="Path to target gene JSON.")
    parser.add_argument("--assembly", required=True, help="Assembly ID (e.g. GRCh38).")
    parser.add_argument("--target-id", default=None, help="Ensembl gene ID. Takes priority over --target-name.")
    parser.add_argument("--target-name", default=None, help="Gene name. Used if --target-id is not provided.")
    parser.add_argument("--outdir", required=True, type=Path, help="Output directory.")

    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    if not args.target_id and not args.target_name:
        parser.error("Either --target-id or --target-name is required.")

    effective_id = args.target_id or args.target_name
    output_path = args.outdir / f"{args.assembly}_{effective_id}_intrinsic.json"

    # TODO: wire IntrinsicFeaturesAnalysis here
    raise NotImplementedError("intrinsic-features script not yet implemented.")


if __name__ == "__main__":
    sys.exit(main())
