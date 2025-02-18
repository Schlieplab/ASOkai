# -*- coding: utf-8 -*-
import argparse
import sys
from utils.file_operations import collect_scaffold, build_bowtie_index, build_cofold_in
from utils.sequence_analysis import get_rna_cofold_energy
import logging
from src.oligo_extractor import OligoExtractor
import configparser
import os



if __name__ == '__main__':

    # Create a configparser object
    config = configparser.ConfigParser()

    parser = argparse.ArgumentParser(
        description="Run the ASO thermodynamics pipeline to retrieve the ddG landscape for " # TODO
                    "selective oligos by the Ensemble gene ID of interest"
    )
    
    parser.add_argument(
        "--args", "-as",
        type=str,
        default="DEFAULT",
        help="Set of Arguments in config.ini to use (default)"
    )


    args_set = parser.parse_args().args
    
    try:
        # Read the configuration file
        config.read('config.ini')
    except Exception as e:
        logging.error(f"Failed to read the configuration file: {e}")
        sys.exit(1)
    
    try:
        # Set Environment variables to use the data dir from config file
        os.environ['PYENSEMBL_CACHE_DIR'] = F'{config[args_set]["PyEnsemblDataDir"]}'
        os.environ['BOWTIE2_INDEXES '] = F'{config[args_set]["Bowtie2Dir"]}/bowtie2Home'
    except KeyError as e:
        logging.error(f"Missing configuration parameters: {e}")
        sys.exit(1)



    logging.basicConfig(
        force=True,
        level=logging.INFO,
        stream=sys.stdout,
        format='### INFO - %(asctime)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    logging.info("%s starting up" % sys.argv[0])

    try:
        if config[args_set]["Species"] == "mouse":
            scaffold_path = None
            bowtie_index = f'GRCm{int(config[args_set]["GenomeAssembly"])}_{int(config[args_set]["EnsembleRelease"])}'
        elif config[args_set]["Species"] == "human":
            scaffold_path = collect_scaffold(int(config[args_set]["GenomeAssembly"]), int(config[args_set]["EnsembleRelease"]))
            bowtie_index = f'GRCh{int(config[args_set]["GenomeAssembly"])}'
        else:
            raise ValueError("Only mouse and human species implemented.")
    except Exception as e:
        logging.error(f"Error while collecting scaffold: {e}")
        sys.exit(1)
    
    try:
        os.makedirs(f"{config[args_set]['OligoDir']}/oligos", exist_ok=True)
        os.makedirs(f"{config[args_set]['Bowtie2Dir']}/bowtie2Home", exist_ok=True)

        oligo_obj = OligoExtractor(config[args_set]["TargetGene"], 
                                   int(config[args_set]["EnsembleRelease"]), 
                                   int(config[args_set]["GenomeAssembly"]), 
                                   config[args_set]["Species"], 
                                   int(config[args_set]["OligoLen"]), 
                                   [int(x) for x in config[args_set]["MultiplicityLayout"].split(',')],
                                   bowtie_index, 
                                   config[args_set]['OligoDir'],
                                   None, 
                                   scaffold_path)
        
        bowtie_infile = f"{config[args_set]['Bowtie2Dir']}/bowtie2Home/" + \
                        f'{config[args_set]["TargetGene"]}_{config[args_set]["OligoLen"]}mers.fa'
                        
        oligo_obj.extract_candidate_oligos_by_gene(bowtie_infile)
        
    except Exception as e:
        logging.error(f"Error during oligo extraction: {e}")
        sys.exit(1)
    
    try: # TODO: subfolder for indices
        build_bowtie_index(int(config[args_set]["EnsembleRelease"]), 
                           int(config[args_set]["GenomeAssembly"]), 
                           config[args_set]["Species"], 
                           bowtie_index, 
                           config[args_set]["TargetGene"])
        
        build_bowtie_index(int(config[args_set]["EnsembleRelease"]), 
                           int(config[args_set]["GenomeAssembly"]), 
                           config[args_set]["Species"], 
                           bowtie_index, 
                           config[args_set]["TargetGene"], 
                           gene_only=True)
        
    except Exception as e:
        logging.error(f"Error building Bowtie2 index: {e}")
        sys.exit(1)
        
    try:
        bowtie_out = oligo_obj.run_bowtie(bowtie_infile, 
                                         config[args_set]['Bowtie2Dir'], 
                                         config["DEFAULT"]["BowtieArgs"])
        

        bowtie_out_gene_gnly = oligo_obj.run_bowtie(bowtie_infile, 
                                config[args_set]['Bowtie2Dir'], 
                                config["DEFAULT"]["BowtieArgs"], gene_only=True)
    except Exception as e:
        logging.error(f"Error running Bowtie2: {e}")
        sys.exit(1)
        
    try:
        oligo_obj.extract_viable_kmers(bowtie_out)
    except Exception as e:
        logging.error(f"Error getting viable kmers: {e}")
        sys.exit(1)

        
    try:
        cofold_in = f"{config[args_set]['OligoDir']}/oligos/{bowtie_index}_{config[args_set]['TargetGene']}" + \
                    f"_filtered_{config[args_set]['OligoLen']}mers.rnacofoldin"
                    
        build_cofold_in(cofold_in, oligo_obj.filtered_kmers)   
        cofold_out = get_rna_cofold_energy(cofold_in)
        
    except Exception as e:
        logging.error(f"Error getting binding affinity: {e}")
        sys.exit(1)
        

    try:
        oligo_obj.extract_repeated_sites(bowtie_out_gene_gnly)
    except Exception as e:
        logging.error(f"Error extracting prone multiplicity: {e}")
        sys.exit(1)
        
    # try:
    #     cofold_in_repeated = f"{config[args_set]['OligoDir']}/oligos/{bowtie_index}" + \
    #                          f'_{config[args_set]["TargetGene"]}_prone_{int(config[args_set]["OligoLen"])}mers.rnacofoldin'
                             
                             
    #     build_cofold_in(cofold_in_repeated, oligo_obj.filtered_kmers, oligo_obj.prone_multiplicity)   
    #     cofold_out_repeated = get_rna_cofold_energy(cofold_in_repeated)
        
    # except Exception as e:
    #     logging.error(f"Error getting binding affinity for repeated target sites: {e}")
    #     sys.exit(1)  
        
    
    try:
        oligo_obj.extract_non_prone_multiplicity(int(config[args_set]["MissmatchCoreRegion"]),
                                                 int(config[args_set]["ConsecutiveMatchesCoreRegion"]))
    except Exception as e:
        logging.error(f"Error extracting non-prone multiplicity: {e}")
        sys.exit(1)
    

      
    try:
        oligo_obj.store_kmer_results(cofold_out, cofold_out_repeated)
    except Exception as e:
        logging.error(f"Error writing kmer results to file: {e}")
        sys.exit(1)
        


    logging.info("Pipeline completed successfully.")




