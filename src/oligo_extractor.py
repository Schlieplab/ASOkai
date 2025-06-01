from typing import List, Set, Tuple, Dict, Optional, Union
from Bio.SeqUtils import gc_fraction
from genome_utils import TargetSite, Site
from Bio.Seq import Seq
from src.utils.sequence_analysis import (
    longest_at_run,
    longest_t_run,
    calculate_homodimer_binding_energy,
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
        
        self.pre_mrna_fasta_path = self.genome.extract_genome_premrna_sequences(output_path=pre_mrna_fasta_path, exclude_genes=self.gene_id)

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
    def _process_repeated_sites_target_worker(args: Tuple[str, str, float, str, str, List[int], bool, float, str, int, int, str]) -> Tuple[str, int, List[Site]]:
        """
        Static worker function to find repeated sites for a single target.

        Args:
            args: A tuple containing:
                target_id (str): Identifier for the target.
                target_sequence (str): The sequence of the target.
                target_dG (float): The dG binding energy of the target.
                target_chromosomal_position (str): The chromosomal position of the target.
                pre_mrna_seq (str): The pre-mRNA sequence of the gene.
                multiplicity_layout (List[int]): Layout for core and flank regions.
                force_core_alignment (bool): Whether to force core alignment.
                max_ddg_threshold (float): Max ddG for filtering repeated sites.
                gene_strand (str): Strand of the gene ('+' or '-').
                gene_start (int): Start position of the gene.
                gene_end (int): End position of the gene.
                gene_chromosome (str): Chromosome of the gene.

        Returns:
            A tuple containing (target_id, raw_site_count, list_of_repeated_sites).
        """
        target_id, target_sequence, target_dG, target_chromosomal_position, \
        pre_mrna_seq, multiplicity_layout, force_core_alignment, max_ddg_threshold, \
        gene_strand, gene_start, gene_end, gene_chromosome = args

        md = RNA.md()
        md.temperature = 37.0
        constraint_string: Optional[str] = None
        if force_core_alignment:
            target_constraint = '.' * multiplicity_layout[0] + '|' * multiplicity_layout[1] + '.' * multiplicity_layout[2]
            oligo_constraint = '.' * multiplicity_layout[2] + '|' * multiplicity_layout[1] + '.' * multiplicity_layout[0]
            constraint_string = target_constraint + '&' + oligo_constraint

        oligo_seq = str(Seq(target_sequence).reverse_complement())
        fc_oligo = RNA.fold_compound(oligo_seq, md)
        (_, oligo_mfe) = fc_oligo.mfe()

        core_start_idx = multiplicity_layout[0]
        core_end_idx = core_start_idx + multiplicity_layout[1]
        core_region = target_sequence[core_start_idx:core_end_idx]

        current_target_secondary_sites: List[Site] = []
        start_pos = 0
        
        expected_site_len = multiplicity_layout[0] + multiplicity_layout[1] + multiplicity_layout[2]

        while True:
            pos = pre_mrna_seq.find(core_region, start_pos)
            if pos == -1:
                break
            
            # adjusted_pos is the start of the full potential site in pre_mrna_seq
            adjusted_pos = pos - core_start_idx 
            
            full_site_start_in_premrna = adjusted_pos
            full_site_end_in_premrna = adjusted_pos + expected_site_len

            if full_site_start_in_premrna < 0 or full_site_end_in_premrna > len(pre_mrna_seq):
                start_pos = pos + 1
                continue
            
            site_sequence = pre_mrna_seq[full_site_start_in_premrna:full_site_end_in_premrna]

            if len(site_sequence) != expected_site_len:
                start_pos = pos + 1 # Move to next search position in pre_mrna_seq
                continue
                
            # Calculate genomic coordinates
            # gene_start and gene_end are 1-based from GTF
            # adjusted_pos is 0-based relative to pre_mrna_seq start
            # chromosomal positions should be 1-based
            if gene_strand == '+':
                # For + strand, pre_mrna_seq coordinates map directly from gene_start
                genomic_start_coord = gene_start + full_site_start_in_premrna
                genomic_end_coord = gene_start + full_site_end_in_premrna -1
            else: # - strand
                # For - strand, pre_mrna_seq coordinates map inversely from gene_end
                genomic_end_coord = gene_end - full_site_start_in_premrna
                genomic_start_coord = gene_end - full_site_end_in_premrna + 1
            
            site_chrom_pos = f"{gene_chromosome}:{genomic_start_coord}-{genomic_end_coord}:{gene_strand}"
            
            site_obj = Site(sequence=site_sequence, chromosomal_position=site_chrom_pos)
            logging.debug(f"Potential site found for target {target_id} at {site_obj.chromosomal_position}: {site_obj.sequence}")
            current_target_secondary_sites.append(site_obj)
            start_pos = pos + 1

        raw_site_count = len(current_target_secondary_sites)
        if raw_site_count == 0:
            return target_id, 0, []

        final_repeated_sites_for_target: List[Site] = []
        for site in current_target_secondary_sites:
            if site.chromosomal_position == target_chromosomal_position:
                continue
            
            fc_repeated_site = RNA.fold_compound(site.sequence, md)
            (_, repeated_site_mfe) = fc_repeated_site.mfe()
            
            repeated_duplex = site.sequence + "&" + oligo_seq
            fc_repeated_duplex = RNA.fold_compound(repeated_duplex, md)
            
            if force_core_alignment and constraint_string:
                fc_repeated_duplex.hc_add_from_db(constraint_string)
            (_, repeated_duplex_mfe) = fc_repeated_duplex.mfe()
            
            mutated_binding_dg = repeated_duplex_mfe - (repeated_site_mfe + oligo_mfe)
            ddg_binding = mutated_binding_dg - target_dG
            
            if ddg_binding <= max_ddg_threshold:
                final_repeated_sites_for_target.append(site)
        
        return target_id, raw_site_count, final_repeated_sites_for_target

    def extract_repeated_sites(self, max_ddg_threshold: float = 5.0, force_core_alignment: bool = False, output_file: Optional[str] = None, num_processes: Optional[int] = None) -> None:
        """
        Extract repeated sites by finding occurrences of the core region in the target gene's pre-mRNA sequence, using multiprocessing.
        Parameters:
            max_ddg_threshold (float): Maximum ddG threshold for keeping a site.
                                        Sites with ddG values above this threshold will be filtered out.
            force_core_alignment (bool): If True, force core alignment of the target and oligo.
            output_file (Optional[str]): If provided, path to save repeated sites in FASTA format.
            num_processes (Optional[int]): Number of processes to use. If None, uses CPU count.
        """
        logging.info("Extracting repeated sites using multiprocessing")
        
        if not self.gene.pre_mrna_sequence:
            logging.error(f"No pre-mRNA sequence available for target gene {self.gene_id}")
            raise ValueError(f"No pre-mRNA sequence available for target gene {self.gene_id}")
            
        pre_mrna_seq = self.gene.pre_mrna_sequence
        
        self.repeated_sites: Dict[str, List[Site]] = {} # Initialize

        tasks = []
        if not self.candidate_targets:
            logging.info("No candidate targets to process for repeated sites.")
        else:
            for target_id, target in self.candidate_targets.items():
                tasks.append((
                    target_id,
                    target.sequence,
                    target.dG,
                    target.chromosomal_position,
                    pre_mrna_seq,
                    self.multiplicity_layout,
                    force_core_alignment,
                    max_ddg_threshold,
                    self.gene.strand,
                    self.gene.start, # gene.start, gene.end are 1-based
                    self.gene.end,
                    self.gene.chromosome
                ))

        if not tasks:
            # This case is already handled by the candidate_targets check above,
            # but as a safeguard if tasks end up empty for other reasons.
            logging.info("No tasks to run for repeated sites extraction.")
            total_sites = sum(len(sites) for sites in self.repeated_sites.values()) # Will be 0
            logging.info(f"Extracted {total_sites} repeated sites across all targets") # Logs 0 sites
            if output_file:
                 # Write empty or header-only file if that's desired, or just log
                logging.info(f"Writing repeated sites to FASTA file: {output_file} (0 sites found).")
                with open(output_file, 'w') as f:
                    pass # Creates an empty file
            return

        if num_processes is None:
            num_processes = mp.cpu_count()
        
        logging.info(f"Starting repeated sites extraction using {num_processes} processes for {len(tasks)} targets.")
        
        with mp.Pool(processes=num_processes) as pool:
            # Using map to preserve order, though order of accumulation into self.repeated_sites doesn't strictly matter
            results = pool.map(OligoExtractor._process_repeated_sites_target_worker, tasks)
            
            for target_id_from_pool, raw_site_count, filtered_sites_list in results:

                if filtered_sites_list:
                    self.repeated_sites[target_id_from_pool] = filtered_sites_list
                elif raw_site_count > 0: # Raw sites found, but none passed filtering (empty filtered_sites_list)
                    pass # Explicitly pass if no action other than logging was here previously and logging is removed
            
        total_passed_sites = sum(len(sites) for sites in self.repeated_sites.values())
        logging.info(f"Extracted {total_passed_sites} repeated sites across all targets.")

        if output_file:
            with open(output_file, 'w') as f:
                for target_id_from_self, sites_list in self.repeated_sites.items():
                    if sites_list: # Should always be true if target_id_from_self is in self.repeated_sites keys
                        for i, site_obj in enumerate(sites_list):
                            header = f">{target_id_from_self}_repeated_{i+1} {site_obj.chromosomal_position}"
                            f.write(f"{header}\n{site_obj.sequence}\n")
            logging.info(f"Successfully wrote {total_passed_sites} repeated sites to {output_file}.")
  
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
            repeated_positions = [site.chromosomal_position for site in self.repeated_sites.get(seq_id, [])]
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
