#!/usr/bin/env bash
#SBATCH --job-name=cd3-dcu_multi
#SBATCH --partition=hx1hdnormal
#SBATCH --nodes=1
#SBATCH --ntasks=4
#SBATCH --cpus-per-task=16
#SBATCH --gres=dcu:4
#SBATCH --time=24:00:00
#SBATCH --output=cd3-dcu_multi-%j.out
#SBATCH --export=ALL

set +eu
cd -- "${SLURM_SUBMIT_DIR:?请从项目根目录提交}" || exit 2
job_root=$PWD
job_env_file=${SITE_ENV:-"$job_root/hpc/env_dcu_hx.sh"}
[[ $job_env_file == /* ]] || job_env_file="$job_root/$job_env_file"
[[ -r $job_env_file ]] || { echo "环境脚本不可读：$job_env_file" >&2; exit 2; }
printf '加载海光站点环境：%s\n' "$job_env_file"
if source "$job_env_file"; then
    :
else
    echo "环境脚本加载失败：$job_env_file" >&2
    exit 2
fi
cd -- "$job_root" || exit 2


export MPI_TYPE=${MPI_TYPE:-pmix_v4}
for prog in tleap sander cpptraj python3 pmemd.hip.MPI srun; do
    command -v "$prog" >/dev/null || { echo "海光环境缺少必需程序：$prog" >&2; exit 2; }
done
export SITE_ENV_LOADED="$job_env_file"
printf '环境已加载；引擎：%s；MPI：%s\n' "$(command -v pmemd.hip.MPI)" "$MPI_TYPE"
set -euo pipefail
exec bash hpc/job_runner.sh dcu_multi "${1:-${PROFILE:-pilot}}" --env-ready
