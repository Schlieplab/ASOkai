# -*- coding: utf-8 -*-
import argparse
import sys
from utils.file_operations import collect_scaffold, build_bowtie_index, build_cofold_in
from utils.sequence_analysis import get_rna_cofold_energy
import logging
from src.oligo_extractor import OligoExtractor
import configparser
import os

def setup_logging():
    logging.basicConfig(
        force=True,
        level=logging.INFO,
        stream=sys.stdout,
        format='### INFO - %(asctime)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def read_config(args_set):
    config = configparser.ConfigParser()
    try:
        config.read('config.ini')
    except Exception as e:
        logging.error(f"Failed to read the configuration file: {e}")
        sys.exit(1)
    return config[args_set]

def set_environment_variables(config):
    try:
        os.environ['PYENSEMBL_CACHE_DIR'] = f'{config["PyEnsemblDataDir"]}'
        os.environ['BOWTIE2_INDEXES'] = f'{config["Bowtie2Dir"]}/bowtie2Home'
    except KeyError as e:
        logging.error(f"Missing configuration parameters: {e}")
        sys.exit(1)

def get_scaffold_and_index(config):
    try:
        if config["Species"] == "mouse":
            scaffold_path = None # Mouse doesn't have a scaffold
            bowtie_index = f'GRCm{int(config["GenomeAssembly"])}_{int(config["EnsembleRelease"])}'
        elif config["Species"] == "human":
            scaffold_path = collect_scaffold(int(config["GenomeAssembly"]), int(config["EnsembleRelease"]))
            bowtie_index = f'GRCh{int(config["GenomeAssembly"])}_{int(config["EnsembleRelease"])}'
        else:
            raise ValueError("Only mouse and human species implemented.")
    except Exception as e:
        logging.error(f"Error while collecting scaffold: {e}")
        sys.exit(1)
    return scaffold_path, bowtie_index

def create_directories(config):
    try:
        os.makedirs(f"{config['OligoDir']}/oligos", exist_ok=True)
        os.makedirs(f"{config['Bowtie2Dir']}/bowtie2Home", exist_ok=True)
    except Exception as e:
        logging.error(f"Error creating directories: {e}")
        sys.exit(1)

def main():
    setup_logging()
    logging.info("Pipeline starting up")

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

    config = read_config(args_set)
    set_environment_variables(config)
    scaffold_path, bowtie_index = get_scaffold_and_index(config)
    create_directories(config)

    try:
        oligo_obj = OligoExtractor(str(config["TargetGene"]), 
                                   int(config["EnsembleRelease"]), 
                                   int(config["GenomeAssembly"]), 
                                   str(config["Species"]), 
                                   int(config["OligoLen"]), 
                                   [int(x) for x in config["MultiplicityLayout"].split(',')],
                                   bowtie_index, 
                                   str(config['OligoDir']),
                                   None, 
                                   scaffold_path)
        
    except Exception as e:
        logging.error(f"Error creating OligoExtractor object: {e}")
        sys.exit(1)
    
    try:
        bowtie_infile = f"{config['Bowtie2Dir']}/bowtie2Home/" + \
                        f'{config["TargetGene"]}_{config["OligoLen"]}mers.fa'
                        
        oligo_obj.extract_candidate_oligos_by_gene(bowtie_infile)
        
    except Exception as e:
        logging.error(f"Error during oligo extraction: {e}")
        sys.exit(1)
    
    try: # TODO: subfolder for indices
        build_bowtie_index(int(config["EnsembleRelease"]), 
                           int(config["GenomeAssembly"]), 
                           config["Species"], 
                           bowtie_index, 
                           config["TargetGene"])
    
    except Exception as e:
        logging.error(f"Error building Bowtie2 transcriptome index: {e}")
    
    try:
        build_bowtie_index(int(config["EnsembleRelease"]), 
                           int(config["GenomeAssembly"]), 
                           config["Species"], 
                           bowtie_index, 
                           config["TargetGene"], 
                           gene_only=True)
        
    except Exception as e:
        logging.error(f"Error building Bowtie2 target gene index: {e}")
        sys.exit(1)
        
    try:
        bowtie_out = oligo_obj.run_bowtie(bowtie_infile, 
                                         config['Bowtie2Dir'], 
                                         config["BowtieArgs"])
        
        bowtie_out_gene_gnly = oligo_obj.run_bowtie(bowtie_infile, 
                                config['Bowtie2Dir'], 
                                config["BowtieArgs"], gene_only=True)
    except Exception as e:
        logging.error(f"Error running Bowtie2: {e}")
        sys.exit(1)
        
    try:
        oligo_obj.extract_viable_kmers(bowtie_out)
    except Exception as e:
        logging.error(f"Error extracting viable kmers: {e}")
        sys.exit(1)

        
    try:
        cofold_in = f"{config['OligoDir']}/oligos/{bowtie_index}_{config['TargetGene']}" + \
                    f"_filtered_{config['OligoLen']}mers.rnacofoldin"
                    
        build_cofold_in(cofold_in, oligo_obj.filtered_kmers)   
        cofold_out = get_rna_cofold_energy(cofold_in, " -P "+config["CofoldParamFile"])
        
    except Exception as e:
        logging.error(f"Error getting binding affinity: {e}")
        sys.exit(1)
        

    try:
        oligo_obj.extract_repeated_sites(bowtie_out_gene_gnly)
    except Exception as e:
        logging.error(f"Error extracting repeated sites: {e}")
        sys.exit(1)
        
    try:
        cofold_in_repeated = (
            f"{config['OligoDir']}/oligos/{bowtie_index}_{config['TargetGene']}_prone_"
            f"{int(config['OligoLen'])}mers.rnacofoldin"
        )
        build_cofold_in(cofold_in_repeated, oligo_obj.filtered_kmers, oligo_obj.repeated_sites)
        cofold_out_repeated = get_rna_cofold_energy(cofold_in_repeated, " -P "+config["CofoldParamFile"])
    except Exception as exc:
        logging.error("Error getting binding affinity for repeated target sites: %s", exc)
        sys.exit(1)
    
    try:
        oligo_obj.extract_non_prone_multiplicity(int(config["MissmatchCoreRegion"]),
                                                 int(config["ConsecutiveMatchesCoreRegion"]))
    except Exception as e:
        logging.error(f"Error extracting non-prone multiplicity: {e}")
        sys.exit(1)
    
    try:
        oligo_obj.store_kmer_results(cofold_out, cofold_out_repeated)
    except Exception as e:
        logging.error(f"Error writing kmer results to file: {e}")
        sys.exit(1)
        
    logging.info("Pipeline completed successfully.")

if __name__ == '__main__':
    main()




