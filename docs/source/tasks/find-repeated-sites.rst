Find repeated sites
===================

.. asokai-runnable-reference:: task find-repeated-sites

This task is the public entry in the Analyses catalog. Its
``identify-potential-repeated-sites`` child is an internal step; inspect it with
``asokai describe step identify-potential-repeated-sites``.

This task prepares the data needed to find the genomic sites at which each
target site repeats, for RNase H1 gapmer ASOs. ``create-target-gene`` supplies
the target gene and its FASTA, ``build-bowtie2-index`` indexes that FASTA, and
``identify-potential-repeated-sites`` searches the sequences that each site's own gapmer
still binds.

Aligning those sequences against the index and counting the genomic hits per
target site are not implemented yet, so the task stops after the search and
exposes the index and the potential repeated sites.

The ``gene`` child reads its configuration like any ``create-target-gene`` run.
Supply an existing path or a named run for a child's input to use a different
target.
