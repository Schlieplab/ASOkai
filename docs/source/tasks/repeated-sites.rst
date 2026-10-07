Repeated sites
==============

.. asokai-runnable-reference:: task repeated-sites

This task finds the genomic sites at which each target site repeats, for
RNase H1 gapmer ASOs. It writes the target gene as FASTA and builds a Bowtie 2
index from it. ``treesearch-target-sites`` then searches site variants that
each site's own gapmer still binds. The task aligns those candidates against
the index and counts the genomic hits per target site with
``count-genomic-hits``.

The ``fasta``, ``treesearch``, and ``analysis`` children read the target gene
from ``create-target-gene`` by default. Supply an existing path or a named run
for a child's ``target_gene`` input to use a different target.
