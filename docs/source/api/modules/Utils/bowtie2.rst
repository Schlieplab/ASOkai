Bowtie 2 utilities
==================

ASOkai wraps the external ``bowtie2``, ``bowtie2-build``, and
``bowtie2-inspect`` executables. Install them through the supplied Conda
environment or provide explicit executable paths. The wrappers run commands
without a shell and raise ``Bowtie2ExecutionError`` on failure.
Their named parameters cover selected Bowtie 2 CLI options; they do not mirror
the full command-line interfaces. Use ``additional_args`` for other options.

``Bowtie2Build`` creates an index from a FASTA file. The output argument is a
basename: Bowtie 2 writes six files with that basename and either ``.bt2`` or
``.bt2l`` suffixes. ``Bowtie2`` accepts that basename to align unpaired or
paired reads to SAM. ``Bowtie2Inspect`` reports reference names or index
metadata.

.. code-block:: python

   from ASOkai.Utils import Bowtie2, Bowtie2Build, Bowtie2Inspect

   Bowtie2Build().run("genome.fa.gz", "indexes/genome", threads=8)
   Bowtie2().run(
       "indexes/genome", "alignments.sam",
       reads="queries.fa", read_format="fasta", threads=8,
       seed_length=16, all_alignments=True,
   )
   names = Bowtie2Inspect().run("indexes/genome", names=True).stdout

Bowtie 2's default seed length targets longer reads. Choose an appropriate
``seed_length`` and scoring policy when searching short oligonucleotides.
The wrappers do not infer a safe sensitivity setting for short queries.
``all_alignments=True`` asks Bowtie 2 to report all alignments it finds; its
heuristic search does not guarantee every possible match. Use an exact sequence
search when a complete count of short repeats is required.

``Bowtie2IndexDirectory`` validates a directory of six index files. Pass its
``index_base(index_directory)`` result to ``Bowtie2.run`` when using an index
directory produced by ASOkai.

The pipeline's ``build-bowtie2-index`` utility step builds this directory from
any plain FASTA. The ``index-target-gene`` task converts a supplied target-gene
JSON file to FASTA and uses that step to build its index.

Bowtie 2 is third-party GPLv3 software. ASOkai invokes its executables
without distributing or linking against them.

.. autoclass:: ASOkai.Utils.Bowtie2
   :members:

.. autoclass:: ASOkai.Utils.Bowtie2Build
   :members:

.. autoclass:: ASOkai.Utils.Bowtie2Inspect
   :members:

.. autoexception:: ASOkai.Utils.Bowtie2ExecutionError
   :members:

.. autoclass:: ASOkai.Utils.ReferenceSequence
   :members:

.. autofunction:: ASOkai.Utils.write_reference_fasta
