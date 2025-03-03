#!/bin/bash
# SBATCH --job-name=genmap
#SBATCH --ntasks=1                # Number of tasks (processes)
#SBATCH --cpus-per-task=64          # Number of CPU cores per task
#SBATCH --mem=128G                   # Memory per node
#SBATCH --time=02:00:00            # Time limit (hh:mm:ss)
#SBATCH --partition=smp       # Partition to submit to
#SBATCH --account=root        # Your account name

# Load necessary modules here

cd /home/ayat/Repositories/ASODesignPipeline/genmap-build

# Your commands for the genmap job
echo "Starting genmap job at: $(date)"
# Your code goes here
# ./bin/genmap index -F /home/ayat/Repositories/ASODesignPipeline/utils/GRCh38_masked.fa -I /home/ayat/Repositories/ASODesignPipeline/data/genmap-index -S 8
./bin/genmap map -I /home/ayat/Repositories/ASODesignPipeline/data/genmap-index -O /home/ayat/Repositories/ASODesignPipeline/data/genmap-res -E 0 -K 8 -S /home/ayat/Repositories/ASODesignPipeline/KRAS.bed -w -fl --csv
echo "Finished genmap job at: $(date)"