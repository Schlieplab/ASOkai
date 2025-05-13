# -*- coding: utf-8 -*-
import argparse
import sys
from src.utils.file_operations import (
    build_genomic_bowtie_index,
    build_transcriptomic_bowtie_index, 
    run_bowtie,
    download_genome,
    create_job_config_summary,
    )
from src.utils.sequence_analysis import (
    find_potential_secondary_sites,
    )
import logging
from src.oligo_extractor import OligoExtractor
import configparser
import os
import multiprocessing as mp
import RNA
import time
from typing import Optional


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
    
    return config_parser[args_set]
    
def convert_tsl_list(tsl_str):
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
        bowtie_index_dir = os.path.join(config['Bowtie2Dir'], "bowtie2Home", bowtie_index_name)
        os.makedirs(bowtie_index_dir, exist_ok=True)

        genome_data_dir = os.path.join(config['GenomeDir'], 'genome', bowtie_index_name)
        os.makedirs(genome_data_dir, exist_ok=True)
        
        if not job_name:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            job_name = f"{config['TargetGene']}_{timestamp}"
            logging.info(f"No job name provided, generated job name: {job_name}")
        
        data_dir = os.path.join(config['DataDir'], 'jobs', job_name)
        logging.info(f"Using job-specific directory: {data_dir}")
        
        os.makedirs(os.path.join(data_dir, 'oligos'), exist_ok=True)
        os.makedirs(os.path.join(data_dir, 'results'), exist_ok=True)
        os.makedirs(os.path.join(data_dir, 'bowtie2'), exist_ok=True)
        
        create_job_config_summary(data_dir, config)
        config['DataDir'] = data_dir
        
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

    return bowtie_index_name, bowtie_index_dir, genome_data_dir

def main():
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
    index_name, index_dir, genome_dir = setup_environment(config, job_name)
    
    gtf_path, cdna_path, pep_path, genome_path, scaffold_gtf_path = download_genome(
        config["Species"],
        int(config["EnsembleRelease"]),
        genome_dir
    )
    
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
                                   os.path.join(config['DataDir']),
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
    
    
    # Build Bowtie2 index for genome
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
    
    
    # Build Bowtie2 index for target gene
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
      
    
    # Run Bowtie2 to find repeated sites in target gene
    try:      
        bowtie_repeated_out = run_bowtie(filtered_fasta_path, 
                                          gene_index_path,
                                          config["BowtieArgs"],
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
        
    logging.info("-----------------------------------")
    
    try:
        potential_secondary_sites_path = filtered_fasta_path.replace(".fa", "_potential_secondary_sites.fa")
        find_potential_secondary_sites(
            oligo_obj.candidate_targets,
            max_ddg=float(config["MaxddG"]),
            multiplicity_layout=oligo_obj.multiplicity_layout,
            ddg_tolerance=float(config["ddGTolerance"]),
            output_fasta_path=potential_secondary_sites_path,
        )
    except Exception as e:
        logging.error(f"Error calculating pruned mutations: {e}")
        logging.info("Exiting.")
        sys.exit(1)
        
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