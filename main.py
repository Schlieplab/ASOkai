# -*- coding: utf-8 -*-
import argparse
import sys
from utils.file_operations import (
    build_bowtie_index, 
    build_RNAcofold_in, 
    run_bowtie,
    run_RNAcofold,
    download_genome,
    )
import logging
from src.oligo_extractor import OligoExtractor
import configparser
import os


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
        
        os.makedirs(os.path.join(config['OligoDir'], 'oligos'), exist_ok=True)
        os.makedirs(os.path.join(config['OligoDir'], 'results'), exist_ok=True)
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
    
    gtf_path, cdna_path, pep_path, scaffold_gtf_path = download_genome(config["Species"],
                                                                       int(config["EnsembleRelease"]),
                                                                       genome_dir)
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
                                   pep_path,
                                   scaffold_gtf_path, 
                                   [int(x) for x in config["MultiplicityLayout"].split(',')],
                                   index_name, 
                                   str(config['OligoDir']),
                                   ) 
        
    except Exception as e:
        logging.error(f"Error creating OligoExtractor object: {e}")
        logging.info("Exiting.")
        sys.exit(1)
        
    logging.info("-----------------------------------")
    
    try:
        bowtie_infile = os.path.join(config['Bowtie2Dir'],
                                     "bowtie2Home",
                                     f"{config['TargetGene']}_{config['OligoLen']}mers.fa")
                        
        oligo_obj.extract_candidate_oligos_by_gene(bowtie_infile)
  
    except Exception as e:
        logging.error(f"Error during oligo extraction: {e}")
        logging.info("Exiting.")
        sys.exit(1)
        
    logging.info("-----------------------------------")

    try: 
        index_path = build_bowtie_index(cdna_path,
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

    # Run Bowtie2 for pre-filtering viable oligos
    try:
        bowtie_out = run_bowtie(bowtie_infile, 
                                index_path,
                                config["BowtieArgs"])
    except Exception as e:
        logging.error(f"Error running Bowtie2 for oligo pre-filtering: {e}")
        logging.info("Exiting.")
        sys.exit(1)
    
    logging.info("-----------------------------------")
        
    # Extract viable kmers based on Bowtie output
    try:
        bowtie_offtarget_infile = f"{config['Bowtie2Dir']}/bowtie2Home/" + \
                f'{config["TargetGene"]}_{config["OligoLen"]}mers_filtered.fa'
        oligo_obj.extract_viable_kmers(bowtie_out, bowtie_offtarget_infile)
        
    except Exception as e:
        logging.error(f"Error extracting viable kmers: {e}")
        logging.info("Exiting.")
        sys.exit(1)
        
    logging.info("-----------------------------------")

    try:
        bowtie_out = run_bowtie(bowtie_offtarget_infile, 
                                index_path,
                                config["BowtieArgs"],
                                trim=True,
                                multiplicity_layout=oligo_obj.multiplicity_layout)
    except Exception as e:
        logging.error(f"Error running Bowtie2 for specific off-targets: {e}")
        logging.info("Exiting.")
        sys.exit(1)

    logging.info("-----------------------------------")

    try:
        cofold_in = f"{config['OligoDir']}/oligos/{index_name}_{config['TargetGene']}" + \
                    f"_filtered_{config['OligoLen']}mers.rnacofoldin"
                    
        build_RNAcofold_in(cofold_in, oligo_obj.filtered_kmers)   
        cofold_out = run_RNAcofold(cofold_in, " -P "+ config["CofoldParamFile"])
        
    except Exception as e:
        logging.error(f"Error getting binding affinity: {e}")
        logging.info("Exiting.")
        sys.exit(1)
    
    logging.info("-----------------------------------")
    
    try:
        gene_index_path = build_bowtie_index(cdna_path,
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
        bowtie_out_gene_only = run_bowtie(bowtie_infile, 
                                          gene_index_path,
                                          config["BowtieArgs"],
                                          gene_only=True,
                                          gene_id=oligo_obj.gene_id,
                                          trim=True,
                                          multiplicity_layout=oligo_obj.multiplicity_layout)
        
    except Exception as e:
        logging.error(f"Error running Bowtie2 for target gene: {e}")
        logging.info("Exiting.")
        sys.exit(1)
        
        

    try:
        oligo_obj.extract_repeated_sites(bowtie_out_gene_only)
    except Exception as e:
        logging.error(f"Error extracting repeated sites: {e}")
        logging.info("Exiting.")
        sys.exit(1)
        
        
        
    try:
        cofold_in_repeated = (
            f"{config['OligoDir']}/oligos/{index_name}_{config['TargetGene']}_prone_"
            f"{int(config['OligoLen'])}mers.rnacofoldin"
        )
        build_RNAcofold_in(cofold_in_repeated, oligo_obj.filtered_kmers, oligo_obj.repeated_sites)
        cofold_out_repeated = run_RNAcofold(cofold_in_repeated, " -P "+config["CofoldParamFile"])
        
    except Exception as exc:
        logging.error("Error getting binding affinity for repeated target sites: %s", exc)
        logging.info("Exiting.")
        sys.exit(1)
    
    
    
    try:
        oligo_obj.extract_non_prone_multiplicity(int(config["MissmatchCoreRegion"]),
                                                 int(config["ConsecutiveMatchesCoreRegion"]))
    except Exception as e:
        logging.error(f"Error extracting non-prone multiplicity: {e}")
        logging.info("Exiting.")
        sys.exit(1)
    
    
    
    try:
        oligo_obj.store_kmer_results(cofold_out, cofold_out_repeated)
    except Exception as e:
        logging.error(f"Error writing kmer results to file: {e}")
        logging.info("Exiting.")
        sys.exit(1)
        
    logging.info("Pipeline completed successfully.")

if __name__ == '__main__':
    main()