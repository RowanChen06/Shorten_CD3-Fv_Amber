#!/bin/bash
#SBATCH -J cd3_dcu
#SBATCH -p hx1hdnormal
#SBATCH -N 1
#SBATCH --ntasks-per-node=8
#SBATCH -c 16
#SBATCH --gres=dcu:8
#SBATCH --time=24:00:00
#SBATCH -o slurm-%j.out

# 加载平台环境，与提供的 Amber 示例一致
# 环境初始化期间不因可选 hipcc 探测失败而提前退出
set +eu
module purge
source /public/home/aci37mn59u/apprepo/amber/26-dtk26.04_hx/scripts/env.sh

# 保存平台 MPI 的位置，避免 Conda 中的同名命令遮蔽它
PLATFORM_MPIRUN="$(command -v mpirun)"
if [[ -z "$PLATFORM_MPIRUN" ]]; then
    echo "ERROR: 平台环境未提供 mpirun" >&2
    exit 1
fi
PLATFORM_MPI_BIN="$(dirname "$PLATFORM_MPIRUN")"

# 初始化并激活已有 AmberTools 环境
if ! command -v conda >/dev/null 2>&1; then
    echo "ERROR: 批处理环境找不到 conda。请先在登录节点执行 conda info --base，确认安装位置。" >&2
    exit 1
fi

CONDA_BASE="$(conda info --base)" || exit 1
source "$CONDA_BASE/etc/profile.d/conda.sh" || exit 1
conda activate ambertools-25 || exit 1

# 保持平台 MPI 命令优先
export PATH="$PLATFORM_MPI_BIN:$PATH"

export HSA_FORCE_FINE_GRAIN_PCIE=1
export HIP_COMGR_ARCH=gfx936
export ROCBLAS_GPU_ARCHNAME=gfx936
export I_MPI_PMI_LIBRARY=/opt/gridview/slurm-3.1.0/lib/libpmi.so
ulimit -l unlimited

# 环境加载后，遇到工作流错误立即停止
set -euo pipefail
echo "===== AmberTools dependency check ====="
echo "CONDA_PREFIX=${CONDA_PREFIX:-unset}"
echo "AMBERHOME=${AMBERHOME:-unset}"

for cmd in python tleap sander cpptraj mpirun srun; do
    command -v "$cmd" || {
        echo "ERROR: missing command: $cmd" >&2
        exit 1
    }
done

python - <<'PY'
import sys
import parmed
import netCDF4

print("Python:", sys.executable)
print("ParmEd:", parmed.__file__)
print("netCDF4:", netCDF4.__file__)
PY

# 进入你的模拟项目
cd /public/home/aci37mn59u/CYX/Shorten_CD3-Fv_Amber_git

# 告诉项目内部启动器使用 HIP 多卡引擎
export ENGINE=/public/home/aci37mn59u/apprepo/amber/26-dtk26.04_hx/app/bin/pmemd.hip.MPI
export MPI_LAUNCHER=srun
export MPI_TYPE=pmix_v4
export MPI_RANKS="$SLURM_NTASKS"
export OMP_NUM_THREADS=1

# 结果根目录；run.sh 会自动建立 full 子目录
export RUN_ROOT="$PWD/runs/dcu_multi-${SLURM_NTASKS}r"

# 项目内部需要直接执行这个启动器
chmod +x hpc/launch_engine.sh

# 一次启动完整流程：
# 准备 → 建模 → 最小化 → 升温 → 平衡 → 生产 → 分析
exec bash run.sh full
