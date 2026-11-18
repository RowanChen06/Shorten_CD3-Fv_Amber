#!/usr/bin/env bash
#SBATCH --job-name=cd3-dcu
#SBATCH --partition=hx1hdnormal
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=8
#SBATCH --cpus-per-task=16
#SBATCH --gres=dcu:8
#SBATCH --time=24:00:00
#SBATCH --output=cd3-dcu-%j.out
#SBATCH --export=ALL

# 平台环境脚本会探测可选的 hipcc，因此先不启用 errexit。
set +eu
module purge
source /public/home/aci37mn59u/apprepo/amber/26-dtk26.04_hx/scripts/env.sh

export HSA_FORCE_FINE_GRAIN_PCIE=1
export HIP_COMGR_ARCH=gfx936
export ROCBLAS_GPU_ARCHNAME=gfx936
export I_MPI_PMI_LIBRARY=/opt/gridview/slurm-3.1.0/lib/libpmi.so
export MPI_TYPE=pmix_v4
ulimit -l unlimited

set -euo pipefail

cd -- "${SLURM_SUBMIT_DIR:?请从项目根目录提交}"

# 选择 Amber 的 HIP 多卡引擎；启动器会按 Slurm 分配启动 8 个 MPI rank。
export ENGINE=pmemd.hip.MPI
export RUN_ROOT="$PWD/runs/dcu_multi-${SLURM_NTASKS}r"

PROFILE="${1:-pilot}"
case "$PROFILE" in
    pilot|full) ;;
    *) echo "用法：sbatch hpc/submit_dcu_multi.slurm [pilot|full]" >&2; exit 2 ;;
esac

exec bash run.sh "$PROFILE"
