# -*- coding: utf-8 -*-
import argparse
import sys
from src.utils.file_operations import (
    build_genomic_bowtie_index,
    build_transcriptomic_bowtie_index, 
    build_RNAcofold_in, 
    run_bowtie,
    run_RNAcofold,
    download_genome,
    )
import logging
from src.oligo_extractor import OligoExtractor
import configparser
import os
import multiprocessing as mp


def setup_logging():
    logging.basicConfig(
    force=True,
    level=logging.INFO,
    stream=sys.stdout,
    format='### %(levelname)s - %(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def read_config(args_set: str):

    config_parser = configparser.ConfigParser()
    files_read = config_parser.read('config.ini')
    if not files_read:
        logging.error("Configuration file 'config.ini' not found or could not be read.")
        logging.info("Exiting.")
        sys.exit(1)
    
    if args_set not in config_parser:
        logging.error("Configuration section '%s' not found in 'config.ini'.", args_set)
        logging.info("Exiting.")
        sys.exit(1)
    
    config = config_parser[args_set]

    return config
    
def convert_tsl_list(tsl_str):
    # Retrieve and process transcript support levels
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
        return False, None   # No custom filter is needed
    return True, converted_tsls

def setup_environment(config):
    
    if config["Species"] == "mus_musculus":
        bowtie_index_name = f'GRCm{int(config["GenomeAssembly"])}_{int(config["EnsembleRelease"])}'
    elif config["Species"] == "homo_sapiens":
        bowtie_index_name = f'GRCh{int(config["GenomeAssembly"])}_{int(config["EnsembleRelease"])}'
    else:
        logging.error("Only mus_musculus and homo_sapiens species implemented. Please set appropriate species in config.ini.")
        logging.info("Exiting.")
        sys.exit(1)

    try:
        bowtie_index_dir = os.path.join(config['Bowtie2Dir'], "bowtie2Home", bowtie_index_name)
        os.makedirs(bowtie_index_dir, exist_ok=True)

        genome_data_dir = os.path.join(config['GenomeDir'], 'genome', bowtie_index_name)
        os.makedirs(genome_data_dir, exist_ok=True)
        
        os.makedirs(os.path.join(config['DataDir'], 'oligos'), exist_ok=True)
        os.makedirs(os.path.join(config['DataDir'], 'RNACofold'), exist_ok=True)
        os.makedirs(os.path.join(config['DataDir'], 'results'), exist_ok=True)
    except Exception as e:
        logging.error(f"Error creating directories: {e}")
        logging.info("Exiting.")
        sys.exit(1)

    try:
        os.environ['BOWTIE2_INDEXES'] = bowtie_index_dir
    except KeyError as e:
        logging.error(f"Error setting Environment Variables: {e}")
        logging.info("Exiting.")
        sys.exit(1)
    
    return bowtie_index_name, bowtie_index_dir, genome_data_dir


from Bio.Seq import Seq
from collections import deque
from bloom_filter import BloomFilter
from functools import partial

import RNA


def worker_function(initial_mutation, target_site, max_ddg, multiplicity_layout, ddg_tolerance):
    """Worker function that processes a single initial mutation path"""
    mfe_calculation_time = 0
    
    # Calculate core start and end positions
    core_start = multiplicity_layout[0]
    core_end = core_start + multiplicity_layout[1]
    
    # Generate target sequence as reverse complement
    target_obj = Seq(target_site)
    oligo_seq = str(target_obj.reverse_complement())
    
    # Set up RNA parameters
    md = RNA.md()
    md.temperature = 37.0
    
    # Calculate reference MFE
    reference_duplex = target_site + "&" + oligo_seq
    fc = RNA.fold_compound(reference_duplex, md)
    (_, reference_mfe) = fc.mfe()
    
    # Define nucleotides and mutable positions
    nucleotides = ['A', 'C', 'G', 'T']
    mutable_positions = list(range(0, core_start)) + list(range(core_end, len(target_site)))
    
    # Create local Bloom filter for this worker
    bloom = BloomFilter(max_elements=4**mutable_positions, error_rate=0.01)
    
    valid_mutations = []
    pos, nt = initial_mutation
    
    # Start with the first mutation specified for this worker
    original_nt = oligo_seq[pos]
    if nt != original_nt:
        mutated_seq = oligo_seq[:pos] + nt + oligo_seq[pos+1:]
        bloom.add(mutated_seq)
        
        mutated_duplex = target_site + "&" + mutated_seq
        fc_mut = RNA.fold_compound(mutated_duplex, md)
        (_, mutated_mfe) = fc_mut.mfe()
        
        ddg = mutated_mfe - reference_mfe
        
        # Initialize the BFS queue with this mutation if it meets criteria
        queue = deque([])
        if ddg <= max_ddg:
            valid_mutations.append((mutated_seq, ddg))
            queue.append((mutated_seq, 1, [pos]))
        elif ddg <= max_ddg + ddg_tolerance:
            queue.append((mutated_seq, 1, [pos]))
    
        # Continue with BFS from this starting point
        while queue:
            current_seq, depth, mutated_pos = queue.popleft()
            
            for next_pos in mutable_positions:
                if next_pos in mutated_pos:
                    continue
                    
                original_nt = current_seq[next_pos]
                
                for next_nt in nucleotides:
                    if next_nt == original_nt:
                        continue
                    
                    mutated_seq = current_seq[:next_pos] + next_nt + current_seq[next_pos+1:]
                    
                    if mutated_seq in bloom:
                        continue
                    
                    bloom.add(mutated_seq)
                    
                    mutated_duplex = target_site + "&" + mutated_seq
                    fc_mut = RNA.fold_compound(mutated_duplex, md)
                    (_, mutated_mfe) = fc_mut.mfe()
                    
                    ddg = mutated_mfe - reference_mfe
                    
                    if ddg <= max_ddg:
                        valid_mutations.append((mutated_seq, ddg))
                        
                        if depth < len(mutable_positions) - 1:
                            new_mutated_pos = mutated_pos + [next_pos]
                            queue.append((mutated_seq, depth + 1, new_mutated_pos))
                    elif ddg <= max_ddg + ddg_tolerance:
                        if depth < len(mutable_positions) - 1:
                            new_mutated_pos = mutated_pos + [next_pos]
                            queue.append((mutated_seq, depth + 1, new_mutated_pos))

    return valid_mutations

def pruned_mutation_search(target_site, max_ddg, multiplicity_layout=[4,8,4], ddg_tolerance=0.5, n_processes=None):
    """
    Parallel version of pruned_mutation_search using multiprocessing
    
    Parameters:
    - target_site: Original ASO sequence
    - max_ddg: Maximum allowed difference in dG (tau)
    - multiplicity_layout: List defining the layout [left_flank, core, right_flank]
    - ddg_tolerance: Tolerance for pruning
    - n_processes: Number of processes to use (defaults to CPU count)
    
    Returns:
    - List of (mutated_sequence, ddg) tuples that meet the criteria
    """
    
    # Validate sequence length
    expected_length = sum(multiplicity_layout)
    if len(target_site) != expected_length:
        raise ValueError(f"Sequence length ({len(target_site)}) does not match layout sum ({expected_length})")
    
    # Calculate core start and end positions
    core_start = multiplicity_layout[0]
    core_end = core_start + multiplicity_layout[1]
    
    # Generate target sequence as reverse complement
    target_obj = Seq(target_site)
    oligo_seq = str(target_obj.reverse_complement())
    
    # Define nucleotides and mutable positions
    nucleotides = ['A', 'C', 'G', 'T']
    mutable_positions = list(range(0, core_start)) + list(range(core_end, len(target_site)))
    
    # Create initial mutations to distribute across workers
    initial_mutations = []
    for pos in mutable_positions:
        original_nt = oligo_seq[pos]
        for nt in nucleotides:
            if nt != original_nt:
                initial_mutations.append((pos, nt))
    
    logging.info(f"Starting parallel search with {len(initial_mutations)} initial mutations")
    
    # Set up multiprocessing
    if n_processes is None:
        n_processes = mp.cpu_count()
    
    logging.info(f"Using {n_processes} processes")
    
    # Create a partial function with fixed parameters
    worker_partial = partial(
        worker_function,
        target_site=target_site,
        max_ddg=max_ddg,
        multiplicity_layout=multiplicity_layout,
        ddg_tolerance=ddg_tolerance
    )

    
    with mp.Pool(processes=n_processes) as pool:
        results = pool.map(worker_partial, initial_mutations)
    
    # Combine results from all workers
    all_mutations = set()
    for result in results:
        all_mutations.update(result)
    
    return list(all_mutations)


def pruned_mutation_search(target_site, max_ddg, multiplicity_layout=[4,8,4], ddg_tolerance=0.5):
    """
    Generate mutations with efficient pruning to search the sequence space
    
    Parameters:
    - target_sequence: Original ASO sequence (16-mer)
    - max_ddg: Maximum allowed difference in dG (tau)
    - multiplicity_layout: List defining the layout [left_flank, core, right_flank]
    
    Returns:
    - List of (mutated_sequence, ddg) tuples that meet the criteria
    """
    # Validate sequence length matches the layout
    expected_length = sum(multiplicity_layout)
    if len(target_site) != expected_length:
        raise ValueError(f"Sequence length ({len(target_site)}) does not match layout sum ({expected_length})")
    
    # Calculate core start and end positions
    core_start = multiplicity_layout[0]
    core_end = core_start + multiplicity_layout[1]
    
    # Generate target sequence as reverse complement of original sequence
    target_obj = Seq(target_site)
    oligo_seq = str(target_obj.reverse_complement())
    
    # Calculate reference dG using RNAcofold with mfe
    md = RNA.md()
    md.temperature = 37.0  # Standard temperature
    
    # Create fold compound for the duplex
    reference_duplex = target_site + "&" + oligo_seq
    fc = RNA.fold_compound(reference_duplex, md)
    (_, reference_mfe) = fc.mfe()
    print('Reference MFE:', reference_mfe, flush=True)
    print('ddg_tolerance:', ddg_tolerance, flush=True)
    # Define nucleotides for mutation
    nucleotides = ['A', 'C', 'G', 'T']  # Use 'U' instead of 'T' if working with RNA
    
    # Define mutable positions (flanking regions)
    mutable_positions = list(range(0, core_start)) + list(range(core_end, len(target_site)))
    
    valid_mutations = []
    
    # Create Bloom filter to track processed sequences
    # For a layout [2,12,2], we expect 3^4 = 81 possible mutations
    # Set capacity higher to account for sequences we'll check but reject
    bloom = BloomFilter(max_elements=4**len(mutable_positions), error_rate=0.001)
    
    # Add original sequence to Bloom filter
    bloom.add(oligo_seq)
    
    # Use breadth-first search for more systematic exploration
    queue = deque([(oligo_seq, 0, [])])  # (current_sequence, current_depth, mutated_positions)
    
    while queue:
        current_seq, depth, mutated_pos = queue.popleft()
        
        for pos in mutable_positions:
            if pos in mutated_pos:
                continue
                
            original_nt = current_seq[pos]
            
            for nt in nucleotides:
                if nt == original_nt:
                    continue
                
                mutated_seq = current_seq[:pos] + nt + current_seq[pos+1:]
                
                if mutated_seq in bloom:
                    continue
                
                bloom.add(mutated_seq)
                
                mutated_duplex = target_site + "&" + mutated_seq
                fc_mut = RNA.fold_compound(mutated_duplex, md)
                (_, mutated_mfe) = fc_mut.mfe()
                ddg = mutated_mfe - reference_mfe
                
                if ddg <= max_ddg:
                    valid_mutations.append((mutated_seq, ddg))
                    
                    if depth < len(mutable_positions) - 1:
                        new_mutated_pos = mutated_pos + [pos]
                        queue.append((mutated_seq, depth + 1, new_mutated_pos))
                elif ddg <= max_ddg + ddg_tolerance:
                    # If ddG is within tolerance, add to queue but don't add to valid mutations
                    if depth < len(mutable_positions) - 1:
                        new_mutated_pos = mutated_pos + [pos]
                        queue.append((mutated_seq, depth + 1, new_mutated_pos))
                # If outside tolerance, prune this branch (don't add to queue)
    
    return valid_mutations


# Example usage
def maintest():
    import time
    import numpy as np
    original_sequence = "CACGTCCACTGCTATCCGGC"  # Your 16-mer ASO
    max_ddg = 5.0 
    
    
    RNA.params_load("/home/ayat/Repositories/ASODesignPipeline/vienna_rna_rna_params.par")

    start = time.time()
    mutations = pruned_mutation_search(
        original_sequence,  
        max_ddg,
        [6,8,6],
        ddg_tolerance=1.0
    )
    end = time.time()
    print(f"Time taken: {end - start:.2f} seconds")
    print(f"Found {len(mutations)} valid mutations within ddG threshold of {max_ddg} kcal/mol")
    for seq, ddg in mutations[:10]:  # Print first 10 for brevity
        print(f"Sequence: {seq}, ddG: {ddg:.2f} kcal/mol")
    print("-------------------------", flush=True)

    start = time.time()
    
    mutations = pruned_mutation_search(
        original_sequence,  
        max_ddg,
        [6,8,6],
        ddg_tolerance=1.0
    )
    
    end = time.time()
    print(f"Time taken: {end - start:.2f} seconds")
    print(f"Found {len(mutations)} valid mutations within ddG threshold of {max_ddg} kcal/mol")
    for seq, ddg in mutations[:10]:  # Print first 10 for brevity
        print(f"Sequence: {seq}, ddG: {ddg:.2f} kcal/mol")
    print("-------------------------", flush=True)

    
    # start = time.time()
    
    # mutations = pruned_mutation_search_new(
    #     original_sequence,  
    #     max_ddg,
    #     [8,8,8],
    #     ddg_tolerance=5.0
    # )
    
    # end = time.time()
    # print(f"Time taken: {end - start:.2f} seconds")
    # print(f"Found {len(mutations)} valid mutations within ddG threshold of {max_ddg} kcal/mol")
    
    # start = time.time()

    # non_pruned_mutations = mutation_search(
    #     original_sequence,  
    #     max_ddg,
    #     [5,8,5],
    #     num_processes=64
    # )
    
    # end = time.time()
    # print(f"Time taken: {end - start:.2f} seconds")
    # print(f"Found {len(non_pruned_mutations)} valid mutations within ddG threshold of {max_ddg} kcal/mol")
    # for seq, ddg in non_pruned_mutations[:10]:  # Print first 10 for brevity
    #     print(f"Sequence: {seq}, ddG: {ddg:.2f} kcal/mol")

def main():
    # Setup logging
    setup_logging()
    logging.info("Pipeline starting up")
    logging.info("--------------------")

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Run the ASO Design pipeline to retrieve candidate ASOs for "
                    "selective gene of interest"
    )
    parser.add_argument(
        "--args", "-as",
        type=str,
        default="DEFAULT",
        help="Set of Arguments in config.ini to use (default=DEFAULT)"
    )
    args_set = parser.parse_args().args

    # Read configuration file
    config = read_config(args_set)
    
    index_name, index_dir, genome_dir = setup_environment(config)
    
    gtf_path, cdna_path, pep_path, genome_path, scaffold_gtf_path = download_genome(
        config["Species"],
        int(config["EnsembleRelease"]),
        genome_dir
    )
        
    
    tsl, tsl_list = convert_tsl_list(config["transcriptSupportLevels"])
    
    logging.info("-----------------------------------")
    
    maintest()
    sys.exit(0)
    try:
        oligo_obj = OligoExtractor(str(config["TargetGene"]), 
                                   int(config["EnsembleRelease"]), 
                                   int(config["GenomeAssembly"]), 
                                   int(config["OligoLen"]),
                                   tuple(map(float, config['GCbound'].split(','))),
                                   str(config["Species"]), 
                                   gtf_path,
                                   cdna_path,
                                   scaffold_gtf_path, 
                                   [int(x) for x in config["MultiplicityLayout"].split(',')],
                                   index_name, 
                                   os.path.join(config['DataDir']),
                                   ) 
        
    except Exception as e:
        logging.error(f"Error creating OligoExtractor object: {e}")
        logging.info("Exiting.")
        sys.exit(1)
        
    logging.info("-----------------------------------")
    
    try:             
        candidate_fasta_path = oligo_obj.extract_candidate_targets()
  
    except Exception as e:
        logging.error(f"Error during oligo extraction: {e}")
        logging.info("Exiting.")
        sys.exit(1)
        
    logging.info("-----------------------------------")

    try: 
        transcriptome_index_path = build_transcriptomic_bowtie_index(cdna_path,
                                        index_dir, 
                                        index_name,
                                        config["BowtieBuildIndexArgs"],
                                        tsl=tsl,
                                        genome=oligo_obj.genome,
                                        tsl_list=tsl_list)
    
    except Exception as e:
        logging.error(f"Error building Bowtie2 transcriptome index: {e}")
        logging.info("Exiting.")
        sys.exit(1)

    logging.info("-----------------------------------")
    
    try:
        genome_index_path = build_genomic_bowtie_index(genome_path,
                                        index_dir, 
                                        index_name,
                                        config["BowtieBuildIndexArgs"])
    except Exception as e:
        logging.error(f"Error building Bowtie2 genome index: {e}")
        logging.info("Exiting.")
        sys.exit(1)
    
    logging.info("-----------------------------------")

    # Run Bowtie2 for pre-filtering viable oligos
    try:
        bowtie_out = run_bowtie(candidate_fasta_path, 
                                transcriptome_index_path,
                                config["BowtieArgs"],
                                os.path.join(config['Bowtie2Dir'], 'bowtie2Home'),)
    except Exception as e:
        logging.error(f"Error running Bowtie2 for oligo pre-filtering: {e}")
        logging.info("Exiting.")
        sys.exit(1)
    
    logging.info("-----------------------------------")
        
    # filter viable kmers based on Bowtie output
    try:
        filtered_fasta_path = oligo_obj.filter_candidate_targets(bowtie_out)
        
    except Exception as e:
        logging.error(f"Error filtering viable kmers: {e}")
        logging.info("Exiting.")
        sys.exit(1)
        
    logging.info("-----------------------------------")
    
    try:
        cofold_in = os.path.join(config['DataDir'], 
                                 'RNACofold', 
                                 os.path.basename(filtered_fasta_path)
                                 .replace(".fa", 
                                          ".rnacofoldin"))
                    
        build_RNAcofold_in(cofold_in, oligo_obj.candidate_targets)   
        cofold_out = run_RNAcofold(cofold_in, config["CofoldParamFile"])
        
    except Exception as e:
        logging.error(f"Error getting binding affinity: {e}")
        logging.info("Exiting.")
        sys.exit(1)
    
    try:
        oligo_obj.add_dg_to_targets(cofold_out)
    except Exception as e:
        logging.error(f"Error adding binding affinity to targets: {e}")
        logging.info("Exiting.")
        sys.exit(1)
        
        
    logging.info("-----------------------------------")
    
    try:
        gene_index_path = build_transcriptomic_bowtie_index(cdna_path,
                           index_dir, 
                           index_name,
                           config["BowtieBuildIndexArgs"],
                           gene_only=True,
                           gene_id=oligo_obj.gene_id)
        
    except Exception as e:
        logging.error(f"Error building Bowtie2 target gene index: {e}")
        logging.info("Exiting.")
        sys.exit(1)
        
    logging.info("-----------------------------------")
        
    try:      
        bowtie_repeated_out = run_bowtie(filtered_fasta_path, 
                                          gene_index_path,
                                          config["BowtieArgs"],
                                          os.path.join(config['Bowtie2Dir'], 'bowtie2Home'),
                                          trim=True,
                                          multiplicity_layout=oligo_obj.multiplicity_layout)
        
    except Exception as e:
        logging.error(f"Error running Bowtie2 for target gene: {e}")
        logging.info("Exiting.")
        sys.exit(1)
        
    logging.info("-----------------------------------")

    try:
        oligo_obj.extract_repeated_sites(bowtie_repeated_out)
    except Exception as e:
        logging.error(f"Error extracting repeated sites: {e}")
        logging.info("Exiting.")
        sys.exit(1)
        
        
    try:
        cofold_in_repeated = cofold_in.replace(".rnacofoldin", "_repeated.rnacofoldin")

        build_RNAcofold_in(cofold_in_repeated, oligo_obj.repeated_sites, oligo_obj.candidate_targets)
        cofold_out_repeated = run_RNAcofold(cofold_in_repeated, config["CofoldParamFile"])
        
    except Exception as exc:
        logging.error("Error getting binding affinity for repeated target sites: %s", exc)
        logging.info("Exiting.")
        sys.exit(1)
    
    try:
        oligo_obj.filter_repeated_sites_by_ddg(cofold_out_repeated)
    except Exception as e:
        logging.error(f"Error filtering repeated sites by ddG: {e}")
        logging.info("Exiting.")
        sys.exit(1)
        
    logging.info("-----------------------------------")

    try:
        bowtie_offtarget_out = run_bowtie(filtered_fasta_path, 
                                genome_index_path,
                                config["BowtieArgs"],
                                os.path.join(config['Bowtie2Dir'], 'bowtie2Home'),
                                trim=True,
                                multiplicity_layout=oligo_obj.multiplicity_layout)
    except Exception as e:
        logging.error(f"Error running Bowtie2 for specific off-targets: {e}")
        logging.info("Exiting.")
        sys.exit(1)


    logging.info("-----------------------------------")
    
    # try:
    #     oligo_obj.extract_offtarget_sites(bowtie_offtarget_out)
    # except Exception as e:
    #     logging.error(f"Error extracting off-target sites: {e}")
    #     logging.info("Exiting.")
    #     sys.exit(1)

    
    # try:
    #     oligo_obj.store_kmer_results(cofold_out, cofold_out_repeated)
    # except Exception as e:
    #     logging.error(f"Error writing kmer results to file: {e}")
    #     logging.info("Exiting.")
    #     sys.exit(1)
        
    # logging.info("Pipeline completed successfully.")

if __name__ == '__main__':
    main()