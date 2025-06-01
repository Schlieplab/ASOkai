import RNA
import logging
from typing import Dict, Optional, Tuple

class RNACofold:
    """
    Handles RNA MFE (Minimum Free Energy) and binding energy calculations
    with caching for single sequence MFEs to improve efficiency.
    """
    def __init__(self, temperature: float = 37.0, params_file_path: Optional[str] = None):
        """
        Initializes the RNACofold calculator.

        Args:
            temperature (float): The temperature in Celsius for RNA folding.
            params_file_path (Optional[str]): Path to a ViennaRNA parameter file.
                                         If None, default parameters are used.
        """
        self.md = RNA.md()
        self.md.temperature = temperature
        if params_file_path:
            try:
                RNA.params_load(params_file_path) # This loads params globally for ViennaRNA
                logging.info(f"Loaded ViennaRNA parameters from: {params_file_path}")
            except RuntimeError as e:
                logging.error(f"Failed to load ViennaRNA parameters from {params_file_path}: {e}. Using defaults.")
        
        # Cache for two most recent distinct sequences and their MFEs
        self.cache_slot1: Optional[Tuple[str, float]] = None
        self.cache_slot2: Optional[Tuple[str, float]] = None
        logging.debug(f"RNACofold initialized with temperature {temperature}°C. Caching MFEs for two recent sequences.")

    def get_mfe(self, sequence: str) -> float:
        """
        Calculates or retrieves from cache the MFE of a single RNA sequence.
        Caches MFEs for the two most recently used unique sequences.
        If a sequence matches either slot, its MFE is returned.
        A new MFE calculation replaces slot1, and slot1's old content moves to slot2.

        Args:
            sequence (str): The RNA sequence.

        Returns:
            float: The MFE of the sequence in kcal/mol.
        """
        if not sequence:
            return 0.0
        
        # Check cache slot 1
        if self.cache_slot1 and self.cache_slot1[0] == sequence:
            return self.cache_slot1[1]
        
        # Check cache slot 2
        if self.cache_slot2 and self.cache_slot2[0] == sequence:
            return self.cache_slot2[1]
            
        # If not cached, calculate MFE
        fc = RNA.fold_compound(sequence, self.md)
        (_ss, mfe) = fc.mfe()
        
        # Update cache: new item (sequence, mfe) goes to slot1, old slot1 content moves to slot2.
        self.cache_slot2 = self.cache_slot1 
        self.cache_slot1 = (sequence, mfe)
        
        return mfe

    def calculate_binding_dg(self, seq1: str, seq2: str, constraint: Optional[str] = None) -> float:
        """
        Calculates the binding free energy (dG) between two RNA sequences.
        dG_binding = MFE(seq1&seq2) - (MFE(seq1) + MFE(seq2))

        Args:
            seq1 (str): The first RNA sequence.
            seq2 (str): The second RNA sequence.
            constraint (Optional[str]): An optional structure constraint for the duplex folding.
                                       Example: "((((....))))&((((....))))"

        Returns:
            float: The binding free energy in kcal/mol.
        """
        if not seq1 or not seq2:
            logging.warning("One or both sequences are empty for binding dG calculation. Returning 0.0.")
            return 0.0

        mfe1 = self.get_mfe(seq1)
        mfe2 = self.get_mfe(seq2)
        
        duplex_sequence = f"{seq1}&{seq2}"
        fc_duplex = RNA.fold_compound(duplex_sequence, self.md)
        
        if constraint:
            fc_duplex.hc_add_from_db(constraint)
            
        (_ss_duplex, duplex_mfe) = fc_duplex.mfe()
        
        binding_dg = duplex_mfe - (mfe1 + mfe2)
        return binding_dg

    def calculate_homodimer_binding_dg(self, sequence: str, constraint: Optional[str] = None) -> float:
        """
        Calculates the self-binding (homodimer) free energy of an RNA sequence.

        Args:
            sequence (str): The RNA sequence.
            constraint (Optional[str]): An optional structure constraint for the duplex folding.

        Returns:
            float: The homodimer binding free energy in kcal/mol.
        """
        # For homodimer, the constraint would typically be for seq&seq
        # Example: if sequence is "AAAA", constraint might be "((..))&((..))"
        return self.calculate_binding_dg(sequence, sequence, constraint=constraint) 