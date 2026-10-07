Tree search for target sites
============================

.. asokai-step-reference:: treesearch-target-sites

The step finds candidate repeated sites: variants of a target site that the
site's own gapmer still binds almost as strongly as the site itself. They are
only candidates. A later step aligns them to a reference, and only the
variants found there are repeated sites.

Sites and strands
-----------------

The target sites come from the ``target_gene`` input, which defaults to
``create-target-gene``. The step needs no therapeutic input: a gapmer is the
reverse complement of its target site, so each site is searched against the
reverse complement of that same site.

The wing and gap lengths come from the configured gapmer design under
``parameters.antisense.design``. Positions of the site that pair with the gap
form the core, which is never mutated. Because the gapmer runs antiparallel to
the site, its 5' left wing pairs with the site's 3' end, so the core covers
site positions ``right_wing_length`` through
``right_wing_length + gap_length - 1`` (zero-based). A 2-10-4 design on a
16-nucleotide site therefore has its core at positions 4 to 13.

Search
------

The search visits the flanking positions one at a time, 5' to 3'. At each
position every variant kept so far is extended with each of the four
nucleotides, and each new variant is scored against the unchanged gapmer:

.. math::

   \Delta\Delta G = \Delta G_\text{binding}(\text{variant}) -
   \Delta G_\text{binding}(\text{site})

where ``ΔG_binding = MFE(site&strand) - (MFE(site) + MFE(strand))`` is computed
with :func:`ASOkai.Utils.binding_dg`.

- A variant with ``ΔΔG <= max_ddg`` is reported as a candidate.
- A variant with ``ΔΔG <= max_ddg + ddg_tolerance`` is explored further but
  not reported, because a later substitution can restore binding.
- Every other variant is pruned together with its subtree.

By default the gap's base pairs are enforced while folding, so each variant is
scored in the RNase H1-competent alignment. Set ``unconstrained_duplex`` to
fold the duplex freely instead.

Progress
--------

The step logs the number of target sites and workers before it starts. Each
process then logs how many sites it has searched and its current rate, every
1000 sites by default. A worker counts only its own sites, so the lines from
several workers add up to the total.

Output
------

``candidate_repeated_sites`` is a FASTA file with one record per candidate,
ready to align with ``query-bowtie2``. Each record is named by the site it
came from and the substitutions applied to it, and carries nothing else::

   >site:GRCh38:12:25250719-25250734:-_n0
   ATGACTGAATATAAAC
   >site:GRCh38:12:25250719-25250734:-_n1_m1G
   GTGACTGAATATAAAC
   >site:GRCh38:12:25250719-25250734:-_n2_m1G_m14G
   GTGACTGAATATAGAC

The identifier is the site ID, then ``_n`` and the number of substitutions,
then one ``_m{position}{nucleotide}`` group per substitution with one-based
positions. ``_n2_m1G_m14G`` therefore means two substitutions, ``G`` at
position 1 and ``G`` at position 14. Applying the groups to the site sequence
reproduces the candidate, so the identifier records the whole variant and no
side table is needed. ``parse_candidate_id`` and ``rebuild_sequence`` in
``ASOkai.Analysis._treesearch_target_sites`` read it back.

The record carries no description, so an aligner keeps the identifier intact
as the read name and a later step recovers each alignment's target site from
that name alone. Every search also writes the unmutated site itself as an
``_n0`` record, so exact copies of a site are found too. Within one site the
remaining records are ordered by binding-energy loss. The energies themselves
are not written; :class:`~ASOkai.Analysis.TreesearchTargetSitesAnalysis`
returns them when the search is run directly.

Limitations
-----------

- ViennaRNA's RNA energy parameters are applied to DNA sequences, so the
  energies approximate an RNA-RNA duplex. They model neither the DNA-RNA
  hybrid of the gap nor the modified chemistry of the wings. An RNA G·U wobble
  counts as stabilizing, so some variants receive a negative ``ΔΔG``.
- Wide thresholds produce many candidates. With the default ``max_ddg`` a
  3-10-3 design can yield roughly a thousand candidates per site, and a
  pre-mRNA target gene contributes tens of thousands of sites.
- ViennaRNA holds the interpreter lock while folding, so the analysis opts
  into worker processes. Where those are unavailable it falls back to threads,
  which overlap very little, and the running time then scales with the number
  of target sites.
