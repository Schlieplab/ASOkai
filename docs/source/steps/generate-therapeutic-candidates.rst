Generate therapeutic candidates
===============================

The step currently supports ASO and gapmer designs. siRNA candidate generation is
not implemented; selecting ``sirna`` fails during parameter validation.

Select the modality with ``parameters.antisense.modality.type`` and place its
mechanism at ``parameters.antisense.modality.mechanism`` and its design settings
under ``parameters.antisense.modality.design``. For example,
the CLI selects a gapmer with ``--param antisense.modality.type=aso`` and
``--param antisense.modality.design.type=gapmer``, followed by its segment
lengths. The gapmer design rules apply to the ASO modality.

.. asokai-step-reference:: generate-therapeutic-candidates
