#!/usr/bin/env bash
# 各 Slurm 模板共用的作业主体：只启动一个主流程，不把 run.sh 放进多进程 srun。
set -eo pipefail
job_variant=${1:?缺少模板类型}
job_profile=${2:-${PROFILE:-pilot}}
case "$job_profile" in pilot|full|analyse|analyze|check) ;; *) echo "不支持的模式：$job_profile" >&2; exit 2 ;; esac
: "${SLURM_JOB_ID:?请使用 sbatch 提交模板}"
cd -- "${SLURM_SUBMIT_DIR:?请从包含 run.sh 的项目根目录提交}"
[[ -f run.sh && -f config/protocol.json ]] || { echo "提交目录不是项目根目录。" >&2; exit 2; }
job_root=$PWD
case "$job_variant" in
    cpu_serial) job_default_engine=sander; job_family=cpu; job_mpi=0 ;;
    cpu_mpi) job_default_engine=sander.MPI; job_family=cpu; job_mpi=1 ;;
    nvidia_single) job_default_engine=pmemd.cuda; job_family=cuda; job_mpi=0 ;;
    nvidia_multi) job_default_engine=pmemd.cuda.MPI; job_family=cuda; job_mpi=1 ;;
    dcu_single|hip_single) job_default_engine=pmemd.hip; job_family=hip; job_mpi=0 ;;
    dcu_multi|hip_multi) job_default_engine=pmemd.hip.MPI; job_family=hip; job_mpi=1 ;;
    *) echo "未知模板类型：$job_variant" >&2; exit 2 ;;
esac

# 站点环境脚本先加载，之后再开启 nounset，兼容厂商初始化脚本中的可选变量。
job_env_file=${SITE_ENV:-}
if [[ $job_variant == dcu_* && -z $job_env_file ]]; then job_env_file="$job_root/hpc/env_dcu_hx.sh"; fi
if [[ -n $job_env_file ]]; then
    [[ $job_env_file == /* ]] || job_env_file="$job_root/$job_env_file"
    [[ -r $job_env_file ]] || { echo "环境脚本不可读：$job_env_file" >&2; exit 2; }
    source "$job_env_file"
    # 厂商环境可能改变工作目录，随后恢复项目根目录。
    cd -- "$job_root"
fi
set -euo pipefail
export SITE_ENV_LOADED="$job_env_file"
export JOB_VARIANT="$job_variant"
export EXPECTED_ENGINE_FAMILY="$job_family"
export EXPECTED_MPI_MODE="$job_mpi"
job_ranks=${SLURM_NTASKS:-1}
[[ $job_ranks =~ ^[1-9][0-9]*$ ]] || { echo "无效 Slurm 任务数。" >&2; exit 2; }
if [[ $job_mpi == 0 && $job_ranks != 1 ]]; then
    echo "单进程/单卡模板需要 --ntasks=1；多卡请使用 multi 模板。" >&2; exit 2
fi
if [[ $job_family != cpu ]]; then
    export EXPECTED_ACCELERATORS="$job_ranks"
    # CUDA 的部分 Slurm 部署提供此数值；DCU 设备信息仍以站点日志/监控核实。
    if [[ $job_family == cuda && ${SLURM_GPUS_ON_NODE:-} =~ ^[0-9]+$ && $SLURM_GPUS_ON_NODE != "$job_ranks" ]]; then
        echo "申请的 GPU 数与 MPI 任务数不一致。" >&2; exit 2
    fi
else
    unset EXPECTED_ACCELERATORS || true
fi
# 模板主动选择正确引擎，忽略登录环境遗留的 ENGINE；用 ENGINE_BIN 显式覆盖路径。
export ENGINE=${ENGINE_BIN:-$job_default_engine}
export PROFILE="$job_profile"
if [[ $job_profile == analyse || $job_profile == analyze || $job_profile == check ]]; then
    # 分析默认针对正式轨迹；分析 pilot 请设置 ANALYSIS_PROFILE=pilot。
    export PROFILE=${ANALYSIS_PROFILE:-full}
fi
export RUN_ROOT=${RUN_ROOT:-"$job_root/runs/$job_variant-${job_ranks}r"}
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-1}
export PYTHONUNBUFFERED=1
printf 'Job=%s Host=%s Variant=%s Tasks=%s Mode=%s\n' "$SLURM_JOB_ID" "$(hostname)" "$job_variant" "$job_ranks" "$job_profile"
printf 'ENGINE=%s RUN_ROOT=%s\n' "$ENGINE" "$RUN_ROOT"
if [[ $job_profile != analyse && $job_profile != analyze && $job_profile != check ]]; then bash run.sh check; fi
exec bash run.sh "$job_profile"
