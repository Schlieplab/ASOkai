#!/usr/bin/env python
"""Tests for generated top-level runtime CWLs."""
from pathlib import Path
import shutil
import subprocess
from typing import ClassVar

import pytest
import yaml

from ASOkai._cwl.generation import generate_cwl_bundle
from ASOkai._cwl.spec import (
    InputParam,
    OutputParam,
    ScalarParam,
    StepCwlGenerator,
    StepSpec,
)
from ASOkai._pipeline.base import Step
from ASOkai._pipeline.registry import get_steps


class _SpecStep(Step):
    name = "test-step"
    description = "Test step."
    cli_module = "tests.fake_step"
    dependencies: ClassVar[list[str]] = []
    spec = StepSpec()

    def outputs_exist(self, config):
        return False

    def cleanup(self, config):
        pass


def _spec_step(
    name: str,
    spec: StepSpec,
    *,
    dependencies: list[str] | None = None,
) -> Step:
    """Return an isolated Step subclass configured with class-level metadata."""

    class ConfiguredSpecStep(_SpecStep):
        pass

    ConfiguredSpecStep.name = name
    ConfiguredSpecStep.spec = spec
    ConfiguredSpecStep.dependencies = list(dependencies or [])
    return ConfiguredSpecStep()


def _generate_run_cwl(
    steps: list[Step],
    pre_resolved: dict[str, Path],
    config: dict,
) -> str:
    return generate_cwl_bundle(steps, pre_resolved, config).run_cwl


@pytest.fixture
def workflow_config(tmp_path):
    return {
        "datadir": str(tmp_path),
        "genome": {
            "assembly_id": "GRCh38",
            "ensembl_release": 114,
            "source": "ensembl",
            "species": "Homo_sapiens",
        },
        "target": {
            "target_id": "ENSG00000133703",
            "target_name": "KRAS",
            "k": 16,
            "region": "pre-mrna",
        },
    }


def test_generate_cwl_wires_download_outputs_into_create_target_gene(workflow_config):
    from ASOkai._pipeline.steps.create_target_gene import CreateTargetGeneStep
    from ASOkai._pipeline.steps.download_genome import DownloadGenomeStep

    doc = yaml.safe_load(
        _generate_run_cwl(
            [DownloadGenomeStep(), CreateTargetGeneStep()],
            {},
            workflow_config,
        )
    )

    create_inputs = doc["steps"]["step_create_target_gene"]["in"]
    assert create_inputs["dna"] == "step_download_genome/dna"
    assert create_inputs["cdna"] == "step_download_genome/cdna"
    assert create_inputs["annotation"] == "step_download_genome/annotation"
    assert create_inputs["db"] == "step_download_genome/db"


def test_generate_cwl_does_not_expose_derived_output_filenames_as_inputs(
    workflow_config,
):
    from ASOkai._pipeline.steps.create_target_gene import CreateTargetGeneStep
    from ASOkai._pipeline.steps.download_genome import DownloadGenomeStep

    doc = yaml.safe_load(
        _generate_run_cwl(
            [DownloadGenomeStep(), CreateTargetGeneStep()],
            {},
            workflow_config,
        )
    )

    download_inputs = doc["steps"]["step_download_genome"]["in"]
    assert "dna_output" not in download_inputs
    assert "cdna_output" not in download_inputs
    assert "annotation_output" not in download_inputs
    assert "dna_output" not in doc["inputs"]


def test_generate_cwl_uses_declared_step_input_types(workflow_config):
    from ASOkai._pipeline.steps.create_target_gene import CreateTargetGeneStep
    from ASOkai._pipeline.steps.download_genome import DownloadGenomeStep

    doc = yaml.safe_load(
        _generate_run_cwl(
            [DownloadGenomeStep(), CreateTargetGeneStep()],
            {},
            workflow_config,
        )
    )

    assert doc["inputs"]["release"] == "int"
    assert doc["inputs"]["k"] == "int"
    assert doc["inputs"]["region"]["type"]["type"] == "enum"


def test_generate_cwl_pre_resolved_dependency_outputs_are_file_inputs(tmp_path):
    from ASOkai._pipeline.steps.create_target_gene import CreateTargetGeneStep

    config = {
        "datadir": str(tmp_path),
        "genome": {
            "assembly_id": "GRCh38",
            "ensembl_release": 114,
            "source": "ensembl",
            "species": "Homo_sapiens",
        },
        "target": {
            "target_id": "ENSG00000133703",
            "target_name": "KRAS",
            "k": 16,
            "region": "pre-mrna",
        },
    }

    doc = yaml.safe_load(
        _generate_run_cwl(
            [CreateTargetGeneStep()],
            {"dna": tmp_path / "dna.fa.gz", "cdna": tmp_path / "cdna.fa.gz"},
            config,
        )
    )

    assert doc["inputs"]["dna"] == "File"
    assert doc["inputs"]["cdna"] == "File"
    assert doc["steps"]["step_create_target_gene"]["in"]["dna"] == "dna"
    assert doc["steps"]["step_create_target_gene"]["in"]["cdna"] == "cdna"


def test_generate_cwl_input_overrides_keep_declared_file_types_when_not_wired(workflow_config):
    from ASOkai._pipeline.steps.create_target_gene import CreateTargetGeneStep

    doc = yaml.safe_load(_generate_run_cwl([CreateTargetGeneStep()], {}, workflow_config))

    assert doc["inputs"]["dna"] == "File"
    assert doc["inputs"]["cdna"] == "File"
    assert doc["inputs"]["annotation"] == "File"
    assert doc["inputs"]["db"] == "File"


def test_generate_cwl_publishes_every_step_output_under_data_roots(workflow_config):
    from ASOkai._pipeline.steps.create_target_gene import CreateTargetGeneStep
    from ASOkai._pipeline.steps.download_genome import DownloadGenomeStep

    doc = yaml.safe_load(
        _generate_run_cwl(
            [DownloadGenomeStep(), CreateTargetGeneStep()],
            {},
            workflow_config,
        )
    )

    assert set(doc["outputs"]) == {"published_GRCh38"}
    assert doc["outputs"]["published_GRCh38"] == {
        "type": "Directory",
        "outputSource": "publish_outputs/published_GRCh38",
    }
    assert doc["steps"]["publish_outputs"]["in"]["files"]["source"] == [
        "step_download_genome/dna",
        "step_download_genome/cdna",
        "step_download_genome/annotation",
        "step_download_genome/db",
        "step_create_target_gene/target_gene",
    ]
    assert doc["steps"]["publish_outputs"]["in"]["files"]["linkMerge"] == (
        "merge_flattened"
    )
    assert set(doc["steps"]).isdisjoint(doc["outputs"])


def test_generate_cwl_bundle_contains_every_required_document(workflow_config):
    from ASOkai._pipeline.steps.create_target_gene import CreateTargetGeneStep
    from ASOkai._pipeline.steps.download_genome import DownloadGenomeStep

    generated = generate_cwl_bundle(
        [DownloadGenomeStep(), CreateTargetGeneStep()],
        {},
        workflow_config,
    )
    publisher = yaml.safe_load(generated.publish_cwl)
    layout = yaml.safe_load(generated.output_layout)

    assert publisher["baseCommand"] == ["ASOkai", "publish-outputs"]
    assert publisher["inputs"]["files"]["type"] == {
        "type": "array",
        "items": "File",
    }
    assert publisher["outputs"]["published_GRCh38"] == {
        "type": "Directory",
        "outputBinding": {"glob": "published/GRCh38"},
    }
    assert "InlineJavascriptRequirement" not in publisher.get("requirements", {})
    assert layout["outputs"][0] == {
        "id": "step_download_genome__dna",
        "destination": (
            "GRCh38/genomes/ensembl/114/"
            "Homo_sapiens.GRCh38.dna.primary_assembly.fa.gz"
        ),
    }
    assert set(generated.step_cwls) == {
        "download-genome.cwl",
        "create-target-gene.cwl",
    }


def test_generate_cwl_normalizes_step_ids_with_underscores(workflow_config):
    from ASOkai._pipeline.steps.create_target_gene import CreateTargetGeneStep
    from ASOkai._pipeline.steps.download_genome import DownloadGenomeStep

    doc = yaml.safe_load(
        _generate_run_cwl(
            [DownloadGenomeStep(), CreateTargetGeneStep()],
            {},
            workflow_config,
        )
    )

    assert "step_download_genome" in doc["steps"]
    assert "step_create_target_gene" in doc["steps"]


def test_generate_cwl_references_generated_step_files(workflow_config):
    from ASOkai._pipeline.steps.create_target_gene import CreateTargetGeneStep
    from ASOkai._pipeline.steps.download_genome import DownloadGenomeStep

    doc = yaml.safe_load(
        _generate_run_cwl(
            [DownloadGenomeStep(), CreateTargetGeneStep()],
            {},
            workflow_config,
        )
    )

    assert doc["steps"]["step_download_genome"]["run"] == "steps/download-genome.cwl"
    assert doc["steps"]["step_create_target_gene"]["run"] == "steps/create-target-gene.cwl"


def test_registered_step_output_paths_define_names(workflow_config):
    for step in get_steps().values():
        assert tuple(step.output_paths(workflow_config).keys())


def test_registered_step_specs_cover_config_and_output_keys(workflow_config):
    for step in get_steps().values():
        input_names = step.cwl_spec.input_names()
        output_names = step.cwl_spec.output_names()

        assert set(step.config_map).issubset(input_names)
        assert set(step.input_overrides).issubset(input_names)
        assert set(step.output_paths(workflow_config)) == output_names


def test_generate_cwl_rejects_conflicting_shared_input_types(tmp_path):
    first = _spec_step(
        "first",
        StepSpec(
            params=[ScalarParam("shared", str, config="first.shared")],
            outputs=[
                OutputParam("first_result", temp_filename="first_result.txt")
            ],
        ),
    )
    second = _spec_step(
        "second",
        StepSpec(
            params=[ScalarParam("shared", int, config="second.shared")],
            outputs=[
                OutputParam("second_result", temp_filename="second_result.txt")
            ],
        ),
    )

    with pytest.raises(ValueError, match="conflicting CWL types"):
        _generate_run_cwl([first, second], {}, {"datadir": str(tmp_path)})


def test_generate_cwl_does_not_wire_undeclared_dependency_outputs(tmp_path):
    producer = _spec_step(
        "producer",
        StepSpec(outputs=[OutputParam("unused", temp_filename="unused.txt")]),
    )
    consumer = _spec_step(
        "consumer",
        StepSpec(outputs=[OutputParam("result", temp_filename="result.txt")]),
        dependencies=["producer"],
    )

    doc = yaml.safe_load(
        _generate_run_cwl([producer, consumer], {}, {"datadir": str(tmp_path)})
    )

    assert "unused" not in doc["steps"]["step_consumer"]["in"]
    assert "unused" not in doc["inputs"]


def test_generate_cwl_rejects_duplicate_temp_filenames(tmp_path):
    first = _spec_step(
        "first",
        StepSpec(outputs=[OutputParam("shared", temp_filename="shared.txt")]),
    )
    second = _spec_step(
        "second",
        StepSpec(outputs=[OutputParam("shared", temp_filename="shared.txt")]),
    )

    with pytest.raises(ValueError, match="temporary filename 'shared.txt'.*both"):
        _generate_run_cwl([first, second], {}, {"datadir": str(tmp_path)})


@pytest.mark.skipif(shutil.which("cwltool") is None, reason="cwltool is not installed")
def test_generated_registered_tools_and_workflow_validate_with_cwltool(
    workflow_config,
    tmp_path,
):
    steps = list(get_steps().values())
    steps_dir = tmp_path / "steps"
    steps_dir.mkdir()
    generator = StepCwlGenerator()
    for step in steps:
        (steps_dir / f"{step.name}.cwl").write_text(generator.render(step))

    generated = generate_cwl_bundle(steps, {}, workflow_config)
    run_path = tmp_path / "run.cwl"
    run_path.write_text(generated.run_cwl)
    (tmp_path / "publish.cwl").write_text(generated.publish_cwl)
    (tmp_path / "output-layout.yml").write_text(generated.output_layout)

    result = subprocess.run(
        ["cwltool", "--validate", str(run_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
