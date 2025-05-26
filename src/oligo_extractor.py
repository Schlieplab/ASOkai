from typing import List, Set, Tuple, Dict, Optional, Union
from Bio.SeqUtils import gc_fraction
from genome_utils import TargetSite, Site
from Bio.Seq import Seq
from src.utils.sequence_analysis import (
    longest_at_run,
    longest_t_run,
    calculate_homodimer_binding_energy,
    get_steady_state_solution_Pedersen,
    get_target_k_diss,
)
import logging
import polars as pl
import os
from typing import List, Optional
import RNA
import multiprocessing as mp
from genome_utils import Genome

class OligoExtractor:
    """
    A class to extract and analyze oligonucleotide (k-mer) sequences from a specified gene, 
    using data from the Ensembl database and aligning them with Bowtie2.

    """
    
    def __init__(self, 
        gene_id: str, 
        e_release: int, 
        genome_assembly: int, 
        k: int, 
        gc_bounds: Tuple[float, float],
        species: str, 
        gtf_path: str, 
        cdna_path: str, 
        scaffold_gtf_path: Optional[str], 
        multiplicity_layout: List[int], 
        bowtie_index: str, 
        data_dir: str,
        genome_path: str,
        ) -> None:
        """
        Initialize an OligoExtractor object.

        Parameters:
            gene_id (str): The Ensembl gene ID for the target gene.
            e_release (int): The Ensembl release version to use for querying gene and transcript data.
            genome_assembly (int): The genome assembly number (e.g., 38 corresponds to GRCh38 or GRCm38).
            k (int): The length of k-mers (oligonucleotides) to extract.
            gc_bounds (Tuple[float, float]): A tuple specifying the lower and upper bounds for GC content filtering.
            species (str): The species of interest. Must be either "mus_musculus" or "homo_sapiens".
            gtf_path (str): The file path to the GTF file containing gene annotations.
            cdna_path (str): The file path to the cDNA FASTA file for transcript sequences.
            scaffold_gtf_path (Optional[str]): The file path to the scaffold GTF file. This is optional.
            multiplicity_layout (List[int]): A list of integers specifying the layout for multiplicity calculation.
            bowtie_index (str): The Bowtie2 index base name for aligning k-mers.
            data_dir (str): The directory path where output files and temporary data are stored.
            genome_path (str): The file path to the primary assembly FASTA file.
        """
        
        logging.info("Creating OligoExtractor object")
        
        self.gene_id: str = gene_id
        self.k: int = k
        self.genome_assembly: int = genome_assembly
        self.e_release: int = e_release
        self.candidate_targets: Dict[str, TargetSite] = {}
        self.multiplicity_layout: List[int] = multiplicity_layout
        self.gc_bounds: Tuple[float, float] = gc_bounds
        self.data_dir: str = data_dir
        self.bowtie_index: str = bowtie_index
        self.repeated_sites: Dict[str, List[Site]] = {}
        self.off_target_sites: Dict[str, List[Site]] = {}
        self.non_prone_multiplicity: Dict[str, Union[int, float]] = {}
        self.average_dG: float = 0.0
        
        if species not in ["mus_musculus", "homo_sapiens"]:
            raise ValueError("Only mus_musculus or homo_sapiens species implemented.")
        self.species = species
        
        self.genome: Genome = Genome(
            reference_name=f'GRC{self.species[0]}{self.genome_assembly}',
            annotation_version=self.e_release,
            gtf_path=gtf_path,
            transcript_fasta_paths=cdna_path,
            primary_assembly_path=genome_path
        )
        
        self.genome.index(overwrite=False)

        if scaffold_gtf_path:
            self.genome_scaffolds: Optional[Genome] = Genome(
                reference_name=f'GRCh{self.genome_assembly}',
                gtf_path=scaffold_gtf_path,
            )
            self.genome_scaffolds.index()
        else:
            self.genome_scaffolds = None

        # Extract pre-mRNA sequences for all genes
        # Derive pre-mRNA filename from primary assembly filename
        pre_mrna_fasta_path = genome_path.replace('.dna.primary_assembly.fa.gz', '.premrna.fa.gz')
        self.genome.extract_genome_premrna_sequences(output_path=pre_mrna_fasta_path, exclude_genes=self.gene_id)

        self.gene = self.genome.gene_by_id(gene_id=gene_id)

        gene_premrna_fasta_path = genome_path.replace('.dna.primary_assembly.fa.gz', f'.premrna.{gene_id}.fa.gz')
        premrna_seq = self.genome.extract_premrna_sequences_per_gene(gene_ids=[gene_id], output_path=gene_premrna_fasta_path)
        self.gene.pre_mrna_sequence = premrna_seq[gene_id]
        
        
        logging.info(f"Gene name: {self.gene.gene_name}")
        logging.info(f"Gene id: {self.gene_id}")
        
        logging.info("Building transcript gene references. This may take a while...")
        self.transcript_gene_lookup: Dict[str, str] = self._get_gene_transcript_mapping()
        logging.info("Transcript gene references built successfully.")

        logging.info("OligoExtractor object created successfully.")


    def _kmers(self, s: str, k: int) -> Set[Tuple[str, int]]:
        """
        Generate k-mers from the input sequence and filter them based on GC bounds if specified.

        Args:
            s: The input DNA sequence from which k-mers are generated
            k: The length of k-mers to generate

        Returns:
            A set of tuples, where each tuple contains a k-mer and its starting position in the sequence
        """
        kmers_list = [(s[i:i + k], i + 1) for i in range(len(s) - k + 1)]
        kmers_list = [seq for seq in kmers_list if self.gc_bounds[0] <= gc_fraction(seq[0]) <= self.gc_bounds[1]]
        
        return set(kmers_list)

    def _get_gene_transcript_mapping(self) -> Dict[str, str]:
        """
        Create a mapping of transcript IDs to gene information.

        Returns:
            A dictionary mapping transcript IDs to gene information
        """
        all_transcripts = self.genome.transcripts()
        if self.genome_scaffolds:
            all_transcripts.extend(self.genome_scaffolds.transcripts())
        
        return {t.transcript_id: t.gene_id for t in all_transcripts}

    def extract_candidate_targets(self, force_core_alignment: bool = False) -> str:
        """
        Extract candidate oligos (k-mers) from the gene including their dG values and save them to a FASTA file.

        Args:
            force_core_alignment: If True, force core alignment of the target and oligo

        Returns:
            Path to the output FASTA file containing candidate targets
        """
        logging.info(f"Extracting {self.k}-mers from gene")

        transcripts = self.gene.transcripts
        candidate_targets_dict: Dict[Tuple[str, str], TargetSite] = {}
        
        md = RNA.md()
        md.temperature = 37.0

        constraint_string: Optional[str] = None
        if force_core_alignment:
            target_constraint = '.' * self.multiplicity_layout[0] + '|' * self.multiplicity_layout[1] + '.' * self.multiplicity_layout[2]
            oligo_constraint = '.' * self.multiplicity_layout[2] + '|' * self.multiplicity_layout[1] + '.' * self.multiplicity_layout[0]
            constraint_string = target_constraint + '&' + oligo_constraint
            
        for t in transcripts:
            kmers_set = self._kmers(t.sequence, self.k)
            
            for kmer_seq, position in kmers_set:
                chrom_pos = t.get_chromosomal_position(position, self.k)
                
                if chrom_pos is None:
                    continue
                
                key = (kmer_seq, chrom_pos)
                exon = t.get_exon_by_position(position)
                
                if key not in candidate_targets_dict:
                    homodimer_dG = calculate_homodimer_binding_energy(kmer_seq)
                    
                    target_obj = Seq(kmer_seq)
                    oligo_seq = str(target_obj.reverse_complement())
                    
                    fc_target = RNA.fold_compound(kmer_seq, md)
                    (_, target_mfe) = fc_target.mfe()
                    
                    fc_oligo = RNA.fold_compound(oligo_seq, md)
                    (_, oligo_mfe) = fc_oligo.mfe()
                    
                    reference_duplex = kmer_seq + "&" + oligo_seq
                    fc_duplex = RNA.fold_compound(reference_duplex, md)
                    if force_core_alignment and constraint_string:
                        fc_duplex.hc_add_from_db(constraint_string)
                        
                    (_, duplex_mfe) = fc_duplex.mfe()
                    binding_dg = duplex_mfe - (target_mfe + oligo_mfe)
                    
                    candidate_targets_dict[key] = TargetSite(
                        sequence=kmer_seq,
                        chromosomal_position=chrom_pos,
                        gene_id=self.gene_id,
                        transcripts=[t],
                        exons=[exon],
                        oligo_dG=homodimer_dG,
                        dG=binding_dg,
                    )
                else:
                    candidate_targets_dict[key].transcripts.append(t)
                    candidate_targets_dict[key].exons.append(exon)
        
        oligo_data_list = list(candidate_targets_dict.values())
        
        for i, oligo_data in enumerate(oligo_data_list, 1):
            index = f'S{str(i).zfill(6)}'
            self.candidate_targets[index] = oligo_data
        
        logging.info(f"{len(self.candidate_targets)} {self.k}-mer candidate target sites found.")

        outfile = os.path.join(self.data_dir, 'oligos', f"{self.bowtie_index}_{self.gene_id}_{self.k}mers.fa")
        with open(outfile, "w") as tmp_bowtie_in:
            for index, oligo in self.candidate_targets.items():
                tmp_bowtie_in.write(f">{index}\n{oligo.sequence}\n")
        
        return outfile


    def filter_candidate_targets(self, in_file: str) -> None:
        """
        Filter candidate targets based on Bowtie2 alignment results.
        
        Args:
            in_file: Path to Bowtie2 alignment results file
            
        Returns:
            Path to filtered FASTA file
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
        with_genes = align_file.with_columns(
            pl.col('RNAME')
            .str.split(".")
            .list.first()
            .replace(self.transcript_gene_lookup)
            .alias('gene_id')
        )
        grouped = with_genes.group_by('SEQ').agg([
            pl.col('gene_id').alias('genes'),
            pl.col('QNAME').first().alias('seq_id')
        ])
        without_target = grouped.with_columns(
            pl.col('genes').list.set_difference([self.gene_id])
        )
        filtered = without_target.filter(pl.col('genes').list.len() == 0)
        res = filtered.select([pl.exclude('genes')]).sort('seq_id')
        
        filtered_oligos = res.select(["seq_id", "SEQ"]).to_numpy().tolist()
        logging.info(f"Viable {self.k}-mer candidate sites after Bowtie: {len(filtered_oligos)}")
        
        outfile = os.path.join(self.data_dir, 'oligos', f"{self.bowtie_index}_{self.gene_id}_{self.k}mers_filtered.fa")

        with open(outfile, "w") as tmp_bowtie_in:
            for x in filtered_oligos:
                tmp_bowtie_in.write(f">{x[0]}\n{x[1]}\n")
        logging.info(f"Filtered kmers written to file: {outfile}")

        filtered_keys = {x[0] for x in filtered_oligos}
        self.candidate_targets = {key: value 
                                 for key, value in self.candidate_targets.items() 
                                 if key in filtered_keys}
        return outfile

    def _get_average_dG(self) -> float:
        """
        Calculate the average dG of candidate sites.

        Returns:
            The average dG value across all candidate sites
        """
        self.average_dG = sum(site.dG for site in self.candidate_targets.values()) / len(self.candidate_targets)
        return self.average_dG
    
    @staticmethod
    def _process_pedersen_target(target_data_tuple: Tuple[str, TargetSite, Dict[str, float], float]) -> Tuple[str, float]:
        """
        Static worker function to process a single target for Pedersen analysis.

        Args:
            target_data_tuple: A tuple containing (target_id, target_site, params, average_dG)

        Returns:
            A tuple containing (target_id, steady_state_concentration)
        """
        target_id, target, params, average_dG = target_data_tuple
        try:
            # Calculate ddG from average
            ddG_from_avg = target.dG - average_dG
            
            # Get dissociation constant for this target
            k_OT_initial = params.get('k_OT')
            if k_OT_initial is None:
                logging.error(f"Missing 'k_OT' in params for target {target_id}")
                return target_id, 0.0
                
            k_diss = get_target_k_diss(k_OT_initial, ddG_from_avg, 37.0)
            
            # Create target-specific parameters
            par_target = params.copy()
            par_target['k_OT'] = k_diss
            
            # Calculate steady state solution
            steady_state = get_steady_state_solution_Pedersen(par_target)
            if steady_state is None:
                logging.warning(f"No steady state solution found for target {target_id}")
                return target_id, 0.0
            
            steady_state_concentration = steady_state['T'] + steady_state['OT'] + steady_state['OTE']
            logging.debug(f"Target {target_id}: ddG={ddG_from_avg:.2f}, k_diss={k_diss:.2e}, T_steady_state={steady_state_concentration:.2e}")
            return target_id, steady_state_concentration
        except KeyError as ke:
            logging.error(f"Missing key in params for target {target_id}: {str(ke)}")
            return target_id, 0.0
        except Exception as e:
            logging.error(f"Error processing target {target_id} in _process_pedersen_target: {str(e)}")
            return target_id, 0.0
        
    def pedersen_analysis(self, params: Dict[str, float], num_processes: Optional[int] = None) -> None:
        """
        Perform Pedersen model analysis on the target sites.
        
        Parameters:
            params (Dict[str, float]): Dictionary containing Pedersen model parameters
            num_processes (Optional[int]): Number of processes to use. If None, uses CPU count.
        """
        
        logging.info(f"Performing Pedersen analysis")
        
        
        if not self.candidate_targets:
            logging.warning("No candidate targets available for Pedersen analysis")
            return
        
        # Calculate average dG if not already calculated
        if self.average_dG == 0.0:
            self._get_average_dG()
        
        par_no_oligo = params.copy()
        par_no_oligo['O_ini'] = 1e-10  # Use a small positive value instead of 0.0
        
        steady_state_no_oligo = get_steady_state_solution_Pedersen(par_no_oligo)
        
        logging.info(f"Average dG of candidate sites: {self.average_dG:.2f}")
        logging.info(f"Steady state concentration of candidate sites without oligo: {steady_state_no_oligo['T']:.2e}")
        # Prepare data for multiprocessing
        # Each item in tasks will be a tuple: (target_id, target_object, params_dict, average_dG_float)
        tasks = [
            (target_id, target_site, params, self.average_dG) 
            for target_id, target_site in self.candidate_targets.items()
        ]

        # Set up multiprocessing
        if num_processes is None:
            num_processes = mp.cpu_count()
        
        logging.info(f"Starting Pedersen analysis using")
        
        # Process targets in parallel using the static method
        with mp.Pool(processes=num_processes) as pool:
            
            # Use imap_unordered for potentially faster consumption of results
            # The worker function is now OligoExtractor._process_pedersen_target
            results = pool.imap_unordered(OligoExtractor._process_pedersen_target, tasks)
            
            for target_id, steady_state_value in results:
                if target_id in self.candidate_targets: # Ensure target_id is valid
                    self.candidate_targets[target_id].pedersen_steady_state = steady_state_value/steady_state_no_oligo['T']
                else:
                    logging.warning(f"Received result for unknown target_id: {target_id}")

        
        logging.info("Completed Pedersen analysis")
  
    def extract_repeated_sites(self, max_ddg_threshold: float = 5.0, force_core_alignment: bool = False, output_file: Optional[str] = None) -> None:
        """
        Extract repeated sites by finding occurrences of the core region in the target gene's pre-mRNA sequence.
        Parameters:
            max_ddg_threshold (float): Maximum ddG threshold for keeping a site 
                                        Sites with ddG values above this threshold will be filtered out.
            force_core_alignment (bool): If True, force core alignment of the target and oligo.
            output_file (Optional[str]): If provided, path to save repeated sites in FASTA format.
        """
        logging.info("Extracting repeated sites")
        
        # Get the target gene's pre-mRNA sequence
        if not self.gene.pre_mrna_sequence:
            raise ValueError(f"No pre-mRNA sequence available for target gene {self.gene_id}")
            
        pre_mrna_seq = self.gene.pre_mrna_sequence
        
        md = RNA.md()
        md.temperature = 37.0
        
        constraint_string = None
        if force_core_alignment:
            target_constraint = '.' * self.multiplicity_layout[0] + '|' * self.multiplicity_layout[1] + '.' * self.multiplicity_layout[2]
            oligo_constraint = '.' * self.multiplicity_layout[2] + '|' * self.multiplicity_layout[1] + '.' * self.multiplicity_layout[0]
            constraint_string = target_constraint + '&' + oligo_constraint
            
        # Initialize secondary_sites dictionary to store all found sites
        secondary_sites: Dict[str, List[Site]] = {}
            
        # Process each target
        for target_id, target in self.candidate_targets.items():
            logging.info(f"Processing target {target_id}")
            
            # Calculate oligo MFE once per target
            oligo_seq = str(Seq(target.sequence).reverse_complement())
            fc_oligo = RNA.fold_compound(oligo_seq, md)
            (_, oligo_mfe) = fc_oligo.mfe()
            
            start_pos = 0
            
            # Extract core region from target sequence based on multiplicity layout
            core_start = self.multiplicity_layout[0]
            core_end = core_start + self.multiplicity_layout[1]
            core_region = target.sequence[core_start:core_end]
            
            while True:
                # Find next occurrence of core region
                pos = pre_mrna_seq.find(core_region, start_pos)
                if pos == -1:  # No more occurrences
                    break
                    
                # Get the full sequence including flanks based on multiplicity_layout
                left_flank_size = self.multiplicity_layout[0]  # Left flank size
                right_flank_size = self.multiplicity_layout[2]  # Right flank size
                
                # Adjust position to account for core region offset
                adjusted_pos = pos - core_start
                
                # Get flanking sequences
                left_flank = pre_mrna_seq[max(0, adjusted_pos):adjusted_pos + left_flank_size]
                right_flank = pre_mrna_seq[adjusted_pos + left_flank_size + len(core_region):adjusted_pos + left_flank_size + len(core_region) + right_flank_size]
                
                # Skip if we don't have enough flanking sequence
                if len(left_flank) < left_flank_size or len(right_flank) < right_flank_size:
                    start_pos = pos + 1
                    continue
                    
                # Calculate genomic coordinates
                if self.gene.strand == '+':
                    genomic_start = self.gene.start + adjusted_pos
                    genomic_end = genomic_start + (left_flank_size + len(core_region) + right_flank_size - 1)
                else:
                    genomic_end = self.gene.end - adjusted_pos
                    genomic_start = genomic_end - (left_flank_size + len(core_region) + right_flank_size - 1)
                    
                # Create site identifier
                site_id = f"{self.gene.chromosome}:{genomic_start}-{genomic_end}:{self.gene.strand}"
                
                # Create Site object with the full sequence including flanks
                site = Site(
                    sequence=left_flank + core_region + right_flank,
                    chromosomal_position=site_id
                )
                print(site)
                # Initialize list for this site_id if it doesn't exist
                if target_id not in secondary_sites:
                    secondary_sites[target_id] = []
                secondary_sites[target_id].append(site)
                
                start_pos = pos + 1
                
            if not secondary_sites[target_id]:
                logging.warning(f"No secondary sites found for target {target_id} in gene {self.gene_id}")
                continue
                
            logging.info(f"Found {len(secondary_sites[target_id])} secondary sites for target {target_id}")
            
            self.repeated_sites[target_id] = []
            
            for site_id, sites in secondary_sites.items():
                position_to_ignore = target.chromosomal_position
                
                for site in sites:
                    # Skip if this is the main target position
                    if site.chromosomal_position == position_to_ignore:
                        logging.info(f"Skipping main target position {site.chromosomal_position} for target {target_id}")
                        continue
                        
                    fc_repeated_site = RNA.fold_compound(site.sequence, md)
                    (_, repeated_site_mfe) = fc_repeated_site.mfe()
                    
                    repeated_duplex = site.sequence + "&" + oligo_seq
                    fc_repeated_duplex = RNA.fold_compound(repeated_duplex, md)
                    
                    if force_core_alignment and constraint_string:
                        fc_repeated_duplex.hc_add_from_db(constraint_string)
                    (_, repeated_duplex_mfe) = fc_repeated_duplex.mfe()
                    
                    mutated_binding_dg = repeated_duplex_mfe - (repeated_site_mfe + oligo_mfe)
                    ddg_binding = mutated_binding_dg - target.dG
                    
                    if ddg_binding <= max_ddg_threshold:
                        self.repeated_sites[target_id].append(site)

            logging.info(f"Found {len(self.repeated_sites[target_id])} repeated sites for target {target_id}")
            
        total_sites = sum(len(sites) for sites in self.repeated_sites.values())
        logging.info(f"Extracted {total_sites} repeated sites across all targets")

        # Write repeated sites to FASTA file if output_file is provided
        if output_file:
            logging.info(f"Writing repeated sites to FASTA file: {output_file}")
            with open(output_file, 'w') as f:
                for target_id, sites in self.repeated_sites.items():
                    for i, site in enumerate(sites):
                        # Create a descriptive header with target ID, site number, and chromosomal position
                        header = f">{target_id}_repeated_{i+1} {site.chromosomal_position}"
                        f.write(f"{header}\n{site.sequence}\n")
            logging.info(f"Successfully wrote {total_sites} repeated sites to {output_file}")
  
    def _extract_secondary_sites(self, infile: str) -> Dict[str, List[Site]]:
        """
        Extract secondary sites for each target from the Bowtie2 alignment results.
        
        Parameters:
            infile (str): Path to the input SAM file from Bowtie2 alignment.
        
        Returns:
            Dict[str, List[Site]]: Dictionary of secondary sites for each QNAME.
        """
        cols = ["QNAME", "FLAG", "RNAME", "POS", "MAPQ", "CIGAR", "RNEXT", "PNEXT", "TLEN", "SEQ", "QUAL", "ALIGN_SCORE"]
        
        sam_df = pl.read_csv(infile, separator="\t", has_header=False, new_columns=cols, truncate_ragged_lines=True)
        
        logging.info(f"Extracting secondary sites for {len(sam_df)} alignments")
        
        secondary_sites: Dict[str, List[Site]] = {qname: [] for qname in sam_df['QNAME'].unique()}
        
        sam_df = sam_df.with_columns((pl.col('POS') - self.multiplicity_layout[0]).alias('adjusted_pos'))
        
        for transcript_id in sam_df['RNAME'].unique():
            try:
                transcript_obj = self.genome.transcript_by_id(transcript_id.split('.')[0])
            except ValueError:
                if self.genome_scaffolds:
                    try:
                        transcript_obj = self.genome_scaffolds.transcript_by_id(transcript_id.split('.')[0])
                    except ValueError:
                        logging.warning(f"Transcript {transcript_id} not found in either genome")
                        continue
                else:
                    continue
            
            transcript_df = sam_df.filter(pl.col('RNAME') == transcript_id)
            
            for qname_tuple, qname_df in transcript_df.group_by('QNAME'):
                qname = qname_tuple[0]  # Extract the string from the tuple
                positions = qname_df['adjusted_pos'].to_list()
                chrom_positions = transcript_obj.get_chromosomal_positions(positions, self.k)
                seqs = [
                    self.genome.get_transcript_subsequence(transcript_id, pos, self.k)
                    for pos in positions
                ]
                
                valid_pairs = set()
                for i, (pos, seq) in enumerate(zip(chrom_positions, seqs)):
                    if pos is not None and seq is not None:
                        valid_pairs.add((pos, seq))
                
                for pos, seq in valid_pairs:
                    secondary_site = Site(sequence=seq, chromosomal_position=pos)
                    secondary_sites[qname].append(secondary_site)
        
        logging.info(f"Extracted {sum(len(sites) for sites in secondary_sites.values())} secondary sites")
        return secondary_sites


    def extract_offtarget_sites(self, infile: str) -> Dict[str, List[Site]]:
        """
        Extract off-target sites for each target from the Bowtie2 alignment results.
        Off-target sites are secondary sites that are not the main target site
        or any of the repeated sites.
        
        Parameters:
            infile (str): Path to the input SAM file from Bowtie2 alignment.
            
        Returns:
            Dict[str, List[Site]]: Dictionary of off-target sites for each QNAME.
        """
        logging.info("Extracting off-target sites")
        
        secondary_sites = self._extract_secondary_sites(infile)
        
        for qname, sites in secondary_sites.items():
            seq_id, site_idx = qname.split('_')
            if site_idx == '0':
                continue
            
            main_position = self.candidate_targets[seq_id].chromosomal_position
            repeated_positions = [site.chromosomal_position for site in self.repeated_sites[seq_id]]
            positions_to_ignore = set([main_position] + repeated_positions)
            
            for site in sites:
                if site.chromosomal_position not in positions_to_ignore:
                    existing_sites = [
                        s for s in self.off_target_sites.get(seq_id, [])
                        if s.chromosomal_position == site.chromosomal_position and s.sequence == site.sequence
                    ]
                    
                    if not existing_sites:
                        if seq_id not in self.off_target_sites:
                            self.off_target_sites[seq_id] = []
                        self.off_target_sites[seq_id].append(site)

        logging.info(f"Extracted {sum(len(sites) for sites in self.off_target_sites.values())} off-target sites")
        


    def store_kmer_results(self) -> None:
        """
        Generate a CSV file with detailed results for each k-mer, including various properties and metrics.
        Converts nested data structures to string representations for CSV compatibility.
        """
        logging.info("Completing final results")

        results = []
        for idx, candidate in self.candidate_targets.items():
            chromosomal_position = candidate.chromosomal_position
            position_without_strand = chromosomal_position.rstrip(':+-') if chromosomal_position else ""
            ensembl_link = f"https://www.ensembl.org/{self.species}/Location/View?r={position_without_strand}"
            
            oligo_reverse_comp = str(Seq(candidate.sequence).reverse_complement())
            
            transcript_count = len(candidate.transcripts) if isinstance(candidate.transcripts, list) else 0
            total_transcripts = len(self.gene.transcripts)
            transcript_prevalence_ratio = round(transcript_count / total_transcripts, 3) if total_transcripts > 0 else 0
            
            transcript_ids = [t.transcript_id for t in candidate.transcripts] if isinstance(candidate.transcripts, list) else []
            ordered_transcripts_str = ','.join(transcript_ids)
            
            exon_ids = [e.exon_id for e in candidate.exons] if isinstance(candidate.exons, list) else []
            ordered_exons_str = ','.join(exon_ids)
            
            results.append({
                'seq_num': idx,
                'target': candidate.sequence,
                'absolute_loc': chromosomal_position,
                'oligo_reverse_comp': oligo_reverse_comp,
                'oligo_GC_content': gc_fraction(oligo_reverse_comp),
                'oligo_AT_run': longest_at_run(oligo_reverse_comp),
                'oligo_T_run': longest_t_run(oligo_reverse_comp),
                'repeated_sites_multiplicity': len(self.repeated_sites.get(idx, [])),
                'off_targets_multiplicity': len(self.off_target_sites.get(idx, [])),
                'pedersen_steady_state_target_percentage': candidate.pedersen_steady_state,
                'dG_binding': candidate.dG,
                'oligo_homodimer_dG': candidate.oligo_dG,
                'transcript_prevalence_ratio': transcript_prevalence_ratio,
                'ensembl_link': ensembl_link,
            })
            
        kmer_results = pl.DataFrame(results)

        output_path = os.path.join(self.data_dir, 'results', f"{self.gene_id}_{self.k}mer_results.csv")
        kmer_results.write_csv(output_path)

        logging.info(f"Results saved to {output_path}")
