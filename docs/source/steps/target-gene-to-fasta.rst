Target gene to FASTA
====================

.. asokai-step-reference:: target-gene-to-fasta

The FASTA contains one record for the supplied target gene's full 5′ to 3′
sequence. Supply a typed target-gene JSON file. Its destination is
``targets/target_gene.fa`` beneath ``datadir``. In the default signature
validation mode, a change to the input invalidates the output's receipt.
