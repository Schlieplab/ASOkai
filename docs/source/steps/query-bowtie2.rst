Query Bowtie 2
==============

.. asokai-step-reference:: query-bowtie2

The step aligns plain FASTA queries against a Bowtie 2 index directory and
writes SAM alignments. Tasks connect both inputs to their producers; the
``repeated-sites`` task uses ``build-bowtie2-index`` and
``treesearch-target-sites``.
