# -*- coding: utf-8 -*-
import argparse
import sys

from src import (
    PedersenAnalysis,
    SecondarySiteFinder,
    RNACofold,
    )
import logging
import configparser
import os
import polars as pl
import time
from typing import Optional, Dict, Tuple, Any, List
from src import CandidateTargetsManager, KmerCounter, ResultsGenerator, GenomeDataManager
import multiprocessing as mp

def create_job_config_summary(job_dir: str, config: dict) -> None:
    """
    Create a summary file containing all configuration Parameters: used for the job.
    
    Parameters:
        job_dir (str): Path to the job directory
        config (dict): Dictionary containing all configuration Parameters:
    """
    config_file = os.path.join(job_dir, 'job_config.txt')
    
    with open(config_file, 'w') as f:
        f.write("Job Configuration Summary\n")
        f.write("=======================\n\n")
        f.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        for key, value in config.items():
            f.write(f"{key}: {value}\n")
            
    logging.info(f"Job configuration summary written to {config_file}")

def convert_tsl_list(tsl_str: str) -> Optional[List[Optional[int]]]:
        """
        Convert a string of transcript support levels into a list of integers or None values.
        
        Parameters:
            tsl_str (str): Comma-separated string of transcript support levels (e.g., "tsl1,tsl2,tslNA")
            
        Returns:
            Optional[List[Optional[int]]]: List of TSL values (1-5 or None for NA), or None if all TSLs are included
        """
        if tsl_str == "all" or tsl_str == "":
            return None
        
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
            return None
        return converted_tsls 
    
def setup_logging() -> None:
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
    
    return config_parser[args_set]
    
def setup_environment(config, job_name: Optional[str] = None):
    if config["Species"] == "mus_musculus":
        reference_name = f'GRCm{int(config["GenomeAssembly"])}_{int(config["EnsembleRelease"])}'
    elif config["Species"] == "homo_sapiens":
        reference_name = f'GRCh{int(config["GenomeAssembly"])}_{int(config["EnsembleRelease"])}'
    else:
        logging.error("Only mus_musculus and homo_sapiens species implemented. Please set appropriate species in config.ini.")
        logging.info("Exiting.")
        sys.exit(1)

    try:


        genome_data_dir = os.path.join(config['GenomeDir'], reference_name)
        os.makedirs(genome_data_dir, exist_ok=True)
        
        if not job_name:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            job_name = f"{config['TargetGene']}_{timestamp}"
            logging.info(f"No job name provided, generated job name: {job_name}")
        
        data_dir = os.path.join(config['JobDir'], 'jobs', job_name)

        logging.info(f"Using job-specific directory: {data_dir}")
        
        os.makedirs(os.path.join(data_dir, 'oligos'), exist_ok=True)
        os.makedirs(os.path.join(data_dir, 'results'), exist_ok=True)
        
        
        
        create_job_config_summary(data_dir, config)
        
    except Exception as e:
        logging.error(f"Error creating directories: {e}")
        logging.info("Exiting.")
        sys.exit(1)


    return reference_name, genome_data_dir, data_dir

def main() -> None:
    setup_logging()
    logging.info("Pipeline starting up")
    logging.info("--------------------")

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
    parser.add_argument(
        "--job", "-j",
        type=str,
        help="Job name for organizing output files (optional)"
    )
    args = parser.parse_args()
    args_set = args.args
    job_name = args.job

    config = read_config(args_set)
    index_name, genome_dir, data_dir = setup_environment(config, job_name)

    logging.info("-----------------------------------")

    rna_cofold = RNACofold(params_file_path=config.get("RNACofoldParamFile", None))

    genome_data_manager = GenomeDataManager(
        gene_id=config["TargetGene"],
        species=config["Species"],
        e_release=int(config["EnsembleRelease"]),
        genome_assembly=int(config["GenomeAssembly"]),
        genome_dir=genome_dir,
        data_dir=data_dir,
        tsl_list_to_keep=convert_tsl_list(config.get("transcriptSupportLevels", "")),
        protein_coding_only=config.getboolean("ProteinCodingOnly", False),
        verbose=config.getboolean("Verbose", False)
    )
    
    logging.info("-----------------------------------")

    candidate_targets_manager = CandidateTargetsManager(
        target_gene=genome_data_manager.get_target_gene_object(),
        k=int(config["OligoLen"]),
        gc_bounds=tuple(map(float, config.get("GCbound", ("0.0,1.0")).split(','))),
        rna_cofold=rna_cofold,
        multiplicity_layout=list(map(int, config.get("MultiplicityLayout", "").split(','))),
        verbose=config.getboolean("Verbose", False)
    )

    candidate_targets_manager.extract_candidate_targets()


    logging.info("-----------------------------------")

    kmer_counter = KmerCounter(
        k=int(config["OligoLen"]),
        kmc_path=config.get("KMCPath", "kmc"),
        kmc_tools_path=config.get("KMCToolsPath", "kmc_tools"),
        kmc_db_threads=config.getint("NumProcesses", mp.cpu_count()),
        gene_processing_workers=config.getint("NumProcesses", mp.cpu_count()),
        kmc_db_memory_gb=config.getint("MaxMemory", 64),
        temp_dir_base=os.path.join(data_dir, 'temp'),
        verbose=False
    )
    
    candidates_present_in_cdna = kmer_counter.find_present_targets(
        fasta_path=genome_data_manager.get_processed_cdna_excluding_target_path(),
        candidate_sites_kmers=candidate_targets_manager.get_candidates_as_dict()
    )

    candidate_targets_manager.filter_candidates_by_id_list(ids_to_remove=candidates_present_in_cdna)
    
    logging.info("-----------------------------------")
    
    # candidate_targets_manager.find_repeated_sites(force_core_alignment_dG=True, 
    #                                               max_ddg_threshold=float(config.get("RepeatedMaxddG", 5.0)))
    
    # logging.info("-----------------------------------")
    
    
    secondary_site_finder = SecondarySiteFinder(
        max_ddg=float(config.get("OffTargetMaxddG", 5.0)),
        multiplicity_layout=list(map(int, config.get("MultiplicityLayout", "4,8,4").split(','))),
        ddg_tolerance=float(config.get("ddGTolerance", 0.5)),
        num_processes=config.getint("NumProcesses", mp.cpu_count()),
        rna_cofold=rna_cofold,
        verbose=config.getboolean("Verbose", False)
    )
    
    potential_secondary_sites = secondary_site_finder.find_sites(
        target_sites=candidate_targets_manager.get_all_candidate_targets(),
    )
    
    secondary_sites_counts = kmer_counter.calculate_aggregate_counts(
        pre_mrna_fasta_path=genome_data_manager.get_genes_pre_mrna_fasta_excludint_target_path(),
        potential_kmers_by_aso=potential_secondary_sites
    )
    logging.info("-----------------------------------")


    # pedersen_analyzer = PedersenAnalysis(
    #     candidate_targets=candidate_targets_manager.get_all_candidate_targets(),
    #     num_processes=config.getint("NumProcesses", mp.cpu_count()),
    #     params_file_path=config.get("PedersenParamFile", None),
    #     verbose=config.getboolean("Verbose", False)
    # )
    
    # candidate_targets_manager.update_pedersen_steady_state(pedersen_results=pedersen_analyzer.run_analysis())
    
    # logging.info("-----------------------------------")
    
    # results_generator = ResultsGenerator(
    #     candidate_manager=candidate_targets_manager,
    #     target_gene_species=config["Species"],
    #     base_output_dir=data_dir
    # )
    
    # results_generator.generate_csv_report(off_target_multiplicities=secondary_sites_counts)
            
#     try:
#         pedersen_params_file = config.get('PedersenParamFile', None)
        
#         pedersen_analyzer = PedersenAnalysis(
#             candidate_targets=oligo_obj.candidate_targets,
#             num_processes=config.getint("NumProcesses", mp.cpu_count()),
#             params_file_path=pedersen_params_file
#         )
        
#         oligo_obj.candidate_targets = pedersen_analyzer.run_analysis()
#     except Exception as e:
#         logging.error(f"Error during Pedersen analysis: {e}")
#         logging.info("Exiting.")
#         sys.exit(1)
        
#     logging.info("-----------------------------------")
    
    
#     # Calculate potential secondary sites (mutations)
#     potential_secondary_sites_path = os.path.join(data_dir, 'oligos', f"{oligo_obj.gene_id}_potential_secondary_sites.fa")
#     try:
#         finder = SecondarySiteFinder(
#             max_ddg=float(config["OffTargetMaxddG"]),
#             multiplicity_layout=oligo_obj.multiplicity_layout,
#             ddg_tolerance=float(config["ddGTolerance"]),
#             num_processes=config.getint("NumProcesses", mp.cpu_count())
#         )
#         potential_secondary_sites = finder.find_sites(
#             target_sites=oligo_obj.candidate_targets,
#             output_fasta_path=potential_secondary_sites_path
#         )
#     except Exception as e:
#         logging.error(f"Error calculating potential secondary sites: {e}")
#         logging.info("Exiting.")
#         sys.exit(1)
        
#     logging.info("-----------------------------------")
    
#     logging.info("Starting KmerCounter analysis...")

    
#     pre_mrna_fasta_path = oligo_obj.pre_mrna_fasta_path

#     if not os.path.exists(pre_mrna_fasta_path):
#         logging.error(f"KmerCounter pre-mRNA FASTA file not found: {pre_mrna_fasta_path}")
#         logging.error("Please ensure this file exists and the path construction is correct.")
#         # Decide if to exit or continue without KmerCounter
#         # For now, let's log an error and skip KmerCounter if file not found.
#         kmer_counter_instance = None
#     else:
#         try:
#             kmer_counter_init_start_time = time.time()
#             kmer_counter_instance = KmerCounter(
#                 pre_mrna_fasta_path=pre_mrna_fasta_path,
#                 potential_secondary_sites=potential_secondary_sites,
#                 k=oligo_obj.k, # k from OligoExtractor
#                 # Optional: pull KMC paths and params from config if needed
#                 # kmc_path=config.get("KMCPath", "kmc"),
#                 # kmc_tools_path=config.get("KMCToolsPath", "kmc_tools"),
#                 kmc_db_threads=config.getint("KMCDbThreads", 64),
#                 kmc_db_memory_gb=config.getint("KMCDbMemoryGB", 128),
#                 gene_processing_workers=config.getint("KMCGeneProcessingWorkers", 64),
#                 temp_dir_base=kmc_dir, # Use the KMC directory configured earlier for temp files
#                 total_genes_for_matrix=len(oligo_obj.genome.genes)
#             )
#             kmer_counter_init_end_time = time.time()
#             logging.info(f"KmerCounter initialized in {kmer_counter_init_end_time - kmer_counter_init_start_time:.2f} seconds.")

#         except Exception as e:
#             logging.error(f"Error initializing KmerCounter: {e}")
#             kmer_counter_instance = None # Ensure it's None if init fails

#     if kmer_counter_instance:
#         try:
#             logging.info("Calculating aggregate k-mer counts...")
#             agg_counts_start_time = time.time()
#             aggregate_aso_counts = kmer_counter_instance.calculate_aggregate_counts()
#             agg_counts_end_time = time.time()
#             logging.info(f"Calculated aggregate counts for {len(aggregate_aso_counts)} ASOs in {agg_counts_end_time - agg_counts_start_time:.2f} seconds.")
#             # logging.info(f"Aggregate ASO counts: {aggregate_aso_counts}")
#             # Optionally, save to a file in data_dir/results
#             agg_counts_path = os.path.join(data_dir, 'results', f"{job_name or oligo_obj.gene_id}_aggregate_kmer_counts.json")
#             with open(agg_counts_path, 'w') as f_agg:
#                 json.dump(aggregate_aso_counts, f_agg, indent=4)
#             logging.info(f"Aggregate k-mer counts saved to {agg_counts_path}")

#         except Exception as e:
#             logging.error(f"Error during KmerCounter aggregate counts: {e}")

#     #     # 2. Calculate and time per-gene counts matrix
#     #     try:
#     #         logging.info("Calculating per-gene k-mer counts matrix...")
#     #         matrix_start_time = time.time()
#     #         aso_gene_matrix = kmer_counter_instance.calculate_per_gene_counts_matrix()
#     #         matrix_end_time = time.time()
            
#     #         if aso_gene_matrix is not None:
#     #             logging.info(f"Calculated ASO x Gene matrix with shape {aso_gene_matrix.shape} in {matrix_end_time - matrix_start_time:.2f} seconds.")
#     #             # logging.info(f"ASO x Gene matrix:\n{aso_gene_matrix}")
#     #             # Optionally, save to a file in data_dir/results
#     #             matrix_path = os.path.join(data_dir, 'results', f"{job_name or oligo_obj.gene_id}_aso_gene_kmer_matrix.parquet") # Or .csv
#     #             try:
#     #                 aso_gene_matrix.write_parquet(matrix_path)
#     #                 logging.info(f"ASO x Gene k-mer matrix saved to {matrix_path}")
#     #             except Exception as e_save:
#     #                 logging.error(f"Error saving ASO x Gene matrix to Parquet: {e_save}")
#     #                 # Fallback to CSV if Parquet fails or if preferred
#     #                 matrix_csv_path = os.path.join(data_dir, 'results', f"{job_name or oligo_obj.gene_id}_aso_gene_kmer_matrix.csv")
#     #                 try:
#     #                     aso_gene_matrix.write_csv(matrix_csv_path)
#     #                     logging.info(f"ASO x Gene k-mer matrix saved to {matrix_csv_path}")
#     #                 except Exception as e_csv_save:
#     #                     logging.error(f"Error saving ASO x Gene matrix to CSV: {e_csv_save}")
#     #         else:
#     #             logging.warning(f"ASO x Gene matrix calculation did not return a DataFrame. Elapsed time: {matrix_end_time - matrix_start_time:.2f} seconds.")

#     #     except Exception as e:
#     #         logging.error(f"Error during KmerCounter per-gene counts matrix: {e}")
#     # else:
#     #     logging.warning("KmerCounter instance not available. Skipping k-mer counting steps.")

#     logging.info("-----------------------------------")
    

#     oligo_obj.store_kmer_results()
#     logging.info("Pipeline completed successfully.")

if __name__ == '__main__':
    main()