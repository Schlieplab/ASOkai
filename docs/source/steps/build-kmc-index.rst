Build KMC index
===============

.. asokai-step-reference:: build-kmc-index

.. note::

   This step invokes the third-party ``kmc`` and ``kmc_tools`` executables.
   KMC is GPLv3-only software; ASOkai does not distribute or link against it.
   Install the executables through the supplied Conda environment.

Supply a plain or gzip-compressed FASTA file as ``reference``. The step builds
one KFF index using the configured k-mer length and KMC options. Set
``resources.build-kmc-index.memory_mb`` to control KMC's memory limit.
Configure ``parameters.genome.assembly``, ``parameters.genome.source``, and
``parameters.genome.release`` to place the index under its genome
directory. Link the step to a named genome download when the FASTA needs to be
created::

   datadir: /path/to/data
   parameters:
     genome:
       assembly: GRCh38
       source: ensembl
       release: 114
       species: Homo_sapiens
   runs:
     - step: download-genome
       id: genome
     - step: build-kmc-index
       parameters:
         k: 16
       inputs:
         reference:
           from: run.genome.dna

If the FASTA already exists, select only ``build-kmc-index`` and supply its
``reference`` input with ``{path: /path/to/genome.fa}``.
