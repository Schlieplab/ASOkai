"""Tests for StandardWorkflow."""
import pytest
from pipeline.workflows.standard import StandardWorkflow
from pipeline.base import Runnable, Workflow, Step, Task
from pipeline.plan import _flatten_runnable


@pytest.fixture
def config(tmp_path):
    return {
        "datadir": str(tmp_path),
        "genome": {
            "assembly_id":    "GRCh38",
            "ensembl_release": 114,
            "source":         "ensembl",
            "species":        "Homo_sapiens",
        },
        "target": {
            "target_id":   "ENSG00000133703",
            "target_name": "KRAS",
            "k":           16,
            "region":      "pre-mrna",
        },
    }


@pytest.fixture
def workflow():
    return StandardWorkflow()


def test_name(workflow):
    assert workflow.name == "standard"


def test_implements_runnable(workflow):
    assert isinstance(workflow, Runnable)


def test_implements_workflow_protocol(workflow):
    assert isinstance(workflow, Workflow)


def test_members_are_runnables(workflow):
    assert all(isinstance(m, Runnable) for m in workflow.members)
    assert isinstance(workflow.members[0], Task)
    assert isinstance(workflow.members[1], Step)


def test_member_names(workflow):
    assert [m.name for m in workflow.members] == [
        "instantiate-target-gene",
        "intrinsic-features",
    ]


def test_flattens_to_step_names(workflow):
    assert [s.name for s in _flatten_runnable(workflow)] == [
        "download-genome",
        "create-target-gene",
        "intrinsic-features",
    ]


def test_output_paths(workflow, config, tmp_path):
    paths = workflow.output_paths(config)
    target_base = tmp_path / "GRCh38" / "targets" / "ENSG00000133703"
    assert paths["target_gene"] == target_base / "ENSG00000133703_k16_pre-mrna.json"
    assert paths["intrinsic_features"] == (
        target_base / "analysis" / "intrinsic" / "ENSG00000133703_k16_pre-mrna_intrinsic.json"
    )


def test_outputs_do_not_exist(workflow, config):
    assert workflow.outputs_exist(config) is False


def test_outputs_exist(workflow, config, tmp_path):
    for p in workflow.output_paths(config).values():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
    assert workflow.outputs_exist(config) is True


def test_cleanup(workflow, config, tmp_path):
    for p in workflow.output_paths(config).values():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
    workflow.cleanup(config)
    assert workflow.outputs_exist(config) is False
