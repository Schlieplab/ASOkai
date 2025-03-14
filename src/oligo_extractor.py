from typing import List, Set, Tuple, Dict, Optional, Any, Union, NamedTuple
from Bio.SeqUtils import gc_fraction
from pyensembl import Genome
from utils.sequence_analysis import (
    get_chromosomal_positions_per_transcript,
    build_transcript_to_genomic_map,
    get_chromosomal_positions_with_mapping,
    get_transcript_object,
    get_seq_by_transcript_position,
    get_exon_id,
    longest_at_run,
    longest_t_run
)
from utils.kmer_searcher import KmerSearcher
import logging
import polars as pl
import os

class OligoData(NamedTuple):
    sequence: str
    chromosomal_position: str
    gene_id: str
    transcripts: List[str]
    exons: List[str]
    
class OligoExtractor:
    """
    A class to extract and analyze oligonucleotide (k-mer) sequences from a specified gene, 
    using data from the Ensembl database and aligning them with Bowtie2.

    This class provides functionalities to:
    - Extract k-mer sequences from a specified gene.
    - Align k-mers using Bowtie2 and analyze alignment results to find viable kmers for ASO Design.
    - Compute result k-mers along with their intrinsic and extrinsic features.
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
        data_dir: str, 
        ) -> None:
        """
        Initialize an OligoExtractor object.

        Parameters:
            gene_id (str): The Ensembl gene ID for the target gene.
            e_release (int): The Ensembl release version to use for querying gene and transcript data.
            g_assembly (int): The genome assembly number (e.g., 38 corresponds to GRCh38 or GRCm38).
            k (int): The length of k-mers (oligonucleotides) to extract.
            gc_bounds (Tuple[float, float]): A tuple specifying the lower and upper bounds for GC content filtering.
            species (str): The species of interest. Must be either "mus_musculus" or "homo_sapiens".
            gtf_path (str): The file path or URL to the GTF file containing gene annotations.
            dna_path (str): The file path or URL to the DNA FASTA file for transcript sequences.
            pep_path (str): The file path or URL to the protein FASTA file containing peptide sequences.
            scaffold_path (Optional[str]): The file path or URL to the scaffold GTF file. This is optional.
            multiplicity_layout (List[int]): A list of integers specifying the layout for multiplicity calculation.
            bowtie_index (str): The Bowtie2 index base name for aligning k-mers.
            data_dir (str): The directory path where output files and temporary data are stored.
        """
        
        logging.info("Creating OligoExtractor object")
        
        self.gene_id: str = gene_id
        self.k: int = k
        self.g_assembly: int = g_assembly
        self.e_release: int = e_release
        self.gene_kmers: List[str] = []
        self.candidate_targets: Dict[str, OligoData] = {}
        self.multiplicity_layout: List[int] = multiplicity_layout
        self.gc_bounds: Tuple[float, float] = gc_bounds
        self.data_dir: str = data_dir
        self.bowtie_index: str = bowtie_index
        self.repeated_sites: Dict[str, Any] = {}
        self.non_prone_multiplicity: Dict[str, Union[int, float]] = {}

        if species == "mus_musculus":
            self.species: str = "mus_musculus"
            # mus_musculus doesn't have scaffold
        elif species == "homo_sapiens":
            self.species: str = "homo_sapiens"
        else:
            raise ValueError("Only mus_musculus or homo_sapiens species implemented.")
        
        self.genome: Genome = Genome(
            reference_name=f'GRC{self.species[0]}{self.g_assembly}',
            annotation_name="ensembl",
            annotation_version=self.e_release,
            gtf_path_or_url=gtf_path,
            transcript_fasta_paths_or_urls=dna_path,
            protein_fasta_paths_or_urls=pep_path,
            
        )
        
        self.genome.index(overwrite=False)


        if scaffold_path:
            self.genome_scaffolds: Optional[Genome] = Genome(
                reference_name=f'GRCh{g_assembly}',
                annotation_name='scaffolds',
                gtf_path_or_url=scaffold_path,
            )
            self.genome_scaffolds.index()
        else:
            self.genome_scaffolds = None
        

        self.gene = self.genome.gene_by_id(gene_id=gene_id)
        
        logging.info(f"Gene name: {self.gene.gene_name}")
        logging.info(f"Gene id: {self.gene_id}")
        
        logging.info("Building transcript gene references. This may take a while...")
        self.transcript_gene_lookup: Dict[str, str] = self.get_gene_transcript_mapping()
        logging.info("Transcript gene references built successfully.")

        logging.info("OligoExtractor object created successfully.")

    def _kmers(self, 
               s: str, 
               k: int
               ) -> Set[Tuple[str, int]]:
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
        # Collect all transcripts
        all_transcripts = self.genome.transcripts()
        if self.genome_scaffolds:
            all_transcripts.extend(self.genome_scaffolds.transcripts())
        
        # Use dictionary comprehension - much faster than building incrementally
        return {t.transcript_id: t.gene_id for t in all_transcripts}


    def extract_candidate_targets(self) -> str:
        """
        Extract candidate oligos (k-mers) from the gene and save them to a FASTA file.
        """
        logging.info(f"Extracting {self.k}-mers from gene")

        transcripts = self.gene.transcripts
        candidate_targets = {}  # Dictionary to store unique oligos
        
        for t in transcripts:
            # Extract k-mers from transcript sequence
            kmers_set = self._kmers(t.sequence, self.k)
            
            for kmer_seq, position in kmers_set:
                # Get chromosomal position
                chrom_pos = get_chromosomal_positions_per_transcript(
                    t.transcript_id, 
                    position, 
                    self.genome, 
                    self.k, 
                    self.genome_scaffolds
                )
                
                if chrom_pos is None:
                    continue  # Skip if no valid chromosomal position
                
                # Use the sequence and chromosomal position as a composite key
                key = (kmer_seq, chrom_pos)
                
                if key not in candidate_targets:
                    candidate_targets[key] = {
                        'transcripts': [],
                        'exons': []
                    }
                
                # Add transcript and exon information
                candidate_targets[key]['transcripts'].append(t.transcript_id)
                exon_id = get_exon_id(position, t)
                candidate_targets[key]['exons'].append(exon_id)
        
        # Create a list of OligoData objects
        oligo_data_list = []
        for (seq, chrom_pos), data in candidate_targets.items():
            oligo_data_list.append(
                OligoData(
                    sequence=seq,
                    chromosomal_position=chrom_pos,
                    gene_id=self.gene_id,
                    transcripts=data['transcripts'],
                    exons=data['exons']
                )
            )
        

        for i, oligo_data in enumerate(oligo_data_list, 1):
            index = f'S{str(i).zfill(6)}'
            self.candidate_targets[index] = oligo_data
        
        logging.info(f"{len(self.candidate_targets)} candidate {self.k}-mers found")
        
        # Extract sequences for later use
        self.gene_kmers = [oligo.sequence for oligo in self.candidate_targets.values()]
        
        # Write to FASTA file
        outfile = os.path.join(self.data_dir, 'oligos', f"{self.gene_id}_{self.k}mers.fa")
        with open(outfile, "w") as tmp_bowtie_in:
            for index, oligo in self.candidate_targets.items():
                tmp_bowtie_in.write(f">{index}\n{oligo.sequence}\n")
        
        return outfile



    def filter_viable_kmers(self, in_file: str) -> None: # TODO: Add option to not filter
        """
        Filter the aligned k-mers based on Bowtie2 alignment results.

        Parameters:
            in_file (str): Path to the input SAM file from Bowtie2 alignment.
        """
        
        columns = ["QNAME", "FLAG", "RNAME", "POS", "MAPQ", "CIGAR", "RNEXT", "PNEXT", "TLEN", "SEQ"]

        align_file = pl.read_csv(
            in_file, 
            separator='\t', 
            has_header=False, 
            columns=range(10),
            new_columns=columns, 
            truncate_ragged_lines=True
        )
        
        res = (align_file
               .group_by('SEQ')
               .agg([
                    pl.col('RNAME')
                      .str.split(".")  
                      .list.first()
                      .alias('transcript_id')
                      .replace(self.transcript_gene_lookup)
                      .alias('genes'),
                    pl.col('QNAME')
                      .first()
                      .alias('seq_id')
                ])
               .with_columns(
                    pl.col('genes')
                      .list.set_difference([self.gene_id])
               )
               .filter(pl.col('genes').list.len() == 0)
               .select([pl.exclude('genes')])
               .sort('seq_id')
            )
        
        filtered_oligos = res.select(["seq_id", "SEQ"]).to_numpy().tolist()
        logging.info(f"Viable {self.k}-mer candidates after Bowtie: {len(filtered_oligos)}")
        
        outfile = os.path.join(self.data_dir, 'oligos', f"{self.gene_id}_{self.k}mers_filtered.fa")

        with open(outfile, "w") as tmp_bowtie_in:
            for x in filtered_oligos:
                tmp_bowtie_in.write(f">{x[0]}\n{x[1]}\n")
        logging.info(f"Filtered kmers written to file: {outfile}")

        # Update candidate_targets to only include filtered candidates:
        filtered_keys = {x[0] for x in filtered_oligos}
        self.candidate_targets = {key: value 
                                 for key, value in self.candidate_targets.items() 
                                 if key in filtered_keys}

        return outfile
    
    # def extract_off_target_sites(self, infile: str) -> None:
    #     """
    #     Extract off-target
    #     """
        
        


        

    def extract_repeated_sites(self, infile: str) -> None:
        """
        Extract repeated sites for each k-mer from the Bowtie2 alignment results.
        Uses Polars native functions for efficient processing and minimizes transcript mapping creation.
        
        Parameters:
            infile (str): Path to the input SAM file from Bowtie2 alignment.
        """
        # Define column names for the SAM file
        cols = ["QNAME", "FLAG", "RNAME", 
            "POS", "MAPQ", "CIGAR", 
            "RNEXT", "PNEXT", "TLEN", 
            "SEQ", "QUAL", "ALIGN_SCORE",]
        
        # Read SAM file using Polars
        sam_df = pl.read_csv(
            infile, 
            separator="\t", 
            has_header=False,
            new_columns=cols,
            truncate_ragged_lines=True
        )
        
        
        # Initialize results dictionary
        self.repeated_sites: Dict[str, set] = {qname: set() for qname in sam_df['QNAME'].unique()}
        
        # Add adjusted position column
        sam_df = sam_df.with_columns(
            (pl.col('POS') - self.multiplicity_layout[0]).alias('adjusted_pos')
        )
        
        # Process each transcript only once
        for transcript in sam_df['RNAME'].unique():
            # Get transcript object and build mapping only once per transcript
            transcript_obj = get_transcript_object(transcript, self.genome, self.genome_scaffolds)
            
            if not transcript_obj:
                continue  # Skip if transcript not found
                
            try:
                # Build transcript-to-genomic mapping once per transcript
                transcript_to_genomic = build_transcript_to_genomic_map(transcript_obj)
            except Exception as e:
                logging.error(f"Error building transcript mapping for {transcript}: {e}")
                continue
                
            # Filter for current transcript
            transcript_df = sam_df.filter(pl.col('RNAME') == transcript)
            
            # Group by QNAME within this transcript
            qname_groups = transcript_df.group_by('QNAME')
            
            # Process each QNAME group using the same transcript mapping
            for qname_group in qname_groups:
                qname = qname_group[0]
                qname_df = qname_group[1]
                
                # Extract positions for batch processing
                positions = qname_df['adjusted_pos'].to_list()
                
                # Get chromosomal positions using the pre-built mapping
                chrom_positions = get_chromosomal_positions_with_mapping(
                    transcript_obj,
                    transcript_to_genomic,
                    positions,
                    self.k
                )
                
                # Get sequences
                seqs = []
                for pos in positions:
                    seq = get_seq_by_transcript_position(
                        transcript, 
                        pos, 
                        self.genome, 
                        self.k, 
                        self.genome_scaffolds
                    )
                    seqs.append(seq)
                
                # Create a DataFrame with positions and sequences
                position_seq_df = pl.DataFrame({
                    'positions': chrom_positions,
                    'seq': seqs
                })
                
                # Filter out None positions and positions to ignore
                position_to_ignore = self.candidate_targets[qname].chromosomal_position
                filtered_df = position_seq_df.filter(
                    (pl.col('positions').is_not_null()) & 
                    (pl.col('positions') != position_to_ignore)
                )
                
                # Remove duplicates
                if not filtered_df.is_empty():
                    unique_df = filtered_df.unique()
                    
                    # Add to results
                    self.repeated_sites[qname].update(
                        list(zip(unique_df['positions'].to_list(), unique_df['seq'].to_list()))
                    )
        



    

        
    def extract_non_prone_multiplicity(self, core_missmatch_count: int, core_consecutive_matches: int) -> None:
        """
        Extract non-prone multiplicity for each k-mer using the KmerSearcher class.
        """
        searcher = KmerSearcher(self.gene_kmers, 
                                core_missmatch_count, 
                                core_consecutive_matches, 
                                f"{self.data_dir}/oligos/{self.gene_id}_{self.k}mer_non_prone_multiplicities.fa")
        
        self.non_prone_multiplicity = searcher.search(self.candidate_targets) # TODO: input changed to candidate_targets
    

    def store_kmer_results(self, cofold_out: str, cofold_out_repeated: str) -> None:
        """
        Generate a CSV file with detailed results for each k-mer, including various properties and metrics.   
        Parameters:
            cofold_out (str): The path to the RNAcofold output file in CSV format.
            cofold_out_repeated (str): The path to the RNAcofold output file for repeated candidates in CSV format.
        """
        logging.info("Completing final results")

        # Read cofold output files with Polars
        cofold_df = pl.read_csv(cofold_out)
        cofold_rep_df = pl.read_csv(cofold_out_repeated)

        # Convert seq_id to string type to ensure proper filtering later
        cofold_df = cofold_df.with_columns(pl.col("seq_id").cast(pl.Utf8))
        cofold_rep_df = cofold_rep_df.with_columns(pl.col("seq_id").cast(pl.Utf8))


        kmer_indices = [x for x in self.candidate_targets] # TODO: input changed to candidate_targets
        res_temp = []

        # Read configuration
        from configparser import ConfigParser
        config = ConfigParser()
        config.read('config.ini')
        max_ddG = float(config['DEFAULT']['MaxddG'])

        for idx in kmer_indices:
            # Get candidate from candidate_targets_df
            can = self.candidate_targets_df.filter(pl.col("seq_num") == idx).row(0, named=True) # TODO: input changed to candidate_targets
            
            # Get cofold data for this index
            idx_cofold = cofold_df.filter(pl.col("seq_id") == idx)
            if len(idx_cofold) == 0:
                logging.warning(f"No cofold data found for {idx}")
                continue
                
            dG_binding = idx_cofold.select("dG_binding").item()
            
            # Extract repeated candidates with higher ddG than maxddG
            repeated_cans = cofold_rep_df.filter(pl.col("seq_id").str.starts_with(idx))
            
            # Filter repeated candidates based on ddG threshold
            repeated_cans = repeated_cans.filter(
                (pl.col("dG_binding") - dG_binding) > max_ddG
            )
            
            # Create Ensembl link
            chromosomal_position = can['chromosomal_position']
            position_without_strand = chromosomal_position.rstrip(':+-') if chromosomal_position else ""
            ensembl_link = f"https://www.ensembl.org/{self.species}/Location/View?r={position_without_strand}"
            
            # Calculate reverse complement
            from Bio.Seq import Seq
            oligo_reverse_comp = str(Seq(can['seq']).reverse_complement())
            
            # Calculate transcript prevalence ratio
            transcript_count = len(can['transcripts']) if isinstance(can['transcripts'], list) else 0
            total_transcripts = len(self.gene.transcripts)
            transcript_prevalence_ratio = round(transcript_count / total_transcripts, 3) if total_transcripts > 0 else 0
            
            res_temp.append({
                'seq_num': idx,
                'target': can['seq'],
                'absolute_loc': can['chromosomal_position'],
                'oligo_reverse_comp': oligo_reverse_comp,
                'oligo_gc_content': gc_fraction(can['seq']),
                'oligo_longest_at_run': longest_at_run(can['seq']),
                'oligo_longest_t_run': longest_t_run(can['seq']),
                'repeated_target_site_multiplicity': len(repeated_cans),
                'non_prone_multiplicity': self.non_prone_multiplicity.get(idx, 0),
                'dG_binding': dG_binding,
                'transcript_prevalence_ratio': transcript_prevalence_ratio,
                'ordered_transcripts': can['transcripts'],
                'ordered_exons': can['exons'],
                'ensembl_link': ensembl_link,
            })
            
        # Create results DataFrame
        kmer_results = pl.DataFrame(res_temp)

        # Write results to CSV
        output_path = f'{self.data_dir}/results/{self.gene_id}_{self.k}mer_results.csv'
        kmer_results.write_csv(output_path)

        logging.info(f"Results saved to {output_path}")
