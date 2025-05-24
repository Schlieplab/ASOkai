import logging
import multiprocessing as mp
from functools import partial
import RNA
import os
from Bio.Seq import Seq
from collections import deque
from scipy import constants
from genome_utils import TargetSite
import math
import numpy as np
import sympy as sp
from typing import Dict, List, Tuple, Optional, Union, Set, Any, Callable
from src.utils.time_utils import ProgressTracker, timed


def longest_at_run(seq: str) -> float:
    """
    Calculate the longest contiguous run of A or T nucleotides.

    Parameters:
        seq (str): The nucleotide sequence.

    Returns:
        float: The length of the longest A/T run divided by the total length of the sequence.
    """
    seq = seq.upper()
    if not seq:
        return 0.0
    max_at_run = 0
    current_at_run = 0
    for nucleotide in seq:
        if nucleotide in 'AT':
            current_at_run += 1
            max_at_run = max(max_at_run, current_at_run)
        else:
            current_at_run = 0
    return max_at_run


def longest_t_run(seq: str) -> float:
    """
    Calculate the longest contiguous run of T nucleotides.

    Parameters:
        seq (str): The nucleotide sequence.

    Returns:
        float: The length of the longest T run divided by the total length of the sequence.
    """
    seq = seq.upper()
    if not seq:
        return 0.0
    max_t_run = 0
    current_t_run = 0
    for nucleotide in seq:
        if nucleotide == 'T':
            current_t_run += 1
            max_t_run = max(max_t_run, current_t_run)
        else:
            current_t_run = 0
    return max_t_run


def calculate_homodimer_binding_energy(seq: str) -> float:
    """
    Calculate the self-binding energy of a nucleotide sequence.

    Parameters:
        seq (str): The nucleotide sequence.

    Returns:
        float: The self-binding energy in kcal/mol.
    """
    if not seq:
        return 0.0
    md = RNA.md()
    md.temperature = 37.0
    
    fc = RNA.fold_compound(seq, md)
    (_, mfe) = fc.mfe()
        
    # MFE of the reference duplex
    duplex = seq + "&" + seq
    fc_duplex = RNA.fold_compound(duplex, md)
    
    (ss, duplex_mfe) = fc_duplex.mfe()

    # Reference Binding Energy
    binding_dg = duplex_mfe - (mfe + mfe)
    
    return binding_dg


def pruned_mutation_search(
    target_input: Tuple[str, Tuple[str, float]], 
    max_ddg: float = 5.0, 
    multiplicity_layout: List[int] = [4,8,4], 
    ddg_tolerance: float = 0.5, 
    force_core_alignment: bool = True
) -> Tuple[str, List[Tuple[str, float]]]:
    """
    Generate target site mutations using binding energy (dG_binding) with efficient pruning.
    Mutations are introduced in the flanking regions of the target site, one position at a time per depth level.
    Binding energy is calculated between the mutated target site and the original oligo.
    
    Parameters:
        target_input: Tuple of (target_id, (target_sequence, reference_binding_dg))
        max_ddg: Maximum allowed difference in dG_binding (tau)
        multiplicity_layout: List defining the layout [left_flank, core, right_flank]
        ddg_tolerance: Tolerance for pruning mutations based on dG_binding
        force_core_alignment: If True, use constraints to force core region to form base pairs
    
    Returns:
        Tuple of (target_id, list of (mutated_target_sequence, ddg_binding) tuples)
    """
    target_id, target_site_and_reference_binding_dg = target_input
    target_site, reference_binding_dg = target_site_and_reference_binding_dg
    
    try:
        expected_length = sum(multiplicity_layout)
        if len(target_site) != expected_length:
            raise ValueError(f"Sequence length ({len(target_site)}) does not match layout sum ({expected_length})")
        
        core_start = multiplicity_layout[0]
        core_end = core_start + multiplicity_layout[1]
        
        target_obj = Seq(target_site)
        oligo_seq = str(target_obj.reverse_complement())
        
        md = RNA.md()
        md.temperature = 37.0
        
        constraint_string = None
        if force_core_alignment:
            target_constraint = '.' * multiplicity_layout[0] + '|' * multiplicity_layout[1] + '.' * multiplicity_layout[2]
            oligo_constraint = '.' * multiplicity_layout[2] + '|' * multiplicity_layout[1] + '.' * multiplicity_layout[0]
            constraint_string = target_constraint + '&' + oligo_constraint
        
        fc_oligo = RNA.fold_compound(oligo_seq, md)
        (_, oligo_mfe) = fc_oligo.mfe()
        
        nucleotides = ['A', 'C', 'G', 'T']
        mutable_positions = list(range(0, core_start)) + list(range(core_end, len(target_site)))
        
        valid_mutations_set: Set[Tuple[str, float]] = set()  # Use a set to store unique (sequence, ddg) tuples

        # Queue for BFS at current depth
        current_level_queue = deque([target_site])

        # Process each depth (each mutable position)
        for depth_idx in range(len(mutable_positions)):
            if not current_level_queue:  # No sequences to process at this depth
                break

            pos_to_mutate = mutable_positions[depth_idx]
            next_level_queue = deque()
            # Track unique sequences for next level to avoid duplicates
            next_level_unique_sequences: Set[str] = set()

            # Process all sequences at current depth
            while current_level_queue:
                current_seq = current_level_queue.popleft()
                
                # Try all possible nucleotides at current position
                for nt in nucleotides:
                    # Create mutated sequence
                    mutated_seq_list = list(current_seq)
                    mutated_seq_list[pos_to_mutate] = nt
                    mutated_target_seq = "".join(mutated_seq_list)
                    
                    # Calculate binding energy for mutated sequence
                    fc_mut_target = RNA.fold_compound(mutated_target_seq, md)
                    (_, mut_target_mfe) = fc_mut_target.mfe()
                    
                    mutated_duplex = mutated_target_seq + "&" + oligo_seq
                    fc_mut_duplex = RNA.fold_compound(mutated_duplex, md)
                    if force_core_alignment and constraint_string:
                        fc_mut_duplex.hc_add_from_db(constraint_string)
                    (_, mut_duplex_mfe) = fc_mut_duplex.mfe()
                    
                    mutated_binding_dg = mut_duplex_mfe - (mut_target_mfe + oligo_mfe)
                    ddg_binding = mutated_binding_dg - reference_binding_dg
                    
                    # Check if this mutation is valid and should be explored further
                    if ddg_binding <= max_ddg:
                        # Add to valid mutations if it's not the original sequence
                        if mutated_target_seq != target_site:
                            valid_mutations_set.add((mutated_target_seq, ddg_binding))
                        
                        # Add to next level queue if not already there
                        if mutated_target_seq not in next_level_unique_sequences:
                            next_level_queue.append(mutated_target_seq)
                            next_level_unique_sequences.add(mutated_target_seq)
                    
                    # If within tolerance, explore but don't add to valid mutations
                    elif ddg_binding <= max_ddg + ddg_tolerance:
                        if mutated_target_seq not in next_level_unique_sequences:
                            next_level_queue.append(mutated_target_seq)
                            next_level_unique_sequences.add(mutated_target_seq)
            
            # Update queue for next depth level
            current_level_queue = next_level_queue
        
        # Convert set of valid mutations to list
        valid_mutations = list(valid_mutations_set)
        
        return target_id, valid_mutations
            
    except ValueError as ve:
        logging.error(f"Configuration error for target {target_id}: {ve}")
        return target_id, []
    except Exception as e:
        logging.error(f"Error processing target {target_id}: {e}")
        return target_id, []

@timed
def find_potential_secondary_sites(
    target_sites: Dict[str, Union[str, TargetSite]],
    max_ddg: float = 5.0,
    multiplicity_layout: List[int] = [4, 8, 4],
    ddg_tolerance: float = 0.5,
    num_processes: Optional[int] = None,
    output_fasta_path: Optional[str] = None,
    force_core_alignment: bool = True
) -> Dict[str, List[Tuple[str, float]]]:
    """
    Find potential secondary binding sites for each target site.
    
    Args:
        target_sites (dict): Dictionary of target sites
        max_ddg (float): Maximum ddG threshold
        multiplicity_layout (list): Layout for multiplicity calculation
        ddg_tolerance (float): Tolerance for ddG calculations
        num_processes (int): Number of processes to use
        output_fasta_path (str): Path to output FASTA file
        force_core_alignment (bool): Whether to force core alignment
        
    Returns:
        dict: Dictionary of valid mutations for each target
    """
    if num_processes is None:
        num_processes = mp.cpu_count()
    
    processed_dict: Dict[str, Tuple[str, float]] = {}
    for target_id, target in target_sites.items():
        processed_dict[target_id] = (target.sequence, target.dG)
    
    worker_with_args = partial(
        pruned_mutation_search, 
        max_ddg=max_ddg,
        multiplicity_layout=multiplicity_layout,
        ddg_tolerance=ddg_tolerance,
        force_core_alignment=force_core_alignment
    )
    
    if output_fasta_path:
        # Ensure directory exists, handle potential path issues
        output_dir = os.path.dirname(os.path.abspath(output_fasta_path))
        if output_dir: # Check if dirname returned a non-empty string
             os.makedirs(output_dir, exist_ok=True)
        # Clear the file if it exists
        with open(output_fasta_path, 'w') as f:
            pass # Just opening in 'w' mode clears the file

    results: Dict[str, List[Tuple[str, float]]] = {}
    try:
        logging.info(
            f"Calculating pruned mutations (using dG_binding) for {len(processed_dict)} "
            f"targets using {num_processes} processes. Max ddG threshold: {max_ddg:.2f} "
            f"kcal/mol, tolerance: {ddg_tolerance:.2f} kcal/mol"
        )
        
        with mp.Pool(processes=num_processes) as pool:
            # Use imap_unordered for potentially faster consumption of results
            processed_count = 0
            progress = ProgressTracker(len(processed_dict), "Finding secondary sites")
            
            for result in pool.imap_unordered(worker_with_args, processed_dict.items()):
                # Unpack the results: target_id, valid_mutations
                target_id, valid_mutations = result
                
                processed_count += 1
                if processed_count % 100 == 0:
                    progress.update(100)
                
                # Handle potential NaN from worker errors
                if target_id is None:
                    logging.warning(f"Skipping target {target_id or 'Unknown'} due to calculation error.")
                    continue

                results[target_id] = valid_mutations
                
                if output_fasta_path:
                    with open(output_fasta_path, 'a') as f:
                        target_seq, ref_binding_dg = processed_dict[target_id]
                        
                        # Write original target sequence with its reference binding energy
                        f.write(f">{target_id}_0 dG_binding={ref_binding_dg:.2f} (reference)\n{target_seq}\n")
                        
                        # Write mutated oligo sequences with their absolute and relative binding energies
                        for idx, (seq, ddg_binding) in enumerate(valid_mutations):
                            mutation_id = f"{target_id}_{idx+1}"
                            # Calculate absolute binding dG for the mutation
                            mutation_binding_dg = ref_binding_dg + ddg_binding
                            # Write the mutated oligo sequence (seq)
                            f.write(f">{mutation_id} dG_binding={mutation_binding_dg:.2f} ddG_binding={ddg_binding:.2f}\n{seq}\n")
                
        logging.info(f"Completed pruned mutation calculations for {len(results)} targets")
        total_mutations = sum(len(muts) for muts in results.values() if muts is not None) # Handle potential None lists
        logging.info(f"Found a total of {total_mutations} valid mutations based on dG_binding")
        
        if output_fasta_path:
            logging.info(f"Mutations written to {output_fasta_path}")
            
        return results
    
    except Exception as e:
        logging.error(f"Error in parallel processing: {e}")
        # Consider more specific error handling or logging
        raise # Re-raise the exception after logging
 
 
 
# Pedersen Model Below

def get_target_k_diss(k_diss: float, ddG: float, temp: float = 37.0) -> float:
    """
    Calculate the dissociation constant for ASO:Target complex based on ddG from average dG.
    
    Args:
        k_diss: Dissociation constant for ASO:Target complex
        ddG: Free energy difference in kJ/mol from the average dG
        temp: Temperature in Celsius (default: 37.0)
        
    Returns:
        Dissociation constant for ASO:Target complex with specified ddG between average ASO dG and Target dG
    """
    temp_k = constants.convert_temperature(temp, 'C', 'K')
    return k_diss * math.exp((ddG * 1000) / (constants.R * temp_k))

def quartic_coeffs(vprod: float, k_degrad: float, k_OpT: float, k_OT: float, k_OC: float,
                   k_OTpE: float, k_OTE: float, k_OCE: float, k_cleav: float,
                   E_ini: float, O_ini: float) -> List[float]:
    """
    Calculate coefficients for the quartic equation in the steady state analysis using symbolic computation.
    
    Args:
        vprod: Production rate of target (T → ∅)
        k_degrad: Degradation rate of target (T → ∅)
        k_OpT: Association rate of the OT complex (O + T → OT)
        k_OT: Dissociation rate of the OT complex (OT → O + T)
        k_OC: Association rate of the OC complex (O + C → OC)
        k_OTpE: Association rate of the OTE complex (OT + E → OTE)
        k_OTE: Dissociation rate of the OTE complex (OTE → OT + E)
        k_OCE: Dissociation rate of the OCE complex (OCE → OC + E)
        k_cleav: Cleavage rate of target by RNase H (OTE → OCE)
        E_ini: Initial enzyme concentration
        O_ini: Initial oligo concentration
        
    Returns:
        List of quartic coefficients [alpha4, alpha3, alpha2, alpha1, alpha0]
    """
    OTE = sp.symbols('OTE')  # the single remaining unknown

    # Step 1: express all variables in terms of OTE
    OCE = (k_cleav / k_OCE) * OTE
    OC = (k_cleav / k_OC) * OTE
    E = E_ini - (1 + k_cleav / k_OCE) * OTE
    OT = (vprod - (k_degrad + k_cleav) * OTE - k_degrad * (k_degrad + k_OTE + k_cleav) * OTE / (k_OTpE * (E_ini - (1 + k_cleav / k_OCE) * OTE))) / k_degrad
    T = (vprod - (k_degrad + k_cleav) * OTE - k_degrad * OT) / k_degrad
    O = ((k_OT + k_degrad) * OT + (k_degrad + k_cleav) * OTE) / (k_OpT * T)

    # Step 2: impose the final balance O + OT + OTE + OCE + OC = O_ini
    balance = sp.simplify(O + OT + OTE + OCE + OC - O_ini)

    # Step 3: clear denominators → polynomial numerator
    numer = sp.together(balance).as_numer_denom()[0]
    poly = sp.Poly(sp.expand(numer), OTE)

    # The quartic may have degree < 4 for special parameter choices,
    # so left-pad with zeros if needed
    coeffs = poly.all_coeffs()
    coeffs = [sp.Integer(0)] * (5 - len(coeffs)) + coeffs  # alpha4 … alpha0

    # Convert to ordinary (numeric) floats so we can feed them to numpy
    return [float(sp.N(coeff)) for coeff in coeffs]

def admissible_E_roots(vprod: float, k_degrad: float, k_OpT: float, k_OT: float, k_OC: float,
                      k_OTpE: float, k_OTE: float, k_OCE: float, k_cleav: float,
                      E_ini: float, O_ini: float, atol: float = 1e-12, rtol: float = 1e-9,
                      verbose: bool = False) -> List[float]:
    """
    Find admissible real, non-negative quartic roots that keep denominators non-zero.
    
    Args:
        vprod: Production rate of target (T → ∅)
        k_degrad: Degradation rate of target (T → ∅)
        k_OpT: Association rate of the OT complex (O + T → OT)
        k_OT: Dissociation rate of the OT complex (OT → O + T)
        k_OC: Association rate of the OC complex (O + C → OC)
        k_OTpE: Association rate of the OTE complex (OT + E → OTE)
        k_OTE: Dissociation rate of the OTE complex (OTE → OT + E)
        k_OCE: Dissociation rate of the OCE complex (OCE → OC + E)
        k_cleav: Cleavage rate of target by RNase H (OTE → OCE)
        E_ini: Initial enzyme concentration
        O_ini: Initial oligo concentration
        atol: Absolute tolerance for numerical comparisons
        rtol: Relative tolerance for numerical comparisons
        verbose: Whether to print debug information
        
    Returns:
        List of admissible real, non-negative roots
    """
    try:
        alpha4, alpha3, alpha2, alpha1, alpha0 = quartic_coeffs(
            vprod, k_degrad, k_OpT, k_OT, k_OC, k_OTpE, k_OTE, k_OCE, k_cleav, E_ini, O_ini
        )
        roots = np.roots([alpha4, alpha3, alpha2, alpha1, alpha0])
        
        if verbose:
            logging.info(f"All quartic roots: {roots}")

        good = []
        for r in roots:
            # Check if root is real and non-negative
            if abs(r.imag) < atol and r.real >= -rtol:
                OTE = r.real

                # Check all denominators in the derived formulas
                denom_h = abs(k_OCE) > atol
                denom_e = abs(k_OC) > atol
                denom_f = abs(k_OTpE * (E_ini - (1 + k_cleav / k_OCE) * OTE)) > atol
                denom_b = abs(k_degrad) > atol
                denom_c = abs(k_OpT) > atol

                if all([denom_h, denom_e, denom_f, denom_b, denom_c]):
                    if (OTE > 0) and (OTE <= E_ini) and (OTE <= O_ini):
                        good.append(OTE)

        if verbose:
            logging.info(f"Admissible quartic roots: {good}")
        return good
        
    except Exception as e:
        logging.error(f"Error in admissible_E_roots: {str(e)}")
        return []

def get_steady_state_solution_Pedersen(par: Dict[str, float], verbose: bool = False) -> Optional[Dict[str, float]]:
    """
    Calculate steady state solution using Pedersen's method.
    
    Args:
        par: Dictionary of parameters containing:
            - vprod: Production rate of target (T → ∅)
            - k_degrad: Degradation rate of target (T → ∅)
            - k_OpT: Association rate of the OT complex (O + T → OT)
            - k_OT: Dissociation rate of the OT complex (OT → O + T)
            - k_C: Association rate of the OC complex (O + C → OC)
            - alpha: Ratio between dissociation rates (α)
            - k_OTpE: Association rate of the OTE complex (OT + E → OTE)
            - k_OTE: Dissociation rate of the OTE complex (OTE → OT + E)
            - k_cleav: Cleavage rate of target by RNase H (OTE → OCE)
            - E_ini: Initial enzyme concentration
            - O_ini: Initial oligo concentration
        verbose: Whether to print debug information
        
    Returns:
        Dictionary containing steady state concentrations or None if no valid solution found
    """
    try:
        vprod = par['vprod']
        k_degrad = par['k_degrad']
        k_OpT = par['k_OpT']
        k_OT = par['k_OT']
        k_OC = par['k_OT'] * par['alpha'] if 'alpha' in par else par['k_C']
        k_OTpE = par['k_OTpE']
        k_OTE = par['k_OTE']
        k_OCE = par['k_OTE']
        k_cleav = par['k_cleav']
        E_ini = par['E_ini']
        O_ini = par['O_ini']

        roots = admissible_E_roots(
            vprod, k_degrad, k_OpT, k_OT, k_OC, k_OTpE, k_OTE, k_OCE, k_cleav, E_ini, O_ini
        )

        sol = None
        if not roots:
            if verbose:
                logging.info("No admissible (non-negative) root found.")
        else:
            for i, E_star in enumerate(roots):
                if verbose:
                    logging.info(f"\nSolution {i+1}:")
                    logging.info(f"  OTE = {E_star:.10g}")

                # Calculate steady state concentrations
                OCE = (k_cleav / k_OCE) * E_star
                OC = (k_cleav / k_OC) * E_star
                E = E_ini - (1 + k_cleav / k_OCE) * E_star
                OT = (vprod - (k_degrad + k_cleav) * E_star - k_degrad * (k_degrad + k_OTE + k_cleav) * E_star / (k_OTpE * (E_ini - (1 + k_cleav / k_OCE) * E_star))) / k_degrad
                T = (vprod - (k_degrad + k_cleav) * E_star - k_degrad * OT) / k_degrad
                O = ((k_OT + k_degrad) * OT + (k_degrad + k_cleav) * E_star) / (k_OpT * T)

                if verbose:
                    logging.info(f"  O   = {O:.10g}")
                    logging.info(f"  T   = {T:.10g}")
                    logging.info(f"  E   = {E:.10g}")
                    logging.info(f"  OT  = {OT:.10g}")
                    logging.info(f"  OTE = {E_star:.10g}")
                    logging.info(f"  OCE = {OCE:.10g}")
                    logging.info(f"  OC  = {OC:.10g}")

                # Check physical validity of solution
                if all(x >= 0 for x in [O, T, E, OT, E_star, OCE, OC]):
                    if verbose:
                        logging.info("  --> Physically possible solution")
                    if sol is not None:
                        logging.warning("Multiple physically possible solutions found, only the last one will be returned.")
                    sol = {
                        'O': O, 'T': T, 'E': E, 'OT': OT, 'OTE': E_star,
                        'OCE': OCE, 'OC': OC
                    }
                elif verbose:
                    logging.info("  --> Not all variables are non-negative (non-physical)")

        return sol
        
    except Exception as e:
        logging.error(f"Error in get_steady_state_solution_Pedersen: {str(e)}")
        return None

def convert_tsl_list(tsl_str: str) -> Tuple[bool, Optional[List[Optional[int]]]]:
    """
    Convert a string of transcript support levels into a list of integers or None values.
    
    Args:
        tsl_str (str): Comma-separated string of transcript support levels (e.g., "tsl1,tsl2,tslNA")
        
    Returns:
        Tuple[bool, Optional[List[Optional[int]]]]: A tuple containing:
            - bool: True if specific TSLs were provided, False if all TSLs are included
            - Optional[List[Optional[int]]]: List of TSL values (1-5 or None for NA)
    """
    tsl_tokens = [token.strip() for token in tsl_str.split(',') if token.strip()]
    converted_tsls = []

    for token in tsl_tokens:
        if token.lower().startswith("tsl"):
            value_part = token[3:]
            if value_part.lower() == "na":
                converted_tsls.append(None)
            else:
                try:
                    converted_tsls.append(int(value_part))
                except ValueError:
                    logging.warning("Invalid transcript support level '%s'; using None.", token)
                    converted_tsls.append(None)
        else:
            try:
                converted_tsls.append(int(token))
            except ValueError:
                logging.warning("Invalid transcript support level '%s'; using None.", token)
                converted_tsls.append(None)

    all_tsls = [1, 2, 3, 4, 5, None]
    if converted_tsls == all_tsls:
        return False, None
    return True, converted_tsls