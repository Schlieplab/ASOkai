import subprocess
import shlex
import os
from Bio.SeqUtils import gc_fraction
from pyensembl import EnsemblRelease, Genome
from utils.sequence_analysis import get_chromosomal_positions_per_transcript, get_seq_by_transcript_position
from utils.sequence_analysis import get_exon_id, get_gc_content, longest_at_run, longest_t_run, get_rna_cofold_energy
from utils.file_operations import build_cofold_in
from utils.kmer_searcher import KmerSearcher
import logging
import time
import configparser 
import pandas as pd
from Bio.Seq import Seq
import polars as pl


# Create a configparser object
config = configparser.ConfigParser()

# Read the configuration file
config.read('config.ini')



class OligoExtractor:
    """
    A class to extract and analyze oligonucleotide (k-mer) sequences from a specified gene, 
    using data from the Ensembl database and aligning them with Bowtie2.

    This class provides functionalities to:
    - Extract k-mer sequences from a specified gene.
    - Align k-mers using Bowtie2 and analyze alignment results to find viable kmers for ASO Design.
    - Compute result k-mers along with their intrinsic and extrinsic features.

    Attributes:
        gene_id (str): The Ensembl gene ID for the target gene.
        e_release (int): The Ensembl release version to use.
        g_assembly (str): The genome assembly version (e.g., '38' for GRCh38).
        species (str): The species of interest, either "mouse" or "human".
        k (int): The length of k-mers to extract.
        bowtie_index (str): The path to the Bowtie2 index file.
        gc_bounds (tuple, optional): A tuple specifying the lower and upper GC content bounds for filtering k-mers.
        scaffold_path (str, optional): Path to a GTF file for scaffold annotations.
        gene_kmers (list): A list to store all k-mers extracted from the gene.
        filtered_kmers (list): A list to store k-mers that pass all filters.
        multiplicity_layout (list): A list of integers specifying the layout for multiplicity calculation.
        prone_multiplicity (dict): A dictionary to store prone multiplicity for each k-mer.
        non_prone_multiplicity (dict): A dictionary to store non-prone multiplicity for each k-mer.
        ensembl_obj (Genome): An instance of EnsemblRelease for querying gene and transcript data.
        ensembl_obj_scaffolds (Genome, optional): An optional Genome object for scaffold annotations.
        gene (Gene): The Gene object representing the target gene.
        transcript_lookup (dict): A dictionary mapping transcript IDs to gene IDs.
    """

    def __init__(self, gene_id, e_release, g_assembly, species, k, bowtie_index, gc_bounds= None, scaffold_path=None):
        self.gene_id = gene_id
        self.k = k
        self.g_assembly =  g_assembly
        self.gene_kmers = []
        self.filtered_kmers = []
        self.multiplicity_layout = [int(x) for x in config["DEFAULT"]["MultiplicityLayout"].split(',')]
        self.gc_bounds=gc_bounds
        self.bowtie_index = bowtie_index
        self.bowtie_infile = f"{config['DEFAULT']['DataDir']}/bowtie2Home/{self.gene_id}_{self.k}mers.fa"
        self.prone_multiplicity = dict()
        self.non_prone_multiplicity = dict()

        if species == "mouse":
            self.species = "mus_musculus"
            # mouse doesn't have scaffold
        elif species == "human":
            self.species = "homo_sapiens"
        else:
            raise ValueError("Only mouse or human species implemented.")
        
        self.ensembl_obj = EnsemblRelease(release=e_release, species=self.species)
        self.ensembl_obj.download()
        self.ensembl_obj.index()
        self.scaffold_path = scaffold_path


        if scaffold_path:
            self.ensembl_obj_scaffolds = Genome(
                reference_name=f'GRCh{g_assembly}',
                annotation_name='scaffolds',
                gtf_path_or_url=scaffold_path,
            )
            self.ensembl_obj_scaffolds.download()
            self.ensembl_obj_scaffolds.index()
        else:
            self.ensembl_obj_scaffolds = None
        

        self.gene = self.ensembl_obj.gene_by_id(gene_id=gene_id)
        
        logging.info(f"Gene name: {self.gene.gene_name}")
        logging.info(f"Build transcript gene references. This may take a while...")
        self.transcript_lookup = self.get_gene_transcript_mapping(save_to_file=f"transcript_gene_mapping_GRC{self.species[0]}{g_assembly}.csv")

    def _kmers(self, s, k):
        """
        Generate k-mers from the input sequence and filter them based on GC bounds if specified.

        Parameters:
            s (str): The input DNA sequence from which k-mers are generated.
            k (int): The length of k-mers to generate.

        Returns:
            set: A set of tuples, where each tuple contains a k-mer and its starting position in the sequence.
        """
        kmers_list = [(s[i:i + k], i+1) for i in range(len(s) - k + 1)]
        
        if self.gc_bounds:
            kmers_list = [seq for seq in kmers_list if self.gc_bounds[0] <= gc_fraction(seq[0]) <= self.gc_bounds[1]]
        kmers_set = set(kmers_list)

        return kmers_set

    def get_gene_transcript_mapping(self, save_to_file=None):
        """
        Create a mapping of transcript IDs to gene information.

        Optionally, save the mapping to a CSV file, including details about each transcript's exons.

        Parameters:
            save_to_file (str, optional): If provided, the path to the file where the mapping will be saved.

        Returns:
            dict: A dictionary mapping transcript IDs to gene information.
        """
        # TODO: might be extended to exon mapping
        transcript_lookup = dict()
        transcripts = self.ensembl_obj.transcripts()
        if self.scaffold_path:
            transcripts.extend(self.ensembl_obj_scaffolds.transcripts())

        if save_to_file:
            file = open(f"{config['DEFAULT']['DataDir']}/{save_to_file}", "w")
        for t in transcripts:
            if t.transcript_id not in transcript_lookup.keys():
                transcript_lookup[t.transcript_id] = t.gene_id
                if save_to_file:
                    for e in t.exons:
                        file.write(
                            f"{t.transcript_id},{t.gene_id},{t.contig}:{t.start},{t.contig}:{t.end},{e.exon_id},{e.start},{e.end},{t.gene_name}\n")
        if save_to_file:
            file.close()
        return transcript_lookup

    def _runCommand(self, command):
        """
        Execute a shell command and return the exit code.

        Parameters:
            command (str): The shell command to execute.

        Returns:
            int: The exit code of the executed command.
        """
        return_code = subprocess.call(shlex.split(command))
        return return_code


    def extract_candidate_oligos_by_gene(self):
        """
        Extract and process candidate oligos (k-mers) from the specified gene and save results to files.

        This method identifies candidate oligos of length `k` from the gene transcripts, calculates their 
        chromosomal positions, associates them with relevant transcripts and exons, and saves the results 
        to a CSV file. It also creates a Bowtie input file for sequence alignment.
        """
        logging.info(f"Extract {self.k}mers from gene {self.gene_id}")

        transcripts = self.gene.transcripts
        candidate_oligos = set()
        for t in transcripts:
            # rev_comp_t = Seq(t.sequence).reverse_complement()
            # TODO: make GC content bounds a parameter
            kmers_set = self._kmers(t.sequence, self.k)
            
            kmers_set = {(tup[0], 
                          get_chromosomal_positions_per_transcript(t.transcript_id, tup[1], self.ensembl_obj, self.k, self.ensembl_obj_scaffolds), 
                          t.transcript_id,
                          get_exon_id(tup[1], t)) for tup in kmers_set}
            
            candidate_oligos.update(kmers_set)
            
        
        
        columns = ['seq', 'chromosomal_position', 'transcripts', 'exons']
        candidate_oligos = pd.DataFrame(columns=columns, data=candidate_oligos)
        
        candidate_oligos = candidate_oligos.groupby(['seq', 'chromosomal_position']).agg({
            'exons' : lambda x: list(x),
            'transcripts' : lambda x: list(x),
        }).reset_index()
        
        custom_index = [f'S{str(i).zfill(6)}' for i in range(1, len(candidate_oligos) + 1)]
        candidate_oligos.index = custom_index
        
        logging.info(f"{len(candidate_oligos)} candidate {self.k}mers found")

        candidate_oligos.to_csv(f'{config["DEFAULT"]["DataDir"]}/oligos/{self.gene_id}_{self.k}mer_candidates.csv')
        
        self.gene_kmers = candidate_oligos['seq'].to_numpy().tolist()
        
        os.makedirs(f'{config["DEFAULT"]["DataDir"]}/bowtie2Home', exist_ok=True)
        
        with open(self.bowtie_infile, "w") as tmp_bowtie_in:
            candidate_oligos.apply(lambda x: tmp_bowtie_in.write(">" + str(x.name) + "\n" + x['seq'] + "\n"), axis = 1)
            
            
    def run_bowtie(self, local_gene_only = False):
        """
        Execute Bowtie2 alignment for the k-mers.

        Parameters:
            local_gene_only (bool): If True, aligns only to the local gene region.

        Returns:
            str: The path to the output SAM file.
        """
                
        logging.info("Running Bowtie2")
        
        start = time.time()
        
        if local_gene_only:    
            outFile = os.path.splitext(self.bowtie_infile)[0] + '_gene_only_middle' + ".sam"
            trim = ' --trim3 ' + str(int(self.multiplicity_layout[2])) + ' --trim5 ' + str(int(self.multiplicity_layout[0]))
            command = (f'bowtie2 -x {config["DEFAULT"]["DataDir"]}/bowtie2Home/{self.bowtie_index}_{self.gene_id}_only '
                    f'-U {self.bowtie_infile} -S {outFile} {config["DEFAULT"]["BowtieArgs"]}' + trim)
            
        else:
            outFile = os.path.splitext(self.bowtie_infile)[0] + ".sam"
            command = f'bowtie2 -x {config["DEFAULT"]["DataDir"]}/bowtie2Home/{self.bowtie_index} -U {self.bowtie_infile} -S {outFile} {config["DEFAULT"]["BowtieArgs"]}'
            
        logging.info("Command: {}".format(command))
        return_code = self._runCommand(command)
        logging.info("Return Code: {}".format(return_code))
        
        end = time.time() - start

        logging.info(f"Bowtie Processing time: {end}")
        
        return outFile


    def extract_viable_kmers(self, in_file):
        """
        Filter the aligned k-mers based on Bowtie2 alignment results.

        Parameters:
            in_file (str): Path to the input SAM file from Bowtie2 alignment.
        """
        columns = ["QNAME", "FLAG", "RNAME", "POS", "MAPQ", "CIGAR", "RNEXT", "PNEXT", "TLEN", "SEQ", "QUAL", "ALIGN SCORE", "XS", "XN", "XM", "XO", "XG", "EDIT DIST REF", "MISMATCH POS", "YT"]

        align_file = pl.read_csv(in_file ,separator='\t', has_header=False, new_columns=columns)
        
        res = (align_file
               .group_by('SEQ')
               .agg(
                    pl.col('RNAME')
                    .str.split(".")  
                    .list.first().alias('transcript_id')
                    .replace(self.transcript_lookup)
                    .alias('genes'),
                pl.col('QNAME').first().alias('seq_id'),  
                ).with_columns(
                    pl.col('genes').list.set_difference([self.gene_id])
                ).filter(pl.col('genes').list.len() == 0)
                .select([pl.exclude('genes')])  
            )
        
        self.filtered_kmers = res.select(["seq_id", "SEQ"]).to_numpy().tolist()
                            
        logging.info(f"Viable  {self.k}mers candidates after Bowtie: {len(self.filtered_kmers)}")

    def extract_prone_multiplicity(self):
        """
        Extract prone multiplicity for each k-mer by running Bowtie2 on the local gene region.
        """
        def calculate_occurrences(group):
            # Extract positions and sequences for each row
            result = group.apply(lambda row: {
                                        'positions': get_chromosomal_positions_per_transcript(row['RNAME'], 
                                                                                            row['POS'], 
                                                                                            self.ensembl_obj, 
                                                                                            self.multiplicity_layout[1], 
                                                                                            self.ensembl_obj_scaffolds),
                                        'seq': get_seq_by_transcript_position(row['RNAME'], 
                                                                            row['POS']-self.multiplicity_layout[0]-1, 
                                                                            self.ensembl_obj, 
                                                                            self.k, 
                                                                            self.ensembl_obj_scaffolds)
                                        }, 
                                axis=1)

            # Extract unique positions
            result = pd.DataFrame(result.tolist())
            result = result.dropna()
            result = result.drop_duplicates()

            return list(result.itertuples(index=False, name=None))
        
        outFile = self.run_bowtie(local_gene_only=True) 
    
        columns = ["QNAME", "FLAG", "RNAME", "POS", "MAPQ", "CIGAR", "RNEXT", "PNEXT", "TLEN", "SEQ", "QUAL", "ALIGN SCORE", "XS", "XN", "XM", "XO", "XG", "EDIT DIST REF", "MISMATCH POS", "YT"]

        sam_out = pd.read_csv(outFile, sep="\t", header=None, names = columns)
        sam_out_agg = sam_out.groupby('QNAME').apply(calculate_occurrences)
        # Convert to dictionary
        self.prone_multiplicity = sam_out_agg.to_dict()
    
    
    def get_secondary_target_site_candidates(self, cofold_in):
        """
        Extract prone multiplicity for each k-mer and run RNAcofold for each secondary candidate, return cofold out path.
        """
        self.extract_prone_multiplicity()
        
        build_cofold_in(cofold_in, self.filtered_kmers, self.prone_multiplicity)
        cofold_out_path = get_rna_cofold_energy(cofold_in)
        
        return cofold_out_path

        
    def extract_non_prone_multiplicity(self):
        """
        Extract non-prone multiplicity for each k-mer using the KmerSearcher class.
        """
        searcher = KmerSearcher(self.gene_kmers, 
                                int(config['DEFAULT']['MissmatchCoreRegion']), 
                                int(config['DEFAULT']['ConsecutiveMatchesCoreRegion']), 
                                f"{config['DEFAULT']['DataDir']}/oligos/{self.gene_id}_{self.k}mer_non_prone_multiplicities.fa")
        
        self.non_prone_multiplicity = searcher.search(self.filtered_kmers)
    

    
    def store_kmer_results(self, cofold_out, cofold_out_secondary): 
        """
        Generate a CSV file with detailed results for each k-mer, including various properties and metrics.

        Parameters:
            cofold_out (str): The path to the RNAcofold output file in CSV format.
            cofold_out_secondary (str): The path to the RNAcofold output file for secondary candidates in CSV format.

        """
        logging.info(f"Completing final results")

        cofold_out = pd.read_csv(cofold_out)
        cofold_out.set_index('seq_id', inplace=True)
        
        cofold_out_secondary = pd.read_csv(cofold_out_secondary)
        cofold_out_secondary.set_index('seq_id', inplace=True)
        

        oligo_candidates = pd.read_csv(f'{config["DEFAULT"]["DataDir"]}/oligos/{self.gene_id}_{self.k}mer_candidates.csv', index_col=0)

        os.makedirs(f"{config['DEFAULT']['DataDir']}/oligos", exist_ok=True)
        
        # result csv column names
        columns = ['seq_num',  
                   'oligo_reverse_comp', 
                   'oligo_gc_content',
                   'oligo_longest_at_run',
                   'oligo_longest_t_run',
                   'target', 
                   'absolute_loc', 
                   'ordered_transcripts', 
                   'ordered_exons',
                   'secondary_target_site_multiplicity', 
                   'non_prone_multiplicity', 
                   'dG_binding']
        
        kmer_indices = [x[0] for x in self.filtered_kmers]
        res_temp = []
        
        for idx in kmer_indices:
            can = oligo_candidates.loc[idx]
            secondary_cans = cofold_out_secondary[cofold_out_secondary.index.str.startswith(idx)].copy()
            drop_indices = secondary_cans[(secondary_cans.dG_binding - cofold_out.loc[idx, 'dG_binding']) > int(config['DEFAULT']['maxddG'])].index
            secondary_cans.drop(index=drop_indices, inplace=True)

            
            res_temp.append((idx,                                             # seq_num
                             can['seq'],                                      # oligo_reverse_comp
                             get_gc_content(can['seq']),                          # oligo_gc_content
                             longest_at_run(can['seq']),                      # oligo_longest_at_run
                             longest_t_run(can['seq']),                       # oligo_longest_t_run
                             str(Seq(can['seq']).reverse_complement()),       # target
                             can['chromosomal_position'],                     # absolute_loc
                             can['transcripts'],                              # ordered_transcripts
                             can['exons'],                                    # ordered_exons
                             len(secondary_cans),                             # secondary_target_site_multiplicity
                             self.non_prone_multiplicity.get(idx, 0),         # non_prone_multiplicity
                             cofold_out.loc[idx]['dG_binding'])               # dG_binding
                            )
            
        kmer_results = pd.DataFrame(res_temp, columns=columns)
        
        kmer_results.set_index('seq_num', inplace=True)
        kmer_results.to_csv(f'{config["DEFAULT"]["DataDir"]}/oligos/{self.gene_id}_{self.k}mer_results.csv')