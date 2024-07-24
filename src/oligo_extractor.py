import csv
import subprocess
import shlex
import os
from Bio.SeqUtils import gc_fraction
from pyensembl import EnsemblRelease, Genome
import logging
import time
import configparser 

# Create a configparser object
config = configparser.ConfigParser()

# Read the configuration file
config.read('config.ini')



class OligoExtractor:
    def __init__(self, gene_id, e_release, g_assembly, species, k, bowtie_index, gc_bounds= None, scaffold_path=None):
        self.gene_id = gene_id
        self.k = k
        self.filtered_kmers = []
        self.gc_bounds=gc_bounds
        self.bowtie_index = bowtie_index
        self.bowtie_infile = f"{config['DEFAULT']['DataDir']}/bowtie2Home/{self.gene_id}_{self.k}mers.fa"

        if species == "mouse":
            species = "mus_musculus"
            # mouse doesn't have scaffold so far...
        elif species == "human":
            species = "homo_sapiens"
        else:
            raise ValueError("Only mouse or human species implemented.")

        self.ensembl_obj = EnsemblRelease(release=e_release, species=species)
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

        self.gene = self.ensembl_obj.gene_by_id(gene_id=gene_id)
        logging.info(f"Gene name: {self.gene.gene_name}")
        logging.info(f"Build transcript gene references")
        self.transcript_lookup = self._get_gene_transcript_mapping(save_to_file=f"transcript_gene_mapping_GRC{species[0]}{g_assembly}.csv")

    def _kmers(self, s):
        kmers_list = [s[i:i + self.k] for i in range(len(s) - self.k + 1)]
        if self.gc_bounds:
            kmers_list = [seq for seq in kmers_list if self.gc_bounds[0] <= gc_fraction(seq) <= self.gc_bounds[1]]
        kmers_set = set(kmers_list)
        if len(kmers_list) - len(kmers_set) > 0:
            print(len(kmers_list) - len(kmers_set), "multiple occurences")
        return kmers_set

    def _get_gene_transcript_mapping(self, save_to_file=None):
        # TODO: might be extended to exon mapping
        transcript_lookup = dict()
        transcripts = self.ensembl_obj.transcripts()
        if self.scaffold_path:
            print(len(transcripts))
            transcripts.extend(self.ensembl_obj_scaffolds.transcripts())
            print(len(transcripts))

        if save_to_file:
            file = open(f"{config['DEFAULT']['DataDir']}/{save_to_file}", "w")
        for t in transcripts:
            if t.transcript_id not in transcript_lookup.keys():
                transcript_lookup[t.transcript_id] = {"gene_id": t.gene_id, "gene_name": t.gene_name}
                if save_to_file:
                    for e in t.exons:
                        file.write(
                            f"{t.transcript_id},{t.gene_id},{t.start},{t.end},{e.exon_id},{e.start},{e.end},{t.gene_name}\n")
        if save_to_file:
            file.close()
        return transcript_lookup

    def _runCommand(self, command):
        """ Execute command while immediately printing its stdout to outFile and stderr to the terminal (or logging)."""
        return_code = subprocess.call(shlex.split(command))
        return return_code

    def run_bowtie(self):
        logging.info(f"Running Bowtie2")
        outFile = os.path.splitext(self.bowtie_infile)[0] + ".sam"

        # Run RNAcofold
        logging.info("Running Bowtie2")

        command = f'bowtie2 -x {config["DEFAULT"]["DataDir"]}/bowtie2Home/{self.bowtie_index} -U {self.bowtie_infile} -S {outFile} {config["DEFAULT"]["BowtieArgs"]}'
        logging.info("Command: {}".format(command))
        return_code = self._runCommand(command)
        logging.info("Return Code: {}".format(return_code))
        start = time.time()
        with open(outFile, 'r') as btFile:
            align_file = csv.reader(btFile, delimiter='\t')
            # allheader = ["QNAME", "FLAG", "RNAME", "POS", "MAPQ", "CIGAR", "RNEXT", "PNEXT", "TLEN", "SEQ", "QUAL", "ALIGN SCORE", "XS", "XN", "XM", "XO", "XG", "EDIT DIST REF", "MISMATCH POS", "YT"]
            current_targetSite, current_ah_genes, exon_hits_target_gene = None, set(), set()
            for row in align_file:
                if not current_targetSite:
                    current_targetSite = row[9]  # SEQ field in SAM
                if current_targetSite != row[9]:
                    if current_targetSite == 'AAAGACTCCTAATAGC':
                        print(f"AZD4785: {current_ah_genes}")
                    if len(current_ah_genes) == 0:

                        # if len(exon_hits_target_gene) < 2:
                        self.filtered_kmers.append(current_targetSite)
                    current_targetSite = row[9]
                    current_ah_genes = set()
                    exon_hits_target_gene = set()

                transcript_id = row[2].split(".")[0]  # RNAME field in SAM
                if row[17] == 'NM:i:1':
                    continue
                try:
                    ah_gene_id = self.transcript_lookup[transcript_id]["gene_id"]
                    ah_gene_name = self.transcript_lookup[transcript_id]["gene_name"]
                except KeyError:
                    logging.error(f"Transcript {transcript_id} not found. Check on ensembl.org! Skipping Alignment")
                    continue

                if ah_gene_id != self.gene_id:
                    current_ah_genes.add(ah_gene_id)
                    if ah_gene_name == self.gene.gene_name:
                        logging.info(f"{self.gene.gene_name} has additional gene ID: {ah_gene_id}")
                else:
                    t = self.ensembl_obj.transcript_by_id(transcript_id)
                    abs_pos = t.start + int(row[3]) - 1  # absolute position from POS field in SAM
                    for e in t.exons:
                        if e.start <= abs_pos <= e.end:
                            exon_hits_target_gene.add(e.exon_id)
        end = time.time() - start
        logging.info(f"Viable  {self.k}mers candidates after Bowtie: {len(self.filtered_kmers)}")
        logging.info(f"Bowtie Processing time: {end}")

    def get_candidate_oligos_by_gene(self):
        """

        :param gene_id: String using the Ensembl ID of the gene
        :param e_release: Ensemble Release
        :param k: length of oligo/kmers to extract
        :return: list of distinct candidate of oligos
        """

        logging.info(f"Extract {self.k}mers from gene {self.gene_id}")

        transcripts = self.gene.transcripts
        candidate_oligos = set()
        for t in transcripts:
            # rev_comp_t = Seq(t.sequence).reverse_complement()
            # TODO: make GC content bounds a parameter
            kmers_set = self._kmers(t.sequence)
            candidate_oligos.update(kmers_set)
        logging.info(f"{len(candidate_oligos)} candidate {self.k}mers found")
        seq_count_id = 1

        os.makedirs(f'{config["DEFAULT"]["DataDir"]}/bowtie2Home', exist_ok=True)
        with open(self.bowtie_infile, "w") as tmp_bowtie_in:
            for can in candidate_oligos:
                tmp_bowtie_in.write(">S" + str(seq_count_id).zfill(6) + "\n")
                tmp_bowtie_in.write(str(can) + "\n")
                seq_count_id += 1
