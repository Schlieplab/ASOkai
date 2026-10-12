Create target gene
==================

.. asokai-step-reference:: create-target-gene

The step exposes ``target_gene`` as JSON and ``fasta`` as a plain FASTA file.
For ``pre-mrna``, the FASTA contains the full gene sequence as one record. For
``exonic``, it contains one record per distinct exon ID, in genomic order,
with exon ID breaking ties at the same locus.
For ``transcriptomic``, it contains one spliced sequence per transcript, ordered
by transcript ID. The FASTA uses the same destination stem as the JSON file.

All records use the gene, exon, or transcript ID as their FASTA identifier,
followed by the same description format: ``GENE_NAME gene=GENE_ID
locus=CHR:START-END:STRAND``. Coordinates are 1-based and inclusive; a transcript's
locus describes its full genomic span, including introns, while its sequence is
spliced.
