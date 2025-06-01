# -*- coding: utf-8 -*-
import argparse
import sys
from src.utils.file_operations import (
    build_genomic_bowtie_index,
    build_transcriptomic_bowtie_index, 
    run_bowtie,
    GenomeDownloader,
    create_job_config_summary,
    )
from src.utils.sequence_analysis import (
    find_potential_secondary_sites,
    convert_tsl_list,
    PedersenAnalysis,
    )
from src.kmer_counter import KmerCounter
import logging
from src.oligo_extractor import OligoExtractor
import configparser
import os
import multiprocessing as mp
import RNA
import time
from typing import Optional, Dict, Tuple, Any, List
import json


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
        bowtie_index_name = f'GRCm{int(config["GenomeAssembly"])}_{int(config["EnsembleRelease"])}'
    elif config["Species"] == "homo_sapiens":
        bowtie_index_name = f'GRCh{int(config["GenomeAssembly"])}_{int(config["EnsembleRelease"])}'
    else:
        logging.error("Only mus_musculus and homo_sapiens species implemented. Please set appropriate species in config.ini.")
        logging.info("Exiting.")
        sys.exit(1)

    try:
        bowtie_index_dir = os.path.join(config['Bowtie2Dir'], bowtie_index_name)
        os.makedirs(bowtie_index_dir, exist_ok=True)

        kmc_index_dir = config['KMCDir']
        os.makedirs(kmc_index_dir, exist_ok=True)

        genome_data_dir = os.path.join(config['GenomeDir'], bowtie_index_name)
        os.makedirs(genome_data_dir, exist_ok=True)
        
        if not job_name:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            job_name = f"{config['TargetGene']}_{timestamp}"
            logging.info(f"No job name provided, generated job name: {job_name}")
        
        data_dir = os.path.join(config['DataDir'], 'jobs', job_name)

        logging.info(f"Using job-specific directory: {data_dir}")
        
        os.makedirs(os.path.join(data_dir, 'oligos'), exist_ok=True)
        os.makedirs(os.path.join(data_dir, 'results'), exist_ok=True)
        
        
        os.makedirs(bowtie_index_dir, exist_ok=True)
        os.makedirs(kmc_index_dir, exist_ok=True)
        
        create_job_config_summary(data_dir, config)
        
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
    
    vienna_params_path = config["CofoldParamFile"]
    if vienna_params_path:
        RNA.params_load(vienna_params_path)

    return bowtie_index_name, bowtie_index_dir, genome_data_dir, kmc_index_dir, data_dir

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
    index_name, index_dir, genome_dir, kmc_dir, data_dir = setup_environment(config, job_name)

    # Instantiate and call GenomeDownloader
    genome_downloader = GenomeDownloader(
        species=config["Species"],
        e_release=int(config["EnsembleRelease"]),
        genome_dir=genome_dir
    )
    gtf_path, cdna_path, genome_path, scaffold_gtf_path = genome_downloader.download()


    tsl, tsl_list = convert_tsl_list(config["transcriptSupportLevels"])
    logging.info("-----------------------------------")

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
                                   data_dir,
                                   genome_path
                                   ) 
    except Exception as e:
        logging.error(f"Error creating OligoExtractor object: {e}")
        logging.info("Exiting.")
        sys.exit(1)
        
    logging.info("-----------------------------------")
    
    
    # Build Bowtie2 index for transcriptome
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
    
    
    
    
    # # Build Bowtie2 index for genome
    # try:
    #     genome_index_path = build_genomic_bowtie_index(genome_path,
    #                                     index_dir, 
    #                                     index_name,
    #                                     config["BowtieBuildIndexArgs"])
    # except Exception as e:
    #     logging.error(f"Error building Bowtie2 genome index: {e}")
    #     logging.info("Exiting.")
    #     sys.exit(1)
        
    # logging.info("-----------------------------------")
    
    try:             
        candidate_fasta_path = oligo_obj.extract_candidate_targets()
    except Exception as e:
        logging.error(f"Error during oligo extraction: {e}")
        logging.info("Exiting.")
        sys.exit(1)
        
    logging.info("-----------------------------------")


    # Run Bowtie2 for pre-filtering viable oligos
    try:
        bowtie_out = run_bowtie(candidate_fasta_path, 
                                transcriptome_index_path,
                                config["BowtieArgs"],
                                )
    except Exception as e:
        logging.error(f"Error running Bowtie2 for oligo pre-filtering: {e}")
        logging.info("Exiting.")
        sys.exit(1)
    
    logging.info("-----------------------------------")
        
    try:
        filtered_fasta_path = oligo_obj.filter_candidate_targets(bowtie_out)
    except Exception as e:
        logging.error(f"Error filtering viable kmers: {e}")
        logging.info("Exiting.")
        sys.exit(1)
    
    logging.info("-----------------------------------")
    
    try:
        pedersen_params_file = config.get('PedersenParamFile', None)
        
        pedersen_analyzer = PedersenAnalysis(
            candidate_targets=oligo_obj.candidate_targets,
            num_processes=config.getint("NumProcesses", mp.cpu_count()),
            params_file_path=pedersen_params_file
        )
        
        oligo_obj.candidate_targets = pedersen_analyzer.run_analysis()
    except Exception as e:
        logging.error(f"Error during Pedersen analysis: {e}")
        logging.info("Exiting.")
        sys.exit(1)
        
    logging.info("-----------------------------------")
    
    # Build Bowtie2 index for target gene
    # try:
    #     gene_index_path = build_transcriptomic_bowtie_index(cdna_path,
    #                        index_dir, 
    #                        index_name,
    #                        config["BowtieBuildIndexArgs"],
    #                        gene_only=True,
    #                        gene_id=oligo_obj.gene_id)
    # except Exception as e:
    #     logging.error(f"Error building Bowtie2 target gene index: {e}")
    #     logging.info("Exiting.")
    #     sys.exit(1)
     
    # logging.info("-----------------------------------")
      
    
    # # Run Bowtie2 to find repeated sites in target gene
    # try:      
    #     bowtie_repeated_out = run_bowtie(filtered_fasta_path, 
    #                                       gene_index_path,
    #                                       config["BowtieArgs"],
    #                                       trim=True,
    #                                       multiplicity_layout=oligo_obj.multiplicity_layout)
    # except Exception as e:
    #     logging.error(f"Error running Bowtie2 for target gene: {e}")
    #     logging.info("Exiting.")
    #     sys.exit(1)
        
    # logging.info("-----------------------------------")

    try:
        repeated_sites_path = filtered_fasta_path.replace(".fa", "_repeated_sites.fa")
        oligo_obj.extract_repeated_sites(max_ddg_threshold=float(config["RepeatedMaxddG"]), 
                                         force_core_alignment=True,
                                         output_file=repeated_sites_path)
    except Exception as e:
        logging.error(f"Error extracting repeated sites: {e}")
        logging.info("Exiting.")
        sys.exit(1)
        
    logging.info("-----------------------------------")
    
    try:
        potential_secondary_sites_path = filtered_fasta_path.replace(".fa", "_potential_secondary_sites.fa")
        potential_secondary_sites = find_potential_secondary_sites(
            oligo_obj.candidate_targets,
            max_ddg=float(config["OffTargetMaxddG"]),
            multiplicity_layout=oligo_obj.multiplicity_layout,
            ddg_tolerance=float(config["ddGTolerance"]),
            output_fasta_path=potential_secondary_sites_path,
        )
    except Exception as e:
        logging.error(f"Error calculating pruned mutations: {e}")
        logging.info("Exiting.")
        sys.exit(1)
        
    logging.info("-----------------------------------")
    
    logging.info("Starting KmerCounter analysis...")

    
    pre_mrna_fasta_path = oligo_obj.pre_mrna_fasta_path

    if not os.path.exists(pre_mrna_fasta_path):
        logging.error(f"KmerCounter pre-mRNA FASTA file not found: {pre_mrna_fasta_path}")
        logging.error("Please ensure this file exists and the path construction is correct.")
        # Decide if to exit or continue without KmerCounter
        # For now, let's log an error and skip KmerCounter if file not found.
        kmer_counter_instance = None
    else:
        try:
            kmer_counter_init_start_time = time.time()
            kmer_counter_instance = KmerCounter(
                pre_mrna_fasta_path=pre_mrna_fasta_path,
                potential_secondary_sites=potential_secondary_sites,
                k=oligo_obj.k, # k from OligoExtractor
                # Optional: pull KMC paths and params from config if needed
                # kmc_path=config.get("KMCPath", "kmc"),
                # kmc_tools_path=config.get("KMCToolsPath", "kmc_tools"),
                kmc_db_threads=config.getint("KMCDbThreads", 64),
                kmc_db_memory_gb=config.getint("KMCDbMemoryGB", 128),
                gene_processing_workers=config.getint("KMCGeneProcessingWorkers", 64),
                temp_dir_base=kmc_dir, # Use the KMC directory configured earlier for temp files
                total_genes_for_matrix=len(oligo_obj.genome.genes)
            )
            kmer_counter_init_end_time = time.time()
            logging.info(f"KmerCounter initialized in {kmer_counter_init_end_time - kmer_counter_init_start_time:.2f} seconds.")

        except Exception as e:
            logging.error(f"Error initializing KmerCounter: {e}")
            kmer_counter_instance = None # Ensure it's None if init fails

    if kmer_counter_instance:
        try:
            logging.info("Calculating aggregate k-mer counts...")
            agg_counts_start_time = time.time()
            aggregate_aso_counts = kmer_counter_instance.calculate_aggregate_counts()
            agg_counts_end_time = time.time()
            logging.info(f"Calculated aggregate counts for {len(aggregate_aso_counts)} ASOs in {agg_counts_end_time - agg_counts_start_time:.2f} seconds.")
            # logging.info(f"Aggregate ASO counts: {aggregate_aso_counts}")
            # Optionally, save to a file in data_dir/results
            agg_counts_path = os.path.join(data_dir, 'results', f"{job_name or oligo_obj.gene_id}_aggregate_kmer_counts.json")
            with open(agg_counts_path, 'w') as f_agg:
                json.dump(aggregate_aso_counts, f_agg, indent=4)
            logging.info(f"Aggregate k-mer counts saved to {agg_counts_path}")

        except Exception as e:
            logging.error(f"Error during KmerCounter aggregate counts: {e}")

    #     # 2. Calculate and time per-gene counts matrix
    #     try:
    #         logging.info("Calculating per-gene k-mer counts matrix...")
    #         matrix_start_time = time.time()
    #         aso_gene_matrix = kmer_counter_instance.calculate_per_gene_counts_matrix()
    #         matrix_end_time = time.time()
            
    #         if aso_gene_matrix is not None:
    #             logging.info(f"Calculated ASO x Gene matrix with shape {aso_gene_matrix.shape} in {matrix_end_time - matrix_start_time:.2f} seconds.")
    #             # logging.info(f"ASO x Gene matrix:\n{aso_gene_matrix}")
    #             # Optionally, save to a file in data_dir/results
    #             matrix_path = os.path.join(data_dir, 'results', f"{job_name or oligo_obj.gene_id}_aso_gene_kmer_matrix.parquet") # Or .csv
    #             try:
    #                 aso_gene_matrix.write_parquet(matrix_path)
    #                 logging.info(f"ASO x Gene k-mer matrix saved to {matrix_path}")
    #             except Exception as e_save:
    #                 logging.error(f"Error saving ASO x Gene matrix to Parquet: {e_save}")
    #                 # Fallback to CSV if Parquet fails or if preferred
    #                 matrix_csv_path = os.path.join(data_dir, 'results', f"{job_name or oligo_obj.gene_id}_aso_gene_kmer_matrix.csv")
    #                 try:
    #                     aso_gene_matrix.write_csv(matrix_csv_path)
    #                     logging.info(f"ASO x Gene k-mer matrix saved to {matrix_csv_path}")
    #                 except Exception as e_csv_save:
    #                     logging.error(f"Error saving ASO x Gene matrix to CSV: {e_csv_save}")
    #         else:
    #             logging.warning(f"ASO x Gene matrix calculation did not return a DataFrame. Elapsed time: {matrix_end_time - matrix_start_time:.2f} seconds.")

    #     except Exception as e:
    #         logging.error(f"Error during KmerCounter per-gene counts matrix: {e}")
    # else:
    #     logging.warning("KmerCounter instance not available. Skipping k-mer counting steps.")

    logging.info("-----------------------------------")
    
    
    try:      
        bowtie_offtarget_out = run_bowtie(potential_secondary_sites_path, 
                                         transcriptome_index_path,
                                         config["BowtieArgs"],
                                         )
    except Exception as e:
        logging.error(f"Error running Bowtie2 for secondary sites: {e}")
        logging.info("Exiting.")
        sys.exit(1)
    
    logging.info("-----------------------------------")
    
    try:
        oligo_obj.extract_offtarget_sites(bowtie_offtarget_out)
    except Exception as e:
        logging.error(f"Error extracting off-target sites: {e}")
        logging.info("Exiting.")
        sys.exit(1)

    logging.info("-----------------------------------")

    oligo_obj.store_kmer_results()
    logging.info("Pipeline completed successfully.")

if __name__ == '__main__':
    main()