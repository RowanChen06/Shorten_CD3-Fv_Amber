#!/usr/bin/env bash
# 所有动力学阶段共用此入口；使用 Bash 数组和 "$@"，保留带空格的路径。
# 本文件不能通过 srun 再启动多份；它自身负责启动一次 MPI 作业步骤。
set -euo pipefail
engine=${AMBER_ENGINE_BIN:?请通过 run.sh 配置引擎}
family=${AMBER_ENGINE_FAMILY:?缺少引擎类别}
mpi=${AMBER_USE_MPI:?缺少 MPI 模式}
[[ -f $engine && -x $engine ]] || { echo "引擎不可执行：$engine" >&2; exit 2; }
extra=()
case ${AMBER_ALLOW_SMALL_BOX:-0} in
    0) ;;
    1)
        [[ $family != cpu ]] || { echo "CPU 引擎不使用 -AllowSmallBox。" >&2; exit 2; }
        extra+=(-AllowSmallBox)
        ;;
    *) echo "AMBER_ALLOW_SMALL_BOX 只能是 0 或 1。" >&2; exit 2 ;;
esac

cmd=()
if [[ $mpi == 1 ]]; then
    ranks=${MPI_RANKS:-${SLURM_NTASKS:-}}
    [[ $ranks =~ ^[1-9][0-9]*$ ]] || { echo "MPI 需要有效 MPI_RANKS 或 SLURM_NTASKS。" >&2; exit 2; }
    if [[ ${SLURM_NTASKS:-} =~ ^[1-9][0-9]*$ ]] && (( ranks > SLURM_NTASKS )); then
        echo "MPI 进程数超过 Slurm 分配：$ranks > $SLURM_NTASKS" >&2; exit 2
    fi
    # GPU/DCU 模板按一进程一卡运行，禁止只启动少量 rank 而闲置已申请的卡。
    if [[ $family != cpu && -n ${EXPECTED_ACCELERATORS:-} && $ranks != "$EXPECTED_ACCELERATORS" ]]; then
        echo "MPI 进程数应与本模板的卡数一致：$ranks / $EXPECTED_ACCELERATORS" >&2; exit 2
    fi
    if [[ -n ${SLURM_JOB_ID:-} ]]; then default_launcher=srun; else default_launcher=mpiexec; fi
    launcher=${MPI_LAUNCHER:-$default_launcher}
    command -v -- "$launcher" >/dev/null || { echo "找不到 MPI 启动器：$launcher" >&2; exit 2; }
    case ${launcher##*/} in
        srun)
            [[ -n ${SLURM_JOB_ID:-} ]] || { echo "srun 需要已分配的 Slurm 作业。" >&2; exit 2; }
            cpus=${SLURM_CPUS_PER_TASK:-1}
            [[ $cpus =~ ^[1-9][0-9]*$ ]] || { echo "无效 SLURM_CPUS_PER_TASK" >&2; exit 2; }
            cmd=("$launcher" --ntasks="$ranks" --cpus-per-task="$cpus" --kill-on-bad-exit=1)
            [[ -z ${MPI_TYPE:-} ]] || cmd+=(--mpi="$MPI_TYPE")
            ;;
        mpirun|mpiexec) cmd=("$launcher" -n "$ranks") ;;
        *) echo "MPI_LAUNCHER 仅支持 srun、mpirun 或 mpiexec 的名称/路径。" >&2; exit 2 ;;
    esac
elif [[ $mpi != 0 ]]; then
    echo "AMBER_USE_MPI 只能是 0 或 1。" >&2; exit 2
fi
cmd+=("$engine" "${extra[@]}")
if [[ ${1:-} == --check ]]; then
    printf 'Dynamics: family=%s MPI=%s command=' "$family" "$mpi" >&2
    printf '%q ' "${cmd[@]}" >&2
    printf '\n' >&2
    exit 0
fi
exec "${cmd[@]}" "$@"
