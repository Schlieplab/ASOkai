Target gene to FASTA
====================

.. asokai-step-reference:: target-gene-to-fasta

The FASTA contains one record for the target gene's full 5′ to 3′ sequence.
By default, the input comes from ``create-target-gene``. Select an existing
target-gene JSON file or a named producer run to use a different input. The
FASTA destination is ``targets/target_gene.fa`` beneath ``datadir``. In the
default signature validation mode, a change to the input invalidates the
output's receipt.
