Create target gene
==================

.. asokai-step-reference:: create-target-gene

The step exposes ``target_gene`` as JSON and ``fasta`` as a plain FASTA file.
For ``pre-mrna``, the FASTA contains the full gene sequence as one record. For
``exonic``, it contains one record per distinct exon locus, in genomic order.
For ``transcriptomic``, it contains one spliced sequence per transcript, ordered
by transcript ID. The FASTA uses the same destination stem as the JSON file.
