import logging
import multiprocessing as mp
from functools import partial
import os
from Bio.Seq import Seq
from collections import deque
from scipy import constants
import math
import numpy as np
import sympy as sp
from typing import Dict, List, Tuple, Optional, Union, Set, Any, Callable
from .utils import ProgressTracker, timed, RNACofold, GenomeUtils
import json

# Default Pedersen parameters if no file is provided
DEFAULT_PEDERSEN_PARAMS = {
    "vprod": 34.0,
    "k_degrad": 0.034,
    "k_OpT": 3.32e-5,
    "k_OT": 0.06,
    "k_OTpE": 0.00277,
    "k_OTE": 350.0,
    "k_cleav": 83.8,
    "O_ini": 1000.0,
    "E_ini": 1800.0,
    "alpha": 1.2,
    "k_C": None # Will be calculated
} 
if DEFAULT_PEDERSEN_PARAMS['alpha'] != 0:
    DEFAULT_PEDERSEN_PARAMS['k_C'] = DEFAULT_PEDERSEN_PARAMS['k_OT'] / DEFAULT_PEDERSEN_PARAMS['alpha']

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




class SecondarySiteFinder:
    """
    Finds potential secondary binding sites for a given set of target sequences.
    """
    def __init__(self,
                 max_ddg: float = 5.0,
                 multiplicity_layout: List[int] = [4, 8, 4],
                 ddg_tolerance: float = 0.5,
                 num_processes: Optional[int] = None,
                 force_core_alignment: bool = True,
                 verbose: bool = False):
        """
        Initialize the SecondarySiteFinder.

        Args:
            max_ddg (float): Maximum allowed difference in dG_binding (tau).
            multiplicity_layout (list): Layout defining [left_flank, core, right_flank].
            ddg_tolerance (float): Tolerance for pruning mutations based on dG_binding.
            num_processes (int): Number of processes to use for parallel computation.
            force_core_alignment (bool): If True, use constraints to force core region to form base pairs.
        """
        self.max_ddg = max_ddg
        self.multiplicity_layout = multiplicity_layout
        self.ddg_tolerance = ddg_tolerance
        self.num_processes = num_processes if num_processes is not None else mp.cpu_count()
        self.force_core_alignment = force_core_alignment
        self.verbose = verbose
        
    @staticmethod
    def _pruned_mutation_search(
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
            
            rna_cofold = RNACofold()
            
            constraint_string = None
            if force_core_alignment:
                target_constraint = '.' * multiplicity_layout[0] + '|' * multiplicity_layout[1] + '.' * multiplicity_layout[2]
                oligo_constraint = '.' * multiplicity_layout[2] + '|' * multiplicity_layout[1] + '.' * multiplicity_layout[0]
                constraint_string = target_constraint + '&' + oligo_constraint
            
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
                        
                        mutated_binding_dg = rna_cofold.calculate_binding_dg(mutated_target_seq, 
                                                                             oligo_seq, 
                                                                             constraint_string)
                        
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
    def find_sites(
        self,
        target_sites: Dict[str, GenomeUtils.CandidateTarget],
        output_fasta_path: Optional[str] = None
    ) -> Dict[str, List[Tuple[str, float]]]:
        """
        Find potential secondary binding sites for each target site.
        
        Args:
            target_sites (Dict[str, CandidateTarget]): Dictionary mapping target site identifiers to CandidateTarget objects.
            output_fasta_path (str, optional): Path to output FASTA file for mutations. Defaults to None.
            
        Returns:
            Dict[str, List[Tuple[str, float]]]: Dictionary mapping target_id to a list of (mutation_sequence, ddG_binding) tuples.
        """
        processed_dict: Dict[str, Tuple[str, float]] = {}

        for target_id, candidate in target_sites.items():
            if not (hasattr(candidate, 'sequence') and hasattr(candidate, 'dG_binding')):
                logging.warning(f"Item with id '{target_id}' does not appear to be a valid CandidateTarget object. Skipping.")
                continue

            sequence = candidate.sequence
            binding_energy = candidate.dG_binding
            
            if not sequence:
                logging.warning(f"CandidateTarget '{target_id}' has an empty or None sequence. Skipping.")
                continue

            if binding_energy is None:
                logging.warning(f"CandidateTarget '{target_id}' is missing the 'dG_binding' value. Skipping.")
                continue
            
            processed_dict[target_id] = (sequence, binding_energy)
        
        worker_with_args = partial(
            SecondarySiteFinder._pruned_mutation_search,
            max_ddg=self.max_ddg,
            multiplicity_layout=self.multiplicity_layout,
            ddg_tolerance=self.ddg_tolerance,
            force_core_alignment=self.force_core_alignment
        )
        
        if output_fasta_path:
            output_dir = os.path.dirname(os.path.abspath(output_fasta_path))
            if output_dir:
                 os.makedirs(output_dir, exist_ok=True)
            with open(output_fasta_path, 'w') as f:
                pass

        results: Dict[str, List[Tuple[str, float]]] = {}
        try:
            if self.verbose:
                logging.info(
                    f"Calculating pruned mutations (using dG_binding) for {len(processed_dict)} "
                    f"targets using {self.num_processes} processes. Max ddG threshold: {self.max_ddg:.2f} "
                    f"kcal/mol, tolerance: {self.ddg_tolerance:.2f} kcal/mol"
                )
            
            with mp.Pool(processes=self.num_processes) as pool:
                processed_count = 0
                progress = ProgressTracker(len(processed_dict), "Finding secondary sites")
                
                for result in pool.imap_unordered(worker_with_args, processed_dict.items()):
                    target_id, valid_mutations = result
                    processed_count += 1
                    progress.update(1)
                    
                    if target_id is None:
                        logging.warning(f"Skipping target {target_id or 'Unknown'} due to calculation error.")
                        continue

                    results[target_id] = valid_mutations
                    
                    if output_fasta_path and target_id in processed_dict:
                        with open(output_fasta_path, 'a') as f:
                            target_seq, ref_binding_dg = processed_dict[target_id]
                            f.write(f">{target_id}_0 dG_binding={ref_binding_dg:.2f} (reference)\n{target_seq}\n")
                            for idx, (seq, ddg_binding) in enumerate(valid_mutations):
                                mutation_id = f"{target_id}_{idx+1}"
                                mutation_binding_dg = ref_binding_dg + ddg_binding
                                f.write(f">{mutation_id} dG_binding={mutation_binding_dg:.2f} ddG_binding={ddg_binding:.2f}\n{seq}\n")
                    elif output_fasta_path and target_id not in processed_dict:
                        logging.warning(f"Could not write FASTA for {target_id} as it's not in processed_dict.")

            total_mutations = sum(len(muts) for muts in results.values() if muts is not None)
            if self.verbose:
                logging.info(f"Found a total of {total_mutations} valid mutations based on dG_binding")

            if output_fasta_path and self.verbose:
                logging.info(f"Mutations written to {output_fasta_path}")
                
            return results
        
        except Exception as e:
            logging.error(f"Error in parallel processing: {e}")
            raise


class PedersenAnalysis:
    """
    Performs Pedersen model-based kinetic analysis for ASO-target interactions.

    This class encapsulates the logic for:
    - Loading Pedersen model parameters from a JSON file or using defaults.
    - Calculating average dG for candidate targets.
    - Running the Pedersen steady-state calculations in parallel for multiple targets.
    - Updating target site objects with their normalized steady-state concentrations.

    The main public methods are `__init__` for setup and `run_analysis` to execute the calculations.
    Internal calculations include solving quartic equations derived from the kinetic model.
    """
    def __init__(self, 
                 candidate_targets: Dict[str, GenomeUtils.CandidateTarget],
                 num_processes: Optional[int] = None,
                 params_file_path: Optional[str] = None,
                 verbose: bool = False):
        self.candidate_targets = candidate_targets
        self.num_processes = num_processes if num_processes is not None else mp.cpu_count()
        self.verbose = verbose        
        if params_file_path:
            logging.info(f"Loading Pedersen parameters from specified file: {params_file_path}")
            try:
                self.params = PedersenAnalysis._get_params_from_file(params_file_path)
            except Exception as e:
                logging.error(f"Failed to load Pedersen parameters from {params_file_path}: {e}")
                raise ValueError(f"Could not initialize PedersenAnalysis: {e}")
        else:
            if self.verbose:
                logging.info("No Pedersen parameters file provided. Using default parameters.")
            self.params = DEFAULT_PEDERSEN_PARAMS.copy()

        if self.candidate_targets:
            dG_values = [c.dG_binding for c in self.candidate_targets.values() if c.dG_binding is not None]
            if dG_values:
                self.average_dG = sum(dG_values) / len(dG_values)
                if self.average_dG == 0.0 and any(dG != 0.0 for dG in dG_values):
                     logging.warning("Calculated average_dG is 0.0, but some targets have non-zero dG_binding values. Check data.")
            else:
                self.average_dG = 0.0
                logging.warning("No candidate targets with dG_binding values provided; average_dG set to 0.")
        else:
            self.average_dG = 0.0
            logging.warning("No candidate targets provided; average_dG set to 0.")

    @staticmethod
    def _get_params_from_file(params_file_path: str) -> Dict[str, float]:
        if not os.path.exists(params_file_path):
            raise FileNotFoundError(f"Pedersen parameters file not found: {params_file_path}")
        with open(params_file_path, 'r') as f:
            params = json.load(f)
        params = {k: float(v) for k, v in params.items()}
        if 'k_C' not in params and 'k_OT' in params and 'alpha' in params and params.get('alpha') != 0:
            params['k_C'] = params['k_OT'] / params['alpha']
        elif 'k_C' not in params:
            params['k_C'] = None
        return params

    @staticmethod
    def _get_target_k_diss(k_diss_initial: float, ddG: float, temp: float = 37.0) -> float:
        temp_k = constants.convert_temperature(temp, 'C', 'K')
        return k_diss_initial * math.exp((ddG * 1000) / (constants.R * temp_k))

    @staticmethod
    def _quartic_coeffs(vprod: float, k_degrad: float, k_OpT: float, k_OT: float, k_OC: float,
                       k_OTpE: float, k_OTE: float, k_OCE: float, k_cleav: float,
                       E_ini: float, O_ini: float) -> List[float]:
        OTE = sp.symbols('OTE')
        OCE = (k_cleav / k_OCE) * OTE
        OC = (k_cleav / k_OC) * OTE
        E = E_ini - (1 + k_cleav / k_OCE) * OTE
        
        denom_f_expr = (k_OTpE * (E_ini - (1 + k_cleav / k_OCE) * OTE))
        # Potential for division by zero if denom_f_expr is symbolically zero with specific params.
        # sympy handles symbolic division; numerical issues would arise at evaluation if not careful.
        OT = (k_degrad + k_OTE + k_cleav) * OTE / denom_f_expr 
        T = (vprod - (k_degrad + k_cleav) * OTE - k_degrad * OT) / k_degrad
        O = ((k_OT + k_degrad) * OT + (k_degrad + k_cleav) * OTE) / (k_OpT * T)
        
        balance = sp.simplify(O + OT + OTE + OCE + OC - O_ini)
        numer = sp.together(balance).as_numer_denom()[0]
        poly = sp.Poly(sp.expand(numer), OTE)
        coeffs = poly.all_coeffs()
        coeffs = [sp.Integer(0)] * (5 - len(coeffs)) + coeffs
        return [float(sp.N(coeff)) for coeff in coeffs]

    @staticmethod
    def _admissible_E_roots(params: Dict[str, float], verbose: bool = False, atol: float = 1e-12, rtol: float = 1e-9) -> List[float]:
        vprod = params['vprod']; k_degrad = params['k_degrad']; k_OpT = params['k_OpT']
        k_OT = params['k_OT']; k_OC = params['k_C']; k_OTpE = params['k_OTpE']
        k_OTE = params['k_OTE']; k_OCE = params['k_OTE'] # k_OCE = k_OTE in this model
        k_cleav = params['k_cleav']; E_ini = params['E_ini']; O_ini = params['O_ini']
        
        try:
            alpha_coeffs = PedersenAnalysis._quartic_coeffs(
                vprod, k_degrad, k_OpT, k_OT, k_OC, k_OTpE, k_OTE, k_OCE, k_cleav, E_ini, O_ini
            )
            roots = np.roots(alpha_coeffs)
            if verbose: logging.info(f"All quartic roots: {roots}")
            good_roots = []
            for r_val in roots:
                if abs(r_val.imag) < atol and r_val.real >= -rtol:
                    OTE_root = r_val.real
                    # Denominator checks (simplified, direct check from expressions)
                    denom_h_ok = abs(k_OCE) > atol
                    denom_e_ok = abs(k_OC) > atol if k_OC is not None else True # k_OC can be None
                    denom_f_val_at_root = k_OTpE * (E_ini - (1 + k_cleav / k_OCE) * OTE_root) if denom_h_ok else 0
                    denom_f_ok = abs(denom_f_val_at_root) > atol
                    denom_b_ok = abs(k_degrad) > atol

                    if all([denom_h_ok, denom_e_ok, denom_f_ok, denom_b_ok]):
                        if (OTE_root >= 0) and (OTE_root <= E_ini) and (OTE_root <= O_ini):
                            good_roots.append(OTE_root)
            if verbose: logging.info(f"Admissible quartic roots: {good_roots}")
            return good_roots
        except Exception as e:
            logging.error(f"Error in _admissible_E_roots: {str(e)}")
            return []

    @staticmethod
    def _get_steady_state_solution(par: Dict[str, float], verbose: bool = False) -> Optional[Dict[str, float]]:
        try:
            vprod = par['vprod']; k_degrad = par['k_degrad']; k_OpT = par['k_OpT']
            k_OT = par['k_OT']; k_C = par['k_C'] 
            k_OTpE = par['k_OTpE']; k_OTE = par['k_OTE']; k_OCE = par['k_OTE'] 
            k_cleav = par['k_cleav']; E_ini = par['E_ini']; O_ini = par['O_ini']

            roots = PedersenAnalysis._admissible_E_roots(par, verbose)
            sol = None
            if not roots:
                if verbose: logging.info("No admissible (non-negative) root found for OTE.")
            else:
                for i, E_star in enumerate(roots):
                    if verbose: logging.info(f"\nSolution {i+1}: OTE = {E_star:.10g}")
                    OCE_val = (k_cleav / k_OCE) * E_star if k_OCE != 0 else float('inf')
                    OC_val = (k_cleav / k_C) * E_star if k_C is not None and k_C != 0 else float('inf')
                    E_val = E_ini - (1 + k_cleav / k_OCE) * E_star if k_OCE !=0 else E_ini - E_star 
                    
                    denom_f_val = k_OTpE * (E_ini - (1 + k_cleav / k_OCE) * E_star) if k_OCE !=0 else 0
                    OT_val = (k_degrad + k_OTE + k_cleav) * E_star / denom_f_val if denom_f_val != 0 else float('inf')
                    T_val = (vprod - (k_degrad + k_cleav) * E_star - k_degrad * OT_val) / k_degrad if k_degrad != 0 else float('inf')
                    O_val = ((k_OT + k_degrad) * OT_val + (k_degrad + k_cleav) * E_star) / (k_OpT * T_val) if (k_OpT * T_val) != 0 else float('inf')

                    if verbose:
                        logging.info(f"  O={O_val:.10g}, T={T_val:.10g}, E={E_val:.10g}, OT={OT_val:.10g}, OTE={E_star:.10g}, OCE={OCE_val:.10g}, OC={OC_val:.10g}")
                    
                    # Check for physical validity (non-negative and finite concentrations)
                    if all(x_val >= 0 and not math.isinf(x_val) for x_val in [O_val, T_val, E_val, OT_val, E_star, OCE_val, OC_val]):
                        if verbose: logging.info("  --> Physically possible solution found")
                        if sol is not None: logging.warning("Multiple physically possible solutions found; last one is used.")
                        sol = {'O': O_val, 'T': T_val, 'E': E_val, 'OT': OT_val, 'OTE': E_star, 'OCE': OCE_val, 'OC': OC_val}
                    elif verbose: logging.info("  --> Non-physical solution (negative or infinite concentration detected)")
            return sol
        except KeyError as ke:
            logging.error(f"Missing parameter for steady state solution: {ke}")
            return None
        except Exception as e:
            logging.error(f"Error in _get_steady_state_solution: {str(e)}")
            return None

    @staticmethod
    def _process_pedersen_target(target_data_tuple: Tuple[str, GenomeUtils.CandidateTarget, Dict[str, float], float]) -> Tuple[str, float]:
        target_id, candidate, params, average_dG = target_data_tuple
        try:
            target_dG = candidate.dG_binding
            if target_dG is None:
                logging.error(f"CandidateTarget '{target_id}' is missing the 'dG_binding' value. Skipping Pedersen calculation for this target.")
                return target_id, 0.0
            
            ddG_from_avg = target_dG - average_dG
            k_OT_initial = params.get('k_OT')
            if k_OT_initial is None: 
                logging.error(f"Missing 'k_OT' in params for target {target_id}"); return target_id, 0.0
            
            k_diss = PedersenAnalysis._get_target_k_diss(k_OT_initial, ddG_from_avg, 37.0)
            
            par_target = params.copy()
            par_target['k_OT'] = k_diss
            if 'alpha' in par_target and par_target['alpha'] != 0:
                 par_target['k_C'] = k_diss / par_target['alpha'] 

            steady_state = PedersenAnalysis._get_steady_state_solution(par_target)
            if steady_state is None: 
                logging.warning(f"No steady state solution found for target {target_id}"); return target_id, 0.0
            
            steady_state_concentration = steady_state['T'] + steady_state['OT'] + steady_state['OTE']
            logging.debug(f"Target {target_id}: ddG={ddG_from_avg:.2f}, k_diss={k_diss:.2e}, T_steady_state={steady_state_concentration:.2e}")
            return target_id, steady_state_concentration
        except KeyError as ke: logging.error(f"Missing key in params for target {target_id}: {str(ke)}"); return target_id, 0.0
        except Exception as e: logging.error(f"Error processing target {target_id}: {str(e)}"); return target_id, 0.0

    def run_analysis(self) -> Dict[str, float]:
        logging.info(f"Performing Pedersen analysis")
        if not self.candidate_targets: 
            logging.warning("No candidate targets for Pedersen analysis")
            return {}
        
        if self.average_dG == 0.0:
            has_nonzero_dG = any(c.dG_binding != 0.0 for c in self.candidate_targets.values() if c.dG_binding is not None)
            if has_nonzero_dG:
                logging.error("average_dG is zero, but some targets have non-zero dG_binding values. Pedersen analysis might be unreliable.")
            else:
                logging.warning("All target dG_binding values are zero or no targets. average_dG = 0. Pedersen results might be trivial.")

        par_no_oligo = self.params.copy()
        par_no_oligo['O_ini'] = 1e-10
        
        steady_state_no_oligo_calc = PedersenAnalysis._get_steady_state_solution(par_no_oligo, self.verbose)
        if steady_state_no_oligo_calc is None or steady_state_no_oligo_calc.get('T', 0.0) == 0.0:
            logging.error("Could not calculate valid baseline steady state target concentration (T). Aborting Pedersen analysis.")
            return {tid: 0.0 for tid in self.candidate_targets.keys()}
        steady_state_no_oligo_T = steady_state_no_oligo_calc['T']

        logging.info(f"Average dG: {self.average_dG:.2f}. Baseline steady state T (no oligo): {steady_state_no_oligo_T:.2e}")
        
        tasks = [(tid, candidate, self.params, self.average_dG) for tid, candidate in self.candidate_targets.items()]
        logging.info(f"Starting Pedersen analysis for {len(tasks)} targets using {self.num_processes} processes.")
        
        pedersen_results: Dict[str, float] = {}
        with mp.Pool(processes=self.num_processes) as pool:
            results = pool.imap_unordered(PedersenAnalysis._process_pedersen_target, tasks)
            for target_id, steady_state_value in results:
                if target_id in self.candidate_targets:
                    if steady_state_no_oligo_T != 0:
                        pedersen_results[target_id] = steady_state_value / steady_state_no_oligo_T
                    else:
                        pedersen_results[target_id] = 0.0
                        logging.warning(f"Baseline T concentration is zero for target {target_id}, cannot normalize. Setting pedersen_steady_state to 0.0.") 
                else:
                    logging.warning(f"Received result for unknown target_id: {target_id}")
        logging.info("Completed Pedersen analysis")
        return pedersen_results