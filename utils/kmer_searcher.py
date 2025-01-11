import logging
import time
import multiprocessing as mp
import itertools
from cacheout import Cache
import configparser
import multiprocessing
from functools import partial


# Create a configparser object
config = configparser.ConfigParser()

# Read the configuration file
config.read('config.ini')


class KmerSearcher:
    """
    A class for searching and analyzing k-mers in a given set of oligonucleotides.
    

    Attributes:
        max_distance (int): The maximum allowed Hamming distance for mismatches.
        rnas_h_cleavage_length (int): The length threshold for RNase H cleavage.
        reference_kmers (set): A set of reference k-mers to search against.
        out_file (str): The path to the output file for storing results.
        multiplicity_layout (list): A list defining the layout for multiplicity calculation.
        total_kmers_found (set): A set to store all found k-mers.
        population (dict): A dictionary mapping nucleotides to their possible substitutions.

    Methods:
        __init__(self, reference_kmers, max_distance, rnas_h_cleavage_length, out_file):
            Initialize the KmerSearcher object.

        _get_changed(self, sub, i):
            Generate all possible single-nucleotide changes at a specific position.

        _get_mismatch(self, d, set_matches, match_cache):
            Recursively generate mismatches up to a specified Hamming distance.

        process_oligo(oligo, reference_kmers, multiplicity_layout, max_distance, rnas_h_cleavage_length, searcher):
            Process a single oligonucleotide to find matching k-mers.

        longest_substring_below_threshold(s1, s2, max_distance):
            Check if the longest common substring between two sequences is below a threshold.

        search(self, oligos):
            Perform a parallel search for k-mers in the given set of oligonucleotides.

    """
    def __init__(self, reference_kmers, max_distance, rnas_h_cleavage_length, out_file):
        self.max_distance = max_distance
        self.rnas_h_cleavage_length = rnas_h_cleavage_length
        self.reference_kmers = set(reference_kmers)
        self.out_file = out_file
        self.multiplicity_layout = [int(x) for x in config["DEFAULT"]["MultiplicityLayout"].split(',')]
        self.total_kmers_found = set()
        self.info = mp.get_logger().info

        self.population = {
            'A': ['C', 'G', 'T'],
            'C': ['A', 'G', 'T'],
            'G': ['A', 'C', 'T'],
            'T': ['A', 'C', 'G']
        }
        logging.info("Start reading file")
        starttime = time.time()

    def _get_changed(self, sub, i):
        return [sub[0:i] + c + sub[i + 1:] for c in self.population[sub[i]]]

    def _get_mismatch(self, d, set_matches, match_cache):
        if d == 0:
            return set_matches

        new_matches = set()
        for sub in set_matches:
            new_matches.update(list(map(lambda x: ''.join(x),
                                        itertools.chain.from_iterable(
                                            ([self._get_changed(sub, i) for i, c in enumerate(sub)])))))

        set_matches = (set_matches.union(new_matches))
        if not match_cache.get((d - 1, str(set_matches)), 0):
            match_cache.set((d - 1, str(set_matches)), self._get_mismatch(d - 1, set_matches, match_cache))

        return match_cache.get((d - 1, str(set_matches)))

    @staticmethod
    def process_oligo(oligo, reference_kmers, multiplicity_layout, max_distance, rnas_h_cleavage_length, searcher):
        oligo_id, oligo_seq = oligo

        s = oligo_seq[multiplicity_layout[0]:multiplicity_layout[0] + multiplicity_layout[1]]
        mmatchHash = Cache(maxsize=512 * 512, ttl=0, timer=time.time, default=None)
        result = list(searcher._get_mismatch(max_distance, {s}, mmatchHash))
        result.remove(s)

        total_kmers_found = set()
        j = 0
        for r in result:
            sr = oligo_seq[:multiplicity_layout[0]] + r + oligo_seq[multiplicity_layout[0] + multiplicity_layout[1]:]
            if sr in reference_kmers and KmerSearcher.longest_substring_below_threshold(s, r, rnas_h_cleavage_length):
                total_kmers_found.add((oligo_id, j, sr))
                j += 1

        return total_kmers_found

    @staticmethod
    def longest_substring_below_threshold(s1, s2, max_distance):
        t = [[0] * (1 + len(s2)) for _ in range(1 + len(s1))]
        for x in range(1, 1 + len(s1)):
            for y in range(1, 1 + len(s2)):
                if s1[x - 1] == s2[y - 1]:
                    t[x][y] = t[x - 1][y - 1] + 1
                    if t[x][y] >= max_distance:
                        return False  # Early exit if longer substring is found
                else:
                    t[x][y] = 0
        return True  # Return True if no substring longer than max_distance is found

    def search(self, oligos):
        logging.info("Start search. This may take a while...")

        non_prone_multiplicity = dict()
        # Create a multiprocessing pool
        with multiprocessing.Pool(processes=multiprocessing.cpu_count()) as pool:
            # Create a partial function with shared arguments
            process_partial = partial(KmerSearcher.process_oligo, reference_kmers=self.reference_kmers,
                                    multiplicity_layout=self.multiplicity_layout,
                                    max_distance=self.max_distance,
                                    rnas_h_cleavage_length=self.rnas_h_cleavage_length,
                                    searcher=self)

            # Map the oligos to the processing function
            results = pool.map(process_partial, oligos)

        total_kmers_found = set()
        for result in results:
            total_kmers_found.update(result)

        with open(self.out_file, "w") as file:
            for kmer_tup in total_kmers_found:
                non_prone_multiplicity[kmer_tup[0]] = non_prone_multiplicity.get(kmer_tup[0], 0) + 1
                file.write(">%s_%i\n%s\n" % kmer_tup)

        logging.info("{} total kmers found through searches".format(len(total_kmers_found)))
        if len(total_kmers_found) == 0:
            logging.info("No off-Targets found. Exiting.")
            exit(0)

        return non_prone_multiplicity