#!/usr/bin/env python
"""
Filename: tests/unit/test_identify_potential_repeated_sites.py
Author: Kian Jalilian
Copyright: 2026, Alexander Schliep
Description: Tests for the similar-sequence search and its pipeline step.
License: LGPL-3.0-or-later
"""

from pathlib import Path
from types import SimpleNamespace

from Bio import SeqIO
from Bio.Seq import Seq
import pytest

from ASOkai.Analysis import SimilarSequenceAnalysis
from ASOkai.Analysis._similar_sequence import (
    DEFAULT_ENERGY_PARAMETERS,
    _gapmer_core_positions,
    _load_energy_parameters,
    _mfe,
    _model_details,
    _parse_similar_sequence_id,
    _rebuild_sequence,
    _similar_sequence_id,
)
from ASOkai.Sites import GenomicSite
from ASOkai.Targets import TargetGene
from ASOkai._pipeline.steps.analysis.identify_potential_repeated_sites import (
    IdentifyPotentialRepeatedSitesStep,
)
from ASOkai._pipeline.steps.core.create_target_gene import (
    CreateTargetGeneStep,
)

GENE_SEQUENCE = "ATGACTGAATATAAACTTGTGGTAGTTGGAGCTGGTGGCG"
LAYOUT = (3, 10, 3)


def _sites() -> dict[str, GenomicSite]:
    sites = {}
    for start in (1, 11):
        site = GenomicSite(
            "12",
            start,
            start + 15,
            "+",
            Seq(GENE_SEQUENCE[start - 1 : start + 15]),
        )
        sites[site.id] = site
    return sites


def test_folding_a_perfect_duplex_releases_energy() -> None:
    site = GENE_SEQUENCE[:16]
    strand = str(Seq(site).reverse_complement())
    model_details = _model_details({})

    duplex = _mfe(f"{site}&{strand}", model_details)

    assert duplex < _mfe(site, model_details) + _mfe(strand, model_details)


def test_extra_model_arguments_reach_viennarna() -> None:
    site = GENE_SEQUENCE[:16]
    duplex = f"{site}&{Seq(site).reverse_complement()}"

    cold = _mfe(duplex, _model_details({"temperature": 10.0}))
    warm = _mfe(duplex, _model_details({"temperature": 60.0}))

    # Duplexes are less stable when warmer, so the energy rises.
    assert cold < warm


def test_analysis_rejects_an_unknown_model_argument() -> None:
    with pytest.raises(ValueError, match="Unknown ViennaRNA model setting"):
        SimilarSequenceAnalysis(*LAYOUT, model_settings={"nonsense": 1})


def test_an_unsatisfiable_constraint_is_an_error() -> None:
    # ViennaRNA reports an impossible constraint as a huge placeholder energy
    # rather than failing, so _mfe turns that into an error.
    impossible = "...." + "|" * 8 + "....&...." + "|" * 8 + "...."
    with pytest.raises(ValueError, match="cannot be satisfied"):
        _mfe(
            "GGGGAAAACCCCAAAA&TTTTGGTTTTTTCCCC",
            _model_details({}),
            impossible,
        )


def test_step_parses_model_settings_as_name_value_pairs() -> None:
    parse = IdentifyPotentialRepeatedSitesStep()._model_settings

    assert parse("temperature=37.0,noGU=1") == {
        "temperature": 37.0,
        "noGU": 1,
    }
    assert parse("") == {}
    with pytest.raises(ValueError, match="name=value"):
        parse("temperature")
    with pytest.raises(ValueError, match="repeats"):
        parse("noGU=1,noGU=0")


def test_named_energy_parameter_sets_change_the_folding_energies() -> None:
    duplex = f"{GENE_SEQUENCE[:16]}&{Seq(GENE_SEQUENCE[:16]).reverse_complement()}"

    # Model details bind the loaded parameters when first folded with, so
    # each measurement builds its own, exactly as analyze_unit does.
    _load_energy_parameters("RNA_Turner2004", None)
    rna = _mfe(duplex, _model_details({}))
    _load_energy_parameters("DNA_Mathews2004", None)
    dna = _mfe(duplex, _model_details({}))
    _load_energy_parameters(DEFAULT_ENERGY_PARAMETERS, None)

    assert rna != dna


def test_a_parameter_file_can_replace_the_named_set(tmp_path: Path) -> None:
    import RNA

    parameter_file = tmp_path / "custom.par"
    RNA.params_save(str(parameter_file))

    _load_energy_parameters(DEFAULT_ENERGY_PARAMETERS, parameter_file)

    assert parameter_file.is_file()


def test_loading_an_unknown_named_set_is_an_error() -> None:
    # ViennaRNA itself decides which sets exist, so no list is duplicated here.
    with pytest.raises(ValueError, match="Unknown energy parameter set"):
        _load_energy_parameters("Bogus", None)


def test_loading_no_named_set_keeps_the_viennarna_default() -> None:
    _load_energy_parameters(None, None)


def test_loading_an_unreadable_parameter_file_is_an_error(tmp_path: Path) -> None:
    # The step validates the selection, so the loader only reports what
    # ViennaRNA itself refuses.
    with pytest.raises(ValueError, match="could not read the parameter file"):
        _load_energy_parameters(
            DEFAULT_ENERGY_PARAMETERS,
            tmp_path / "missing.par",
        )


def test_step_rejects_an_unusable_energy_parameter_selection() -> None:
    step = IdentifyPotentialRepeatedSitesStep()
    base = {
        "k": 16,
        "left_wing_length": 3,
        "gap_length": 10,
        "right_wing_length": 3,
        "max_ddg": 1.0,
        "ddg_tolerance": 0.5,
        "model_settings": "",
        "energy_parameters": DEFAULT_ENERGY_PARAMETERS,
        "energy_parameter_file": None,
    }

    step.validate_parameters(base)
    with pytest.raises(ValueError, match="not both"):
        step.validate_parameters(
            {**base, "energy_parameters": "DNA_Mathews2004",
             "energy_parameter_file": "/tmp/custom.par"}
        )
    with pytest.raises(ValueError, match="is not a file"):
        step.validate_parameters(
            {**base, "energy_parameter_file": "/tmp/definitely-missing.par"}
        )


def test_core_positions_follow_the_gapmer_gap() -> None:
    # The gapmer is antiparallel, so its 5' left wing covers the site's 3' end.
    assert _gapmer_core_positions(10, 4) == range(4, 14)
    assert _gapmer_core_positions(10, 3) == range(3, 13)


def test_step_rejects_a_layout_that_misses_the_target_site_length() -> None:
    with pytest.raises(ValueError, match="must equal the target-site length"):
        IdentifyPotentialRepeatedSitesStep().validate_parameters(
            {
                "k": 16,
                "left_wing_length": 3,
                "gap_length": 10,
                "right_wing_length": 4,
                "max_ddg": 1.0,
                "ddg_tolerance": 0.5,
                "model_settings": "",
            }
        )


def test_identifiers_round_trip() -> None:
    site = GENE_SEQUENCE[:16]
    mutations = ((0, "G"), (13, "T"))

    identifier = _similar_sequence_id("site:12:1-16,+", mutations)

    assert identifier == "site:12:1-16,+&n2_m1G_m14T"
    assert _parse_similar_sequence_id(identifier) == (
        "site:12:1-16,+",
        mutations,
    )
    assert _rebuild_sequence(site, mutations) == "GTGACTGAATATATAC"


def test_identifier_accepts_a_full_genomic_site_id() -> None:
    # Real site IDs carry the assembly, locus, and strand, so they contain
    # the colons and hyphens the identifier suffix must survive.
    site_id = "site:GRCh38:12:25250719-25250734:-"
    mutations = ((0, "G"), (13, "G"))

    identifier = _similar_sequence_id(site_id, mutations)

    assert identifier == f"{site_id}&n2_m1G_m14G"
    assert _parse_similar_sequence_id(identifier) == (site_id, mutations)


def test_identifier_of_the_unmutated_site_has_no_groups() -> None:
    identifier = _similar_sequence_id("site:12:1-16,+", ())

    assert identifier == "site:12:1-16,+&n0"
    assert _parse_similar_sequence_id(identifier) == ("site:12:1-16,+", ())


def test_identifier_rejects_a_wrong_substitution_count() -> None:
    with pytest.raises(ValueError, match="declares 3 substitution"):
        _parse_similar_sequence_id("site:1&n3_m1G")

    with pytest.raises(ValueError, match="Malformed"):
        _parse_similar_sequence_id("site:1&m1G")


def test_search_returns_identifier_and_sequence_pairs() -> None:
    sites = list(_sites().values())
    analysis = SimilarSequenceAnalysis(*LAYOUT, max_ddg=1.0)

    results = analysis.run(sites, n_workers=1)

    by_site = {site.id: str(site.sequence) for site in sites}
    assert all(
        isinstance(result, tuple) and len(result) == 2 for result in results
    )
    assert len({identifier for identifier, _ in results}) == len(results)
    references = 0
    for identifier, sequence in results:
        site_id, mutations = _parse_similar_sequence_id(identifier)
        site_sequence = by_site[site_id]
        assert _rebuild_sequence(site_sequence, mutations) == sequence
        # Only positions outside the gapmer gap may change.
        assert sequence[3:13] == site_sequence[3:13]
        references += not mutations
    assert references == len(sites)


def test_search_rejects_negative_thresholds() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        SimilarSequenceAnalysis(*LAYOUT, max_ddg=-1.0)


def test_search_result_does_not_depend_on_the_worker_count() -> None:
    sites = list(_sites().values())
    analysis = SimilarSequenceAnalysis(*LAYOUT, max_ddg=1.0)

    assert analysis.run(sites, n_workers=1) == analysis.run(sites, n_workers=2)


@pytest.fixture
def target_gene(tmp_path: Path) -> Path:
    gene = TargetGene(
        id="ENSG00000133703",
        name="KRAS",
        chr="12",
        start=1,
        end=len(GENE_SEQUENCE),
        strand="+",
        sequence=Seq(GENE_SEQUENCE),
        sites=_sites(),
    )
    path = tmp_path / "target.json"
    CreateTargetGeneStep.target_gene_output.write(path, gene)
    return path


def test_step_writes_one_recreatable_fasta_record_per_result(
    target_gene: Path,
    tmp_path: Path,
) -> None:
    step = IdentifyPotentialRepeatedSitesStep()
    output = tmp_path / "potential.fa"

    assert step.run_cli(
        [
            "--target-gene", str(target_gene),
            "--k", "16",
            "--left-wing-length", "3",
            "--gap-length", "10",
            "--right-wing-length", "3",
            "--max-ddg", "1.0",
            "--potential-repeated-sites-output", str(output),
        ]
    ) == 0

    records = list(SeqIO.parse(output, "fasta"))
    sites = _sites()
    assert records
    assert len({record.id for record in records}) == len(records)
    for record in records:
        site_id, mutations = _parse_similar_sequence_id(record.id)
        assert _rebuild_sequence(
            str(sites[site_id].sequence),
            mutations,
        ) == str(record.seq)
        assert record.description == record.id
    # Every site contributes its unmutated sequence, so exact copies count too.
    references = {
        _parse_similar_sequence_id(record.id)[0]
        for record in records
        if _parse_similar_sequence_id(record.id)[1] == ()
    }
    assert references == set(sites)


def test_step_takes_its_units_from_the_target_gene_sites(
    target_gene: Path,
) -> None:
    step = IdentifyPotentialRepeatedSitesStep()
    gene = CreateTargetGeneStep.target_gene_output.file_type.read(target_gene)
    args = SimpleNamespace(
        target_gene=gene,
        n_workers=1,
        max_ddg=1.0,
        ddg_tolerance=0.5,
    )

    assert step.dependencies == ["create-target-gene"]
    assert step.analysis_cls is SimilarSequenceAnalysis
    assert step.analysis_units(args) == gene.sites
