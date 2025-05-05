from typing import List, Set, Tuple, Dict, Optional, Union
from Bio.SeqUtils import gc_fraction
from src.utils.genome import Genome
from Bio.Seq import Seq
from src.utils.sequence_analysis import (
    longest_at_run,
    longest_t_run,
    calculate_homodimer_binding_energy
)
import logging
import polars as pl
import os
from typing import List, Optional
from src.utils.genome import TargetSite, Site
import RNA

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
        cdna_path: str, 
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
            cdna_path (str): The file path or URL to the cDNA FASTA file for transcript sequences.
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
        self.candidate_targets: Dict[str, TargetSite] = {}
        self.multiplicity_layout: List[int] = multiplicity_layout
        self.gc_bounds: Tuple[float, float] = gc_bounds
        self.data_dir: str = data_dir
        self.bowtie_index: str = bowtie_index
        self.repeated_sites: Dict[str, List[Site]] = {}
        self.off_target_sites: Dict[str, List[Site]] = {}
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
            annotation_version=self.e_release,
            gtf_path=gtf_path,
            transcript_fasta_paths=cdna_path,            
        )
        
        self.genome.index(overwrite=False)


        if scaffold_path:
            self.genome_scaffolds: Optional[Genome] = Genome(
                reference_name=f'GRCh{g_assembly}',
                gtf_path=scaffold_path,
            )
            self.genome_scaffolds.index()
        else:
            self.genome_scaffolds = None
        

        self.gene = self.genome.gene_by_id(gene_id=gene_id)
        
        logging.info(f"Gene name: {self.gene.gene_name}")
        logging.info(f"Gene id: {self.gene_id}")
        
        logging.info("Building transcript gene references. This may take a while...")
        self.transcript_gene_lookup: Dict[str, str] = self._get_gene_transcript_mapping()
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

    def _get_gene_transcript_mapping(self) -> Dict[str, str]:
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
        # Dictionary to track unique oligos by their sequence and position
        # Key: (sequence, chromosomal_position), Value: TargetSite object
        candidate_targets_dict : Dict[Tuple, TargetSite] = {}
        
        for t in transcripts:
            # Extract k-mers from transcript sequence
            kmers_set = self._kmers(t.sequence, self.k)
            
            for kmer_seq, position in kmers_set:
                # Get chromosomal position using the class method
                chrom_pos = t.get_chromosomal_position(position, self.k)
                
                if chrom_pos is None:
                    continue  # Skip if no valid chromosomal position
                
                # Use the sequence and chromosomal position as a composite key
                key = (kmer_seq, chrom_pos)
                
                # Get exon information
                exon = t.get_exon_by_position(position)
                
                if key not in candidate_targets_dict:
                    
                    # calculate homodimer dG
                    homodimer_dG = calculate_homodimer_binding_energy(kmer_seq)
                    
                    # Create new TargetSite object
                    candidate_targets_dict[key] = TargetSite(
                        sequence=kmer_seq,
                        chromosomal_position=chrom_pos,
                        gene_id=self.gene_id,
                        transcripts=[t],
                        exons=[exon],
                        oligo_dG=homodimer_dG,
                    )
                else:
                    # Update existing TargetSite with additional transcript and exon info
                    candidate_targets_dict[key].transcripts.append(t)
                    candidate_targets_dict[key].exons.append(exon)
        
        # Create indexed dictionary of TargetSite objects
        oligo_data_list = list(candidate_targets_dict.values())
        
        for i, oligo_data in enumerate(oligo_data_list, 1):
            index = f'S{str(i).zfill(6)}'
            self.candidate_targets[index] = oligo_data
        
        logging.info(f"{len(self.candidate_targets)} {self.k}-mer candidate target sites found.")
        

        # Write to FASTA file
        outfile = os.path.join(self.data_dir, 'oligos', f"{self.bowtie_index}_{self.gene_id}_{self.k}mers.fa")
        with open(outfile, "w") as tmp_bowtie_in:
            for index, oligo in self.candidate_targets.items():
                tmp_bowtie_in.write(f">{index}\n{oligo.sequence}\n")
        
        return outfile



    def filter_candidate_targets(self, in_file: str) -> None: # TODO: Add option to not filter
        """
        Filter the aligned k-mer target sites based on Bowtie2 alignment results.

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
        logging.info(f"Viable {self.k}-mer candidate sites after Bowtie: {len(filtered_oligos)}")
        
        outfile = os.path.join(self.data_dir, 'oligos', f"{self.bowtie_index}_{self.gene_id}_{self.k}mers_filtered.fa")

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
            # Get transcript object using the class method
            try:
                # Try main genome first
                transcript_obj = self.genome.transcript_by_id(transcript_id.split('.')[0])
            except ValueError:
                # Try scaffold genome if available
                if self.genome_scaffolds:
                    try:
                        transcript_obj = self.genome_scaffolds.transcript_by_id(transcript_id.split('.')[0])
                    except ValueError:
                        logging.warning(f"Transcript {transcript_id} not found in either genome")
                        continue
                else:
                    continue
            
            transcript_df = sam_df.filter(pl.col('RNAME') == transcript_id)
            
            # Group by QNAME within this transcript
            for qname, qname_df in transcript_df.group_by('QNAME'):
                # Extract positions for batch processing
                positions = qname_df['adjusted_pos'].to_list()
                
                # Get chromosomal positions using the transcript method
                chrom_positions = transcript_obj.get_chromosomal_positions(positions, self.k)
                
                # Get sequences
                seqs = [
                    self.genome.get_transcript_subsequence(transcript_id, pos, self.k)
                    for pos in positions
                ]
                
                # Optimize: Pre-filter null positions and use a set for uniqueness
                valid_pairs = set()
                for i, (pos, seq) in enumerate(zip(chrom_positions, seqs)):
                    if pos is not None and seq is not None:  # Filter out null positions
                        valid_pairs.add((pos, seq))
                
                # Create secondary sites from unique pairs
                for pos, seq in valid_pairs:
                    secondary_site = Site(sequence=seq, chromosomal_position=pos)
                    secondary_sites[qname].append(secondary_site)
        
        logging.info(f"Extracted {sum(len(sites) for sites in secondary_sites.values())} secondary sites")
        return secondary_sites

    def extract_repeated_sites(self, infile: str, min_ddg_threshold: float = 5.0) -> None:
        """
        Extract repeated sites from the Bowtie2 alignment results and calculate their binding energies.
        Parameters:
            infile (str): Path to the input SAM file from Bowtie2 alignment.
            min_ddg_threshold (float): Minimum ddG threshold for keeping a site 
                                        Sites with ddG values above this threshold will be filtered out.
        """
        logging.info("Extracting repeated sites")
        
        secondary_sites = self._extract_secondary_sites(infile)
        
        self.repeated_sites = {qname: [] for qname in self.candidate_targets.keys()}
        
        md = RNA.md()
        md.temperature = 37.0
        
        for qname, sites in secondary_sites.items():
            position_to_ignore = self.candidate_targets[qname].chromosomal_position
            
            # Original Oligo (reverse complement of the original target) - remains constant
            target_obj = Seq(self.candidate_targets[qname].sequence)
            oligo_seq = str(target_obj.reverse_complement())
            
            fc_oligo = RNA.fold_compound(oligo_seq, md)
            (_, oligo_mfe) = fc_oligo.mfe() # This oligo MFE is constant
            
            for site in sites:
                if site.chromosomal_position != position_to_ignore:
                    
                    fc_repeated_site = RNA.fold_compound(site.sequence, md)
                    (_, repeated_site_mfe) = fc_repeated_site.mfe()
                    
                    # MFE of the mutated duplex (mutated target & original oligo)
                    repeated_duplex = site.sequence + "&" + oligo_seq
                    fc_repeated_duplex = RNA.fold_compound(repeated_duplex, md)
                    (_, repeated_duplex_mfe) = fc_repeated_duplex.mfe()
                    
                    # Mutated Binding Energy (using constant oligo_mfe)
                    mutated_binding_dg = repeated_duplex_mfe - (repeated_site_mfe + oligo_mfe)
                    # --- End Mutated Binding Energy Calculation ---

                    # Calculate change in binding energy
                    ddg_binding = mutated_binding_dg - self.candidate_targets[qname].dG
                    
                    if ddg_binding <= min_ddg_threshold:
                        existing_sites = [
                            s for s in self.repeated_sites[qname] 
                            if s.chromosomal_position == site.chromosomal_position and s.sequence == site.sequence
                        ]
                        
                        if not existing_sites:
                            self.repeated_sites[qname].append(site)
        
        logging.info(f"Extracted {sum(len(sites) for sites in self.repeated_sites.values())} repeated sites")
        

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
        
        # Get all secondary sites
        secondary_sites = self._extract_secondary_sites(infile)

        
        for qname, sites in secondary_sites.items():
            # Get positions to ignore (main site and all repeated sites)
            seq_id, site_idx = qname.split('_')
            if site_idx == '0':
                # Skip if this is the main target site
                continue
            
            main_position = self.candidate_targets[seq_id].chromosomal_position
            repeated_positions = [site.chromosomal_position for site in self.repeated_sites[seq_id]]
            positions_to_ignore = set([main_position] + repeated_positions)
            
            # Filter for off-target sites
            for site in sites:
                if site.chromosomal_position not in positions_to_ignore:
                    # Check if this site is already in the list
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
            
            # Create Ensembl link
            chromosomal_position = candidate.chromosomal_position
            position_without_strand = chromosomal_position.rstrip(':+-') if chromosomal_position else ""
            ensembl_link = f"https://www.ensembl.org/{self.species}/Location/View?r={position_without_strand}"
            
            oligo_reverse_comp = str(Seq(candidate.sequence).reverse_complement())
            
            # Calculate transcript prevalence ratio
            transcript_count = len(candidate.transcripts) if isinstance(candidate.transcripts, list) else 0
            total_transcripts = len(self.gene.transcripts)
            transcript_prevalence_ratio = round(transcript_count / total_transcripts, 3) if total_transcripts > 0 else 0
            
            # Convert lists to comma-separated strings
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
                'dG_binding': candidate.dG,
                'oligo_homodimer_dG': candidate.oligo_dG,
                'transcript_prevalence_ratio': transcript_prevalence_ratio,
                'ordered_transcripts': ordered_transcripts_str,
                'ordered_exons': ordered_exons_str,
                'ensembl_link': ensembl_link,
            })
            
        # Create results DataFrame
        kmer_results = pl.DataFrame(results)

        # Write results to CSV
        output_path = f'{self.data_dir}/results/{self.gene_id}_{self.k}mer_results.csv'
        kmer_results.write_csv(output_path)

        logging.info(f"Results saved to {output_path}")
