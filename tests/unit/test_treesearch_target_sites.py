#!/usr/bin/env python
"""
Filename: tests/unit/test_treesearch_target_sites.py
Author: Kian Jalilian
Copyright: 2026, Alexander Schliep
Description: Tests for the candidate repeated-site search and its pipeline step.
License: LGPL-3.0-or-later
"""

import logging
from pathlib import Path
from types import SimpleNamespace

from Bio import SeqIO
from Bio.Seq import Seq
import pytest

from ASOkai.Analysis import TreesearchTargetSitesAnalysis
from ASOkai.Analysis._treesearch_target_sites import (
    candidate_id,
    gapmer_core_positions,
    parse_candidate_id,
    rebuild_sequence,
)
from ASOkai.Sites import GenomicSite
from ASOkai.Targets import TargetGene
from ASOkai.Utils import binding_dg
from ASOkai._pipeline.steps.analysis.treesearch_target_sites import (
    TreesearchTargetSitesStep,
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


def test_binding_dg_is_negative_for_a_perfect_duplex() -> None:
    site = GENE_SEQUENCE[:16]

    assert binding_dg(site, str(Seq(site).reverse_complement())) < 0


def test_binding_dg_accepts_extra_viennarna_model_arguments() -> None:
    site = GENE_SEQUENCE[:16]
    strand = str(Seq(site).reverse_complement())

    cold = binding_dg(site, strand, model_settings={"temperature": 10.0})
    warm = binding_dg(site, strand, model_settings={"temperature": 60.0})

    # Duplexes are less stable when warmer, so the energy rises.
    assert cold < warm


def test_binding_dg_rejects_an_unknown_model_argument() -> None:
    with pytest.raises(ValueError, match="Unknown ViennaRNA model setting"):
        binding_dg("ACGTACGT", "ACGTACGT", model_settings={"nonsense": 1})


def test_step_parses_model_settings_as_name_value_pairs() -> None:
    parse = TreesearchTargetSitesStep()._model_settings

    assert parse("temperature=37.0,noGU=1") == {
        "temperature": 37.0,
        "noGU": 1,
    }
    assert parse("") == {}
    with pytest.raises(ValueError, match="name=value"):
        parse("temperature")
    with pytest.raises(ValueError, match="repeats"):
        parse("noGU=1,noGU=0")


def test_core_positions_follow_the_gapmer_gap() -> None:
    # The gapmer is antiparallel, so its 5' left wing covers the site's 3' end.
    assert gapmer_core_positions(16, 2, 10, 4) == range(4, 14)
    assert gapmer_core_positions(16, 3, 10, 3) == range(3, 13)


def test_core_positions_reject_a_layout_of_another_length() -> None:
    with pytest.raises(ValueError, match="must equal the site length"):
        gapmer_core_positions(16, 3, 10, 4)


def test_candidate_identifiers_round_trip() -> None:
    site = GENE_SEQUENCE[:16]
    mutations = ((0, "G"), (13, "T"))

    identifier = candidate_id("site:12:1-16,+", mutations)

    assert identifier == "site:12:1-16,+_n2_m1G_m14T"
    assert parse_candidate_id(identifier) == ("site:12:1-16,+", mutations)
    assert rebuild_sequence(site, mutations) == "GTGACTGAATATATAC"


def test_candidate_identifier_accepts_a_full_genomic_site_id() -> None:
    # Real site IDs carry the assembly, locus, and strand, so they contain
    # the colons and hyphens the identifier suffix must survive.
    site_id = "site:GRCh38:12:25250719-25250734:-"
    mutations = ((0, "G"), (13, "G"))

    identifier = candidate_id(site_id, mutations)

    assert identifier == f"{site_id}_n2_m1G_m14G"
    assert parse_candidate_id(identifier) == (site_id, mutations)


def test_candidate_identifier_of_the_unmutated_site_has_no_groups() -> None:
    identifier = candidate_id("site:12:1-16,+", ())

    assert identifier == "site:12:1-16,+_n0"
    assert parse_candidate_id(identifier) == ("site:12:1-16,+", ())


def test_candidate_identifier_rejects_a_wrong_substitution_count() -> None:
    with pytest.raises(ValueError, match="declares 3 substitution"):
        parse_candidate_id("site:1_n3_m1G")

    with pytest.raises(ValueError, match="Malformed"):
        parse_candidate_id("site:1_m1G")


def test_search_mutates_only_positions_outside_the_core() -> None:
    sites = list(_sites().values())
    analysis = TreesearchTargetSitesAnalysis(*LAYOUT, max_ddg=1.0)

    results = analysis.run(sites, n_workers=1)

    assert {candidate.site_id for candidate in results} == {
        site.id for site in sites
    }
    by_site = {site.id: str(site.sequence) for site in sites}
    references = [candidate for candidate in results if candidate.is_reference]
    assert len(references) == len(sites)
    for candidate in results:
        site_sequence = by_site[candidate.site_id]
        assert rebuild_sequence(site_sequence, candidate.mutations) == (
            candidate.sequence
        )
        assert candidate.sequence[3:13] == site_sequence[3:13]
        assert candidate.ddg_binding <= 1.0
    for reference in references:
        assert reference.ddg_binding == 0.0
        assert reference.sequence == by_site[reference.site_id]


def test_search_logs_progress_at_its_interval(caplog) -> None:
    sites = list(_sites().values())

    class Noisy(TreesearchTargetSitesAnalysis):
        progress_interval = 1

    with caplog.at_level(
        logging.INFO,
        logger="ASOkai.Analysis._treesearch_target_sites",
    ):
        Noisy(*LAYOUT, max_ddg=0.5).run(sites, n_workers=1)

    progress = [r for r in caplog.records if "Searched" in r.message]
    assert len(progress) == len(sites)


def test_search_can_report_no_progress(caplog) -> None:
    class Quiet(TreesearchTargetSitesAnalysis):
        progress_interval = 0

    with caplog.at_level(
        logging.INFO,
        logger="ASOkai.Analysis._treesearch_target_sites",
    ):
        Quiet(*LAYOUT, max_ddg=0.5).run(list(_sites().values()), n_workers=1)

    assert not [r for r in caplog.records if "Searched" in r.message]


def test_search_rejects_negative_thresholds() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        TreesearchTargetSitesAnalysis(*LAYOUT, max_ddg=-1.0)


def test_search_result_does_not_depend_on_the_thread_count() -> None:
    sites = list(_sites().values())
    analysis = TreesearchTargetSitesAnalysis(*LAYOUT, max_ddg=1.0)

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


def test_step_writes_one_recreatable_fasta_record_per_candidate(
    target_gene: Path,
    tmp_path: Path,
) -> None:
    step = TreesearchTargetSitesStep()
    output = tmp_path / "candidates.fa"

    assert step.run_cli(
        [
            "--target-gene", str(target_gene),
            "--k", "16",
            "--left-wing-length", "3",
            "--gap-length", "10",
            "--right-wing-length", "3",
            "--max-ddg", "1.0",
            "--candidate-repeated-sites-output", str(output),
        ]
    ) == 0

    records = list(SeqIO.parse(output, "fasta"))
    sites = _sites()
    assert records
    assert len({record.id for record in records}) == len(records)
    for record in records:
        site_id, mutations = parse_candidate_id(record.id)
        assert rebuild_sequence(
            str(sites[site_id].sequence),
            mutations,
        ) == str(record.seq)
        assert record.description == record.id
    # Every site contributes its unmutated sequence, so exact copies count too.
    references = {
        parse_candidate_id(record.id)[0]
        for record in records
        if parse_candidate_id(record.id)[1] == ()
    }
    assert references == set(sites)


def test_step_takes_its_units_from_the_target_gene_sites(
    target_gene: Path,
) -> None:
    step = TreesearchTargetSitesStep()
    gene = CreateTargetGeneStep.target_gene_output.file_type.read(target_gene)
    args = SimpleNamespace(
        target_gene=gene,
        n_workers=1,
        max_ddg=1.0,
        ddg_tolerance=0.5,
    )

    assert step.dependencies == ["create-target-gene"]
    assert step.analysis_cls is TreesearchTargetSitesAnalysis
    assert step.analysis_units(args) == gene.sites
