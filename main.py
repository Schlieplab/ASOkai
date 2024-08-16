# -*- coding: utf-8 -*-
import csv
import argparse
import sys
from utils.file_operations import collect_scaffold, build_bowtie_index
from utils.sequence_analysis import getRNAcofoldEnergy
import logging
from src.oligo_extractor import OligoExtractor
from Bio.Seq import Seq
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
        logging.error(f"Missing configuration parameter: {e}")
        sys.exit(1)


    parser = argparse.ArgumentParser(
        description="Run the ASO thermodynamics pipeline to retrieve the ddG landscape for "
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
        default=111,
        help="Ensemble release, default=111"
    )

    args = parser.parse_args()
    logging.basicConfig(
        # force=True,
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
        logging.error(f"Error while setting species and genome assembly: {e}")
        sys.exit(1)
    logging.info(args)
    
    try:
        os.makedirs(f"{config['DEFAULT']['DataDir']}/oligos", exist_ok=True)
        oligo_obj = OligoExtractor(args.gene_id, args.ensembl_release, args.genome_assembly, args.species, args.k, bowtie_index, None, scaffold_path)
        oligo_obj.get_candidate_oligos_by_gene()
    except Exception as e:
        logging.error(f"Error during oligo extraction: {e}")
        sys.exit(1)
    
    try:
        build_bowtie_index(args.ensembl_release, args.genome_assembly, args.species, bowtie_index)
    except Exception as e:
        logging.error(f"Error building Bowtie2 index: {e}")
        sys.exit(1)
        
    try:
        oligo_obj.run_bowtie()
    except Exception as e:
        logging.error(f"Error running Bowtie2: {e}")
        sys.exit(1)
    

    try:
        os.makedirs(f"{config['DEFAULT']['DataDir']}/oligos", exist_ok=True)
        with open(f"{config['DEFAULT']['DataDir']}/oligos/{bowtie_index}_{args.gene_id}_filtered_{args.k}mers.rnacofoldin", "w") as filteredkmerfile:
            for x in oligo_obj.filtered_kmers:
                # First line: '>kmer' (where x[0] is the kmer identifier)
                filteredkmerfile.write('>' + x[0] + '\n')
                
                # Second line: 'kmer&reverse_complement'
                filteredkmerfile.write(x[1] + '&' + str(Seq(x[1]).reverse_complement()) + '\n')
            
        RNAcofoldFile = getRNAcofoldEnergy(f"{config['DEFAULT']['DataDir']}/oligos/{bowtie_index}_{args.gene_id}_filtered_{args.k}mers.rnacofoldin")
        
    except Exception as e:
        logging.error(f"Error getting binding affinity: {e}")
        sys.exit(1)
  
    try:
        oligo_obj.get_kmer_occurrences()
    except Exception as e:
        logging.error(f"Error getting kmer occurrences: {e}")
        sys.exit(1)    
      
    try:
        oligo_obj.store_kmer_results(RNAcofoldFile)
    except Exception as e:
        logging.error(f"Error writing kmer results to file: {e}")
        sys.exit(1)
        


    logging.info("Pipeline completed successfully.")




