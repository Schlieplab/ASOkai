from typing import List, Set, Tuple, Dict, Optional, Any, Union
from Bio.SeqUtils import gc_fraction
from pyensembl import Genome
from utils.sequence_analysis import (
    get_chromosomal_positions_per_transcript,
    get_seq_by_transcript_position,
    get_exon_id,
    longest_at_run,
    longest_t_run
)
from utils.kmer_searcher import KmerSearcher
import logging
import pandas as pd
from Bio.Seq import Seq
import polars as pl
import ast


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
        gc_bounds (tuple): A tuple specifying the lower and upper GC content bounds for filtering k-mers.
        scaffold_path (str, optional): Path to a GTF file for scaffold annotations.
        gene_kmers (list): A list to store all k-mers extracted from the gene.
        filtered_kmers (list): A list to store k-mers that pass all filters.
        multiplicity_layout (list): A list of integers specifying the layout for multiplicity calculation.
        repeated_sites (dict): A dictionary to store repeated sites for each k-mer.
        non_prone_multiplicity (dict): A dictionary to store non-prone multiplicity for each k-mer.
        genome (Genome): An instance of EnsemblRelease genome for querying gene and transcript data.
        genome_scaffolds (Genome, optional): An optional Genome object for scaffold annotations.
        gene (Gene): The Gene object representing the target gene.
        transcript_gene_lookup (dict): A dictionary mapping transcript IDs to gene IDs.
    """

    def __init__(self, 
        gene_id: str, 
        e_release: int, 
        g_assembly: int, 
        k: int, 
        gc_bounds: Tuple[float, float],
        species: str, 
        gtf_path: str, 
        dna_path: str, 
        pep_path: str, 
        scaffold_path: Optional[str], 
        multiplicity_layout: List[int], 
        bowtie_index: str, 
        oligo_dir: str, 
    ) -> None:
        
        logging.info("Creating OligoExtractor object")
        
        self.gene_id: str = gene_id
        self.k: int = k
        self.g_assembly: int = g_assembly
        self.e_release: int = e_release
        self.gene_kmers: List[str] = []
        self.filtered_kmers: List[Tuple[str, str]] = []
        self.multiplicity_layout: List[int] = multiplicity_layout
        self.gc_bounds: Tuple[float, float] = gc_bounds
        self.oligo_dir: str = oligo_dir
        self.bowtie_index: str = bowtie_index
        self.repeated_sites: Dict[str, Any] = {}
        self.non_prone_multiplicity: Dict[str, Union[int, float]] = {}

        if species == "mouse":
            self.species: str = "mus_musculus"
            # mouse doesn't have scaffold
        elif species == "human":
            self.species: str = "homo_sapiens"
        else:
            raise ValueError("Only mouse or human species implemented.")
        
        self.genome: Genome = Genome(
            reference_name=f'GRC{self.species[0]}{self.g_assembly}',
            annotation_name="ensembl",
            annotation_version=self.e_release,
            gtf_path_or_url=gtf_path,
            transcript_fasta_paths_or_urls=dna_path,
            protein_fasta_paths_or_urls=pep_path,
            
        )
        
        self.genome.download(overwrite=False)
        self.genome.index()


        if scaffold_path:
            self.genome_scaffolds: Optional[Genome] = Genome(
                reference_name=f'GRCh{g_assembly}',
                annotation_name='scaffolds',
                gtf_path_or_url=scaffold_path,
            )
            self.genome_scaffolds.download()
            self.genome_scaffolds.index()
        else:
            self.genome_scaffolds = None
        

        self.gene = self.genome.gene_by_id(gene_id=gene_id)
        
        logging.info(f"Gene name: {self.gene.gene_name}")
        logging.info("Building transcript gene references. This may take a while...")
        self.transcript_gene_lookup: Dict[str, str] = self.get_gene_transcript_mapping()
        logging.info("OligoExtractor object created successfully")


    def _kmers(self, s: str, k: int) -> Set[Tuple[str, int]]:
        """
        Generate k-mers from the input sequence and filter them based on GC bounds if specified.

        Parameters:
            s (str): The input DNA sequence from which k-mers are generated.
            k (int): The length of k-mers to generate.

        Returns:
            set: A set of tuples, where each tuple contains a k-mer and its starting position in the sequence.
        """
        kmers_list = [(s[i:i + k], i + 1) for i in range(len(s) - k + 1)]
        kmers_list = [seq for seq in kmers_list if self.gc_bounds[0] <= gc_fraction(seq[0]) <= self.gc_bounds[1]]
        
        return set(kmers_list)

    def get_gene_transcript_mapping(self) -> Dict[str, str]:
        """
        Create a mapping of transcript IDs to gene information.

        Returns:
            dict: A dictionary mapping transcript IDs to gene information.
        """
        # TODO: might be extended to exon mapping
        transcript_lookup: Dict[str, str] = {}
        transcripts = self.genome.transcripts()
        if self.genome_scaffolds:
            transcripts.extend(self.genome_scaffolds.transcripts())

        for t in transcripts:
            if t.transcript_id not in transcript_lookup:
                transcript_lookup[t.transcript_id] = t.gene_id
                
        return transcript_lookup


    def extract_candidate_oligos_by_gene(self, outfile: str) -> None:
        """
        Extract and process candidate oligos (k-mers) from the specified gene and save results to files.

        This method identifies candidate oligos of length `k` from the gene transcripts, calculates their 
        chromosomal positions, associates them with relevant transcripts and exons, and saves the results 
        to a CSV file. It also creates a Bowtie input file for sequence alignment.
        """
        logging.info(f"Extracting {self.k}mers from gene {self.gene_id}")

        transcripts = self.gene.transcripts
        candidate_oligos = set()
        for t in transcripts:
            # TODO: make GC content bounds a parameter
            kmers_set = self._kmers(t.sequence, self.k)
            
            kmers_set = {
                (
                    tup[0],
                    get_chromosomal_positions_per_transcript(
                        t.transcript_id, tup[1], self.genome, self.k, self.genome_scaffolds
                    ),
                    t.transcript_id,
                    get_exon_id(tup[1], t)
                )
                for tup in kmers_set
            }
            
            candidate_oligos.update(kmers_set)
            
        
        
        columns = ['seq', 'chromosomal_position', 'transcripts', 'exons']
        candidate_df = pd.DataFrame(columns=columns, data=candidate_oligos)
        
        candidate_df = candidate_df.groupby(['seq', 'chromosomal_position']).agg({
            'exons' : lambda x: list(x),
            'transcripts' : lambda x: list(x),
        }).reset_index()
        
        custom_index = [f'S{str(i).zfill(6)}' for i in range(1, len(candidate_df) + 1)]
        candidate_df.index = custom_index
        
        logging.info(f"{len(candidate_df)} candidate {self.k}mers found")

        candidate_df.to_csv(f'{self.oligo_dir}/oligos/{self.gene_id}_{self.k}mer_candidates.csv')
        
        self.gene_kmers = candidate_df['seq'].to_numpy().tolist()
                
        with open(outfile, "w") as tmp_bowtie_in:
            candidate_df.apply(lambda x: tmp_bowtie_in.write(f">{x.name}\n{x['seq']}\n"), axis=1)
            


    def extract_viable_kmers(self, in_file: str, out_file: str) -> None: # TODO: Add option to not filter
        """
        Filter the aligned k-mers based on Bowtie2 alignment results.

        Parameters:
            in_file (str): Path to the input SAM file from Bowtie2 alignment.
            out_file (str): Path to the output file to save the filtered k-mers.
        """
        
        columns = ["QNAME", "FLAG", "RNAME", "POS", "MAPQ", "CIGAR", "RNEXT", "PNEXT", "TLEN", "SEQ"]

        align_file = pl.read_csv(in_file, 
                                 separator='\t', 
                                 has_header=False, 
                                 columns=range(10),
                                 new_columns=columns, 
                                 truncate_ragged_lines=True)
        
        res = (align_file
               .group_by('SEQ')
               .agg(
                    pl.col('RNAME')
                    .str.split(".")  
                    .list.first().alias('transcript_id')
                    .replace(self.transcript_gene_lookup)
                    .alias('genes'),
                pl.col('QNAME').first().alias('seq_id'),  
                ).with_columns(
                    pl.col('genes').list.set_difference([self.gene_id])
                ).filter(pl.col('genes').list.len() == 0)
                .select([pl.exclude('genes')])  
            )
        
        self.filtered_kmers = res.select(["seq_id", "SEQ"]).to_numpy().tolist()
                            
        logging.info(f"Viable {self.k}-mer candidates after Bowtie: {len(self.filtered_kmers)}")
        
        with open(out_file, "w") as tmp_bowtie_in:
            for x in self.filtered_kmers:
                tmp_bowtie_in.write(f">{x[0]}\n{x[1]}\n")
        logging.info(f"Filtered kmers written to file: {out_file}")

        return out_file

    def extract_repeated_sites(self, infile: str) -> None:
        """
        Extract repeated sites with up to some missmatches in the flanks for each k-mer by running Bowtie2 on the local gene region.
        
        Parameters:
            in_file (str): Path to the input SAM file from Bowtie2 alignment.
            
        """
        def calculate_occurrences(group: pd.DataFrame, position_to_ignore: str) -> List[Tuple]:
            # Extract positions and sequences for each row
            result = group.apply(lambda row: {
                                        'positions': (lambda pos: pos if pos != position_to_ignore else None)(
                                            get_chromosomal_positions_per_transcript(
                                                row['RNAME'], 
                                                row['POS'] - self.multiplicity_layout[0], 
                                                self.genome, 
                                                self.k, 
                                                self.genome_scaffolds
                                            )
                                        ),
                                        'seq': get_seq_by_transcript_position(
                                            row['RNAME'], 
                                            row['POS'] - self.multiplicity_layout[0], 
                                            self.genome, 
                                            self.k, 
                                            self.genome_scaffolds
                                        )
                                        }, 
                                axis=1)

            # Extract unique positions
            result = pd.DataFrame(result.tolist())
            result = result.dropna()
            result = result.drop_duplicates()


            return list(result.itertuples(index=False, name=None))
        
    
        cols = ["QNAME", "FLAG", "RNAME", 
                   "POS", "MAPQ", "CIGAR", 
                   "RNEXT", "PNEXT", "TLEN", 
                   "SEQ", "QUAL", "ALIGN SCORE", 
                   "XS", "XN", "XM", "XO", "XG", 
                   "EDIT DIST REF", "MISMATCH POS", "YT"]

        oligo_candidates = pd.read_csv(f'{self.oligo_dir}/oligos/{self.gene_id}_{self.k}mer_candidates.csv', index_col=0)
        
        sam_out = pd.read_csv(infile, sep="\t", header=None, names=cols)
        sam_out_agg = sam_out.groupby('QNAME').apply(lambda x : calculate_occurrences(x, oligo_candidates.loc[x['QNAME'],'chromosomal_position'].iloc[0]))
        # Convert to dictionary
        self.repeated_sites = sam_out_agg.to_dict()
    
    

        
    def extract_non_prone_multiplicity(self, core_missmatch_count: int, core_consecutive_matches: int) -> None:
        """
        Extract non-prone multiplicity for each k-mer using the KmerSearcher class.
        """
        searcher = KmerSearcher(self.gene_kmers, 
                                core_missmatch_count, 
                                core_consecutive_matches, 
                                f"{self.oligo_dir}/oligos/{self.gene_id}_{self.k}mer_non_prone_multiplicities.fa")
        
        self.non_prone_multiplicity = searcher.search(self.filtered_kmers)
    

    
    def store_kmer_results(self, cofold_out: str, cofold_out_repeated: str) -> None: 
        """
        Generate a CSV file with detailed results for each k-mer, including various properties and metrics.

        Parameters:
            cofold_out (str): The path to the RNAcofold output file in CSV format.
            cofold_out_repeated (str): The path to the RNAcofold output file for repeated candidates in CSV format.

        """
        logging.info("Completing final results")

        cofold_df = pd.read_csv(cofold_out)
        cofold_df.set_index('seq_id', inplace=True)
        
        
        cofold_rep_df = pd.read_csv(cofold_out_repeated)
        cofold_rep_df.set_index('seq_id', inplace=True)
        

        oligo_candidates = pd.read_csv(f'{self.oligo_dir}/oligos/{self.gene_id}_{self.k}mer_candidates.csv', index_col=0, 
                                       converters={'exons':ast.literal_eval,'transcripts':ast.literal_eval})

        
        # result csv column names
        columns = ['seq_num',  
                   'target', 
                   'absolute_loc', 
                   'oligo_reverse_comp', 
                   'oligo_gc_content',
                   'oligo_longest_at_run',
                   'oligo_longest_t_run',
                   'repeated_target_site_multiplicity', 
                   'non_prone_multiplicity', 
                   'dG_binding',
                   'transcript_prevalence_ratio',
                   'ordered_transcripts', 
                   'ordered_exons',
                   'ensembl_link'
                   ]
        
        kmer_indices = [x[0] for x in self.filtered_kmers]
        res_temp = []
        
        # Assuming 'config' is available in the context where this method is called.
        # Consider passing max_ddG as a parameter instead.
        from configparser import ConfigParser
        config = ConfigParser()
        config.read('config.ini')

        for idx in kmer_indices:
            
            can = oligo_candidates.loc[idx]
            
            # extract repeated candidates with higher ddG than maxddG
            repeated_cans = cofold_rep_df[cofold_rep_df.index.str.startswith(idx)].copy()
            drop_indices = repeated_cans[
                (repeated_cans.dG_binding - cofold_df.loc[idx, 'dG_binding']) <= float(config['DEFAULT']['MaxddG'])
            ].index.tolist()
            repeated_cans.drop(index=drop_indices, inplace=True)

            ensembl_link = f"https://www.ensembl.org/{self.species}/Location/View?r={can['chromosomal_position'].rstrip(':+-')}"
            # TODO: add TSL
            res_temp.append((idx,                                               # seq_num
                             can['seq'],                                        # target
                             can['chromosomal_position'],                       # absolute_loc
                             str(Seq(can['seq']).reverse_complement()),         # oligo_reverse_comp
                             gc_fraction(can['seq']),                           # oligo_gc_content
                             longest_at_run(can['seq']),                        # oligo_longest_at_run
                             longest_t_run(can['seq']),                         # oligo_longest_t_run
                             len(repeated_cans),                                # repeated_target_site_multiplicity
                             self.non_prone_multiplicity.get(idx, 0),           # non_prone_multiplicity
                             cofold_df.loc[idx]['dG_binding'],                  # dG_binding
                             round(len(can['transcripts']) /                    # transcript_prevalence_ratio
                                   len(self.gene.transcripts), 3),  
                             can['transcripts'],                                # ordered_transcripts
                             can['exons'],                                      # ordered_exons
                             ensembl_link,                                      # ensembl_link
                             )                                   
                            )
            
        kmer_results = pd.DataFrame(res_temp, columns=columns)
        
        kmer_results.set_index('seq_num', inplace=True)
        kmer_results.to_csv(f'{self.oligo_dir}/results/{self.gene_id}_{self.k}mer_results.csv')