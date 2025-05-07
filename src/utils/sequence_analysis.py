import logging
import multiprocessing as mp
from functools import partial
import RNA
import os
from Bio.Seq import Seq
from collections import deque
from pybloomfilter import BloomFilter
from src.utils.genome import TargetSite, Site
import math
import time
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


def pruned_mutation_search(target_input, max_ddg=5.0, 
                           multiplicity_layout=[4,8,4], 
                           ddg_tolerance=0.5, 
                           force_core_alignment=True):
    """
    Generate target site mutations using binding energy (dG_binding) with efficient pruning.
    Mutations are introduced in the flanking regions of the target site, one position at a time per depth level.
    Binding energy is calculated between the mutated target site and the original oligo.
    
    Parameters:
    - target_input: Tuple of (target_id, target_sequence)
    - max_ddg: Maximum allowed difference in dG_binding (tau)
    - multiplicity_layout: List defining the layout [left_flank, core, right_flank]
    - ddg_tolerance: Tolerance for pruning mutations based on dG_binding
    - force_core_alignment: If True, use constraints to force core region to form base pairs
    
    Returns:
    - Tuple of (target_id, reference_binding_dg, list of (mutated_target_sequence, ddg_binding) tuples)
    """
    target_id, target_site = target_input
    
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
        
        fc_target = RNA.fold_compound(target_site, md)
        (_, target_mfe) = fc_target.mfe()
        
        fc_oligo = RNA.fold_compound(oligo_seq, md)
        (_, oligo_mfe) = fc_oligo.mfe()
        
        reference_duplex = target_site + "&" + oligo_seq
        fc_duplex = RNA.fold_compound(reference_duplex, md)
        if force_core_alignment and constraint_string:
            fc_duplex.hc_add_from_db(constraint_string)
        (_, duplex_mfe) = fc_duplex.mfe()
        reference_binding_dg = duplex_mfe - (target_mfe + oligo_mfe)

        nucleotides = ['A', 'C', 'G', 'T']
        mutable_positions = list(range(0, core_start)) + list(range(core_end, len(target_site)))
        
        valid_mutations_set = set()  # Use a set to store unique (sequence, ddg) tuples

        # Queue for BFS at current depth
        current_level_queue = deque([(target_site, target_mfe)])

        # Process each depth (each mutable position)
        for depth_idx in range(len(mutable_positions)):
            if not current_level_queue:  # No sequences to process at this depth
                break

            pos_to_mutate = mutable_positions[depth_idx]
            next_level_queue = deque()
            # Track unique sequences for next level to avoid duplicates
            next_level_unique_sequences = set()

            # Process all sequences at current depth
            while current_level_queue:
                current_seq, current_mfe = current_level_queue.popleft()
                
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
                            next_level_queue.append((mutated_target_seq, mut_target_mfe))
                            next_level_unique_sequences.add(mutated_target_seq)
                    
                    # If within tolerance, explore but don't add to valid mutations
                    elif ddg_binding <= max_ddg + ddg_tolerance:
                        if mutated_target_seq not in next_level_unique_sequences:
                            next_level_queue.append((mutated_target_seq, mut_target_mfe))
                            next_level_unique_sequences.add(mutated_target_seq)
            
            # Update queue for next depth level
            current_level_queue = next_level_queue
        
        # Convert set of valid mutations to list
        valid_mutations = list(valid_mutations_set)
        
        return target_id, reference_binding_dg, valid_mutations
            
    except ValueError as ve:
        logging.error(f"Configuration error for target {target_id}: {ve}")
        return target_id, float('nan'), []
    except Exception as e:
        logging.error(f"Error processing target {target_id}: {e}")
        return target_id, float('nan'), []

@timed
def find_potential_secondary_sites(
    target_sites: dict[str, str | TargetSite],
    max_ddg: float = 5.0,
    multiplicity_layout: list = [4, 8, 4],
    ddg_tolerance: float = 0.5,
    num_processes: int = None,
    output_fasta_path: str = None,
    force_core_alignment: bool = True
) -> dict:
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
    
    processed_dict = {}
    for target_id, target in target_sites.items():
        if isinstance(target, str):
            processed_dict[target_id] = target
        else:
            processed_dict[target_id] = target.sequence
    
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

    results = {}
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
                # Unpack the results: target_id, reference_binding_dg, valid_mutations
                target_id, ref_binding_dg, valid_mutations = result
                
                processed_count += 1
                if processed_count % 100 == 0:
                    progress.update(100)
                
                # Handle potential NaN from worker errors
                if target_id is None or math.isnan(ref_binding_dg):
                    logging.warning(f"Skipping target {target_id or 'Unknown'} due to calculation error.")
                    continue

                results[target_id] = valid_mutations
                target_sites[target_id].dG = ref_binding_dg
                
                if output_fasta_path:
                    with open(output_fasta_path, 'a') as f:
                        target_seq = processed_dict[target_id]
                        
                        # Write original target sequence with its reference binding energy
                        # The energy still refers to the binding with the original oligo
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