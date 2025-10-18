from typing import Dict, Any, List

from .base import SiteWideAnalysis
from ..targets import Target


class IntrinsicFeaturesAnalysis(SiteWideAnalysis):
    """
    Analyzes intrinsic features for each target site.

    Available features:
        - GC_content: The proportion of Guanine (G) and Cytosine (C) bases (between 0 and 1).
        - AT_content: The proportion of Adenine (A) and Thymine (T) bases (between 0 and 1).
        - T_count: The count of Thymine (T) bases.
        - CpG_count: The total count of CpG dinucleotides (a Cytosine followed by a Guanine).
        - T_content: The proportion of Thymine (T) bases (between 0 and 1).
        - CpG_content: The proportion of CpG dinucleotides (between 0 and 1).
    """

    def __init__(self, target: Target, features: List[str] = None, **kwargs):
        """
        Initializes the IntrinsicFeaturesAnalysis object.
        
        Args:
            target: The target to analyze.
            features: The features to analyze, defaults to all features.
            kwargs: Additional keyword arguments.
        """
        super().__init__(target, **kwargs)
        self.features = features
        if self.features is None:
            self.features = ['GC_content', 'AT_content', 
                             'T_count', 'CpG_count', 
                             'T_content', 'CpG_content']

    def run(self) -> Dict[str, Dict[str, Any]]:
        """
        Calculates intrinsic features for each site in the target.

        Returns:
            A dictionary mapping a feature to a dictionary of site IDs and the
            feature's value for that site.
        """
        results = {feature: {} for feature in self.features}

        for site in self.target.sites:
            sequence = site.sequence
            seq_len = len(sequence) if sequence else 0

            if 'GC_content' in self.features:
                GC_content = sum(map(sequence.count, "GC")) / seq_len if seq_len > 0 else 0
                results['GC_content'][site.id] = GC_content

            if 'AT_content' in self.features:
                AT_content = sum(map(sequence.count, "AT")) / seq_len if seq_len > 0 else 0
                results['AT_content'][site.id] = AT_content

            if 'T_count' in self.features:
                T_count = sequence.count('T')
                results['T_count'][site.id] = T_count
            
            if 'T_content' in self.features:
                T_content = sequence.count('T') / seq_len if seq_len > 0 else 0
                results['T_content'][site.id] = T_content

            if 'CpG_count' in self.features:
                CpG_count = sequence.count('CG')
                results['CpG_count'][site.id] = CpG_count
            
            if 'CpG_content' in self.features:
                CpG_content = sequence.count('CG') / seq_len if seq_len > 0 else 0
                results['CpG_content'][site.id] = CpG_content

        return results
