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

    try:
        # Read the configuration file
        config.read('config.ini')
    except Exception as e:
        logging.error(f"Failed to read the configuration file: {e}")
        sys.exit(1)
    
    try:
        # Set Environment variables to use the data dir from config file
        os.environ['PYENSEMBL_CACHE_DIR'] = F'{config["DEFAULT"]["PyEnsemblDataDir"]}'
        os.environ['BOWTIE2_INDEXES '] = F'{config["DEFAULT"]["DataDir"]}/bowtie2Home'
    except KeyError as e:
        logging.error(f"Missing configuration parameters: {e}")
        sys.exit(1)


    parser = argparse.ArgumentParser(
        description="Run the ASO thermodynamics pipeline to retrieve the ddG landscape for " # TODO
                    "selective oligos by the Ensemble gene ID of interest"
    )

    parser.add_argument(dest='gene_id',
                        type=str,
                        help="Gene Name to be searched for candidate oligos")
    parser.add_argument(dest='k',
                        type=int,
                        help='Length of oligo'
                        )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Outputs progress information on the console."
    )
    parser.add_argument(
        "--species", "-s",
        type=str,
        default="human",
        help="mouse or human (default)"
    )
    parser.add_argument(
        "--genome-assembly", "-g",
        type=int,
        default=38,
        help="Genome Assembly, default=38"
    )
    parser.add_argument(
        "--ensembl-release", "-e",
        type=int,
        default=113,
        help="Ensemble release, default=113"
    )

    args = parser.parse_args()
    logging.basicConfig(
        force=True,
        level=logging.INFO,
        stream=sys.stdout,
        format='### INFO - %(asctime)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    logging.info("%s starting up" % sys.argv[0])

    try:
        if args.species == "mouse":
            scaffold_path = None
            bowtie_index = f"GRCm{args.genome_assembly}_{args.ensembl_release}"
        elif args.species == "human":
            scaffold_path = collect_scaffold(args.genome_assembly, args.ensembl_release)
            bowtie_index = f"GRCh{args.genome_assembly}"
        else:
            raise ValueError("Only mouse and human species implemented.")
    except Exception as e:
        logging.error(f"Error while collecting scaffold: {e}")
        sys.exit(1)
    
    try:
        os.makedirs(f"{config['DEFAULT']['DataDir']}/oligos", exist_ok=True)
        oligo_obj = OligoExtractor(args.gene_id, args.ensembl_release, args.genome_assembly, args.species, args.k, bowtie_index, None, scaffold_path)
        oligo_obj.extract_candidate_oligos_by_gene()
    except Exception as e:
        logging.error(f"Error during oligo extraction: {e}")
        sys.exit(1)
    
    try:
        build_bowtie_index(args.ensembl_release, args.genome_assembly, args.species, bowtie_index, args.gene_id)
        build_bowtie_index(args.ensembl_release, args.genome_assembly, args.species, bowtie_index, args.gene_id, gene_only=True)
    except Exception as e:
        logging.error(f"Error building Bowtie2 index: {e}")
        sys.exit(1)
        
    try:
        bowtieOut = oligo_obj.run_bowtie()
    except Exception as e:
        logging.error(f"Error running Bowtie2: {e}")
        sys.exit(1)
        
    try:
        oligo_obj.extract_viable_kmers(bowtieOut)
    except Exception as e:
        logging.error(f"Error getting viable kmers: {e}")
        sys.exit(1)

        
    try:
        cofold_in = f"{config['DEFAULT']['DataDir']}/oligos/{bowtie_index}_{args.gene_id}_filtered_{args.k}mers.rnacofoldin"
        build_cofold_in(cofold_in, oligo_obj.filtered_kmers)   
        cofold_out = get_rna_cofold_energy(cofold_in)
    except Exception as e:
        logging.error(f"Error getting binding affinity: {e}")
        sys.exit(1)
        

    try:
        oligo_obj.extract_prone_multiplicity()
    except Exception as e:
        logging.error(f"Error extracting prone multiplicity: {e}")
        sys.exit(1)
        
    try:
        cofold_in_secondary = f"{config['DEFAULT']['DataDir']}/oligos/{bowtie_index}_{args.gene_id}_prone_{args.k}mers.rnacofoldin"
        build_cofold_in(cofold_in_secondary, oligo_obj.filtered_kmers, oligo_obj.prone_multiplicity)   
        cofold_out_secondary = get_rna_cofold_energy(cofold_in_secondary)
    except Exception as e:
        logging.error(f"Error getting binding affinity for secondary target sites: {e}")
        sys.exit(1)  
        
    
    try:
        oligo_obj.extract_non_prone_multiplicity()
    except Exception as e:
        logging.error(f"Error extracting non-prone multiplicity: {e}")
        sys.exit(1)
    

      
    # try:
    oligo_obj.store_kmer_results(cofold_out, cofold_out_secondary)
    # except Exception as e:
    #     logging.error(f"Error writing kmer results to file: {e}")
    #     sys.exit(1)
        


    logging.info("Pipeline completed successfully.")




