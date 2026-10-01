Build k-mer index
=================

.. asokai-step-reference:: build-kmer-index

Supply a plain or gzip-compressed FASTA file as ``reference``. The step builds
one KFF index using the configured k-mer length and KMC options. Configure
``parameters.genome.assembly_id``, ``parameters.genome.source``, and
``parameters.genome.ensembl_release`` to place the index under its genome
directory. Link the step to a named genome download when the FASTA needs to be
created::

   datadir: /path/to/data
   parameters:
     genome:
       assembly_id: GRCh38
       source: ensembl
       ensembl_release: 114
       species: Homo_sapiens
   runs:
     - step: download-genome
       id: genome
     - step: build-kmer-index
       parameters:
         k: 16
       inputs:
         reference:
           from: run.genome.dna

If the FASTA already exists, select only ``build-kmer-index`` and supply its
``reference`` input with ``{path: /path/to/genome.fa}``.
