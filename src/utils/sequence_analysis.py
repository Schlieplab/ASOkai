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


def longest_at_run(seq: str) -> float:
    """
    Calculate the proportion occupied by the longest contiguous run of A or T nucleotides.

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
    return max_at_run / len(seq)


def longest_t_run(seq: str) -> float:
    """
    Calculate the proportion occupied by the longest contiguous run of T nucleotides.

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
    return max_t_run / len(seq)


def pruned_mutation_search(target_input, max_ddg=5.0, multiplicity_layout=[4,8,4], ddg_tolerance=0.5):
    """
    Generate target site mutations using binding energy (dG_binding) with efficient pruning.
    Mutations are introduced in the flanking regions of the target site.
    Binding energy is calculated between the mutated target site and the original oligo.
    
    Parameters:
    - target_input: Tuple of (target_id, target_sequence)
    - max_ddg: Maximum allowed difference in dG_binding (tau)
    - multiplicity_layout: List defining the layout [left_flank, core, right_flank]
    - ddg_tolerance: Tolerance for pruning mutations based on dG_binding
    
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
        
        # Original Oligo (reverse complement of the original target) - remains constant
        target_obj = Seq(target_site)
        oligo_seq = str(target_obj.reverse_complement())
        
        md = RNA.md()
        md.temperature = 37.0
        
        # --- Calculate Reference Binding Energy (Original Target + Original Oligo) ---
        # MFE of individual strands (original)
        fc_target = RNA.fold_compound(target_site, md)
        (_, target_mfe) = fc_target.mfe()
        
        fc_oligo = RNA.fold_compound(oligo_seq, md)
        (_, oligo_mfe) = fc_oligo.mfe() # This oligo MFE is constant
        
        # MFE of the reference duplex
        reference_duplex = target_site + "&" + oligo_seq
        fc_duplex = RNA.fold_compound(reference_duplex, md)
        (_, duplex_mfe) = fc_duplex.mfe()
        
        # Reference Binding Energy
        reference_binding_dg = duplex_mfe - (target_mfe + oligo_mfe)
        # --- End Reference Binding Energy Calculation ---

        nucleotides = ['A', 'C', 'G', 'T']
        # Mutable positions are in the target_site's flanks
        mutable_positions = list(range(0, core_start)) + list(range(core_end, len(target_site)))
        
        valid_mutations = [] # Stores (mutated_target_site, ddg_binding)
        
        # Bloom filter tracks visited *target_site* mutations
        bloom_capacity = 4**len(mutable_positions) if len(mutable_positions) < 14 else 4**13 # Cap capacity
        bloom = BloomFilter(bloom_capacity, 0.001) 
        bloom.add(target_site)
        
        # Queue stores (current_target_site, depth, mutated_pos_indices, current_target_mfe)
        queue = deque([(target_site, 0, [], target_mfe)]) 
        
        while queue:
            current_target_seq, depth, mutated_pos, current_target_mfe = queue.popleft()
            
            for pos_index in range(len(mutable_positions)):
                pos = mutable_positions[pos_index] # Actual position in the sequence
                
                if pos_index in mutated_pos: # Check if this *index* in mutable_positions was mutated
                    continue
                    
                original_nt = current_target_seq[pos]
                
                for nt in nucleotides:
                    if nt == original_nt:
                        continue
                    
                    # Mutate the target site sequence
                    mutated_target_seq = current_target_seq[:pos] + nt + current_target_seq[pos+1:]
                    
                    if mutated_target_seq in bloom:
                        continue
                    
                    bloom.add(mutated_target_seq)
                    
                    # --- Calculate Mutated Binding Energy (Mutated Target + Original Oligo) ---
                    # MFE of mutated target strand
                    fc_mut_target = RNA.fold_compound(mutated_target_seq, md)
                    (_, mut_target_mfe) = fc_mut_target.mfe()
                    
                    # MFE of the mutated duplex (mutated target & original oligo)
                    mutated_duplex = mutated_target_seq + "&" + oligo_seq
                    fc_mut_duplex = RNA.fold_compound(mutated_duplex, md)
                    (_, mut_duplex_mfe) = fc_mut_duplex.mfe()
                    
                    # Mutated Binding Energy (using constant oligo_mfe)
                    mutated_binding_dg = mut_duplex_mfe - (mut_target_mfe + oligo_mfe)
                    # --- End Mutated Binding Energy Calculation ---

                    # Calculate change in binding energy
                    ddg_binding = mutated_binding_dg - reference_binding_dg
                    
                    if ddg_binding <= max_ddg:
                        # Store the mutated *target* sequence and its ddg_binding
                        valid_mutations.append((mutated_target_seq, ddg_binding)) 
                        
                        if depth < len(mutable_positions) - 1:
                            new_mutated_pos_indices = mutated_pos + [pos_index]
                            queue.append((mutated_target_seq, depth + 1, new_mutated_pos_indices, mut_target_mfe)) 
                    elif ddg_binding <= max_ddg + ddg_tolerance:
                        # Explore further even if slightly above threshold, but don't save
                        if depth < len(mutable_positions) - 1:
                            new_mutated_pos_indices = mutated_pos + [pos_index]
                            queue.append((mutated_target_seq, depth + 1, new_mutated_pos_indices, mut_target_mfe))
        
        # Return reference binding energy and mutations (mutated target sites) with ddg_binding
        return target_id, reference_binding_dg, valid_mutations 
            
    except ValueError as ve:
        logging.error(f"Configuration error for target {target_id}: {ve}")
        return target_id, float('nan'), []
    except Exception as e:
        logging.error(f"Error processing target {target_id}: {e}")
        # Return reference_binding_dg as NaN if calculation failed 
        return target_id, float('nan'), []


def find_potential_secondary_sites(
    target_sites: dict[str, str | TargetSite],
    max_ddg: float = 5.0,
    multiplicity_layout: list = [4, 8, 4],
    ddg_tolerance: float = 0.5,
    num_processes: int = None,
    output_fasta_path: str = None
) -> dict:
    """
    Find potential secondary sites (within max_ddg_binding) for a set of target sites using binding energy.
    
    Parameters:
        target_sites (dict): Dictionary of target sites {id: sequence} or {id: TargetSite}.
        max_ddg (float): Max allowed difference in dG_binding (tau) for pruning.
        multiplicity_layout (list): Layout [left_flank, core, right_flank].
        ddg_tolerance (float): Tolerance for pruning based on dG_binding.
        num_processes (int): Number of processes for parallelization.
        output_fasta_path (str): Path to save mutations in FASTA format.
    
    Returns:
        dict: Dictionary mapping target ID to list of valid mutations (sequence, ddG_binding).
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
        ddg_tolerance=ddg_tolerance
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
        logging.info(f"Calculating pruned mutations (using dG_binding) for {len(processed_dict)} targets using {num_processes} processes")
        
        with mp.Pool(processes=num_processes) as pool:
            # Use imap_unordered for potentially faster consumption of results
            for result in pool.imap_unordered(worker_with_args, processed_dict.items()):
                # Unpack the results: target_id, reference_binding_dg, valid_mutations
                target_id, ref_binding_dg, valid_mutations = result
                
                # Handle potential NaN from worker errors
                if target_id is None or math.isnan(ref_binding_dg):
                     logging.warning(f"Skipping target {target_id or 'Unknown'} due to calculation error.")
                     continue

                results[target_id] = valid_mutations
                target_sites[target_id].dG = ref_binding_dg # Store the reference binding energy in the target site object
                
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