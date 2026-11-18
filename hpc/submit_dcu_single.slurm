#!/usr/bin/env bash
#SBATCH --job-name=cd3-dcu_single
#SBATCH --partition=hx1hdnormal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --gres=dcu:1
#SBATCH --time=24:00:00
#SBATCH --output=cd3-dcu_single-%j.out
#SBATCH --export=ALL

# 海光 DCU 单卡。从包含 run.sh 的项目根目录执行 sbatch。
# 多卡模板按一进程一卡；切换卡数必须同时修改 --ntasks 和 --gres。
# CHANGE_ME 必须改为该平台的真实分区；账户、CPU/卡比例和时限按站点要求设置。
# 修改环境请设置 SITE_ENV=/绝对路径/site-env.sh；DCU 默认加载 env_dcu_hx.sh。
# 不要使用 srun 启动多个 run.sh；MPI 由统一引擎启动器负责。
set -euo pipefail
cd -- "${SLURM_SUBMIT_DIR:?请从项目根目录提交}"
exec bash hpc/job_runner.sh dcu_single "${1:-${PROFILE:-pilot}}"
