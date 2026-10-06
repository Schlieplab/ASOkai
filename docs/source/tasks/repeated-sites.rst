Repeated sites
==============

.. asokai-runnable-reference:: task repeated-sites

This task finds the genomic sites at which each target site repeats. It writes
the target gene as FASTA, builds a Bowtie 2 index from it, runs a tree search
over the target sites to produce queries, aligns the queries against the index,
and counts the genomic hits per target site with ``count-genomic-hits``.

The ``fasta``, ``treesearch``, and ``analysis`` children read the target gene
from ``create-target-gene`` by default. Supply an existing path or a named run
for each child's ``target_gene`` input to use a different target.
