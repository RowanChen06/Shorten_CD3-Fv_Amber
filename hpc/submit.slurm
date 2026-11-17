#!/usr/bin/env bash
#SBATCH --job-name=cd3-fv
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --time=24:00:00
#SBATCH --output=cd3-%j.out
set -euo pipefail
cd -- "${SLURM_SUBMIT_DIR:?Submit from the package root}"
if [[ -n ${SITE_ENV:-} ]]; then source "$SITE_ENV"; fi
export ENGINE=${ENGINE:-pmemd.cuda}
exec bash run.sh "${PROFILE:-full}"
