#!/usr/bin/env bash
# 供 run.sh source：识别真实引擎，并将统一启动器传给 Python。
# ENGINE 只能是一个可执行文件的名称或路径，不能包含 srun 命令和参数。
configure_engine() {
    local requested=${ENGINE:-} name resolved
    if [[ -z $requested || $requested == auto ]]; then
        echo "请显式选择 ENGINE（如 sander、sander.MPI、pmemd.cuda、pmemd.cuda.MPI、pmemd.hip、pmemd.hip.MPI），或使用 hpc/submit_*.slurm。不会自动回退 CPU。" >&2
        return 2
    fi
    resolved=$(command -v -- "$requested") || {
        echo "找不到引擎：$requested。请先加载对应软件环境。ENGINE 不能包含启动参数。" >&2
        return 2
    }
    [[ $resolved == /* ]] || resolved="$PWD/$resolved"
    [[ -f $resolved && -x $resolved ]] || { echo "引擎必须是可执行文件：$resolved" >&2; return 2; }
    name=${resolved##*/}
    case "$name" in
        sander|pmemd|sander.MPI|pmemd.MPI) export AMBER_ENGINE_FAMILY=cpu ;;
        pmemd.cuda|pmemd.cuda.MPI|pmemd.cuda_DPFP|pmemd.cuda_DPFP.MPI) export AMBER_ENGINE_FAMILY=cuda ;;
        pmemd.hip|pmemd.hip.MPI|pmemd.hip_DPFP|pmemd.hip_DPFP.MPI) export AMBER_ENGINE_FAMILY=hip ;;
        *) echo "未识别的引擎名称：$name。本包内置支持标准 Amber CPU/CUDA/HIP 可执行文件。" >&2; return 2 ;;
    esac
    case "$name" in *.MPI) export AMBER_USE_MPI=1 ;; *) export AMBER_USE_MPI=0 ;; esac
    # 提交模板与引擎类别必须匹配，防止继承了旧环境变量后跑错后端。
    if [[ -n ${EXPECTED_ENGINE_FAMILY:-} && $AMBER_ENGINE_FAMILY != "$EXPECTED_ENGINE_FAMILY" ]]; then
        echo "模板要求 $EXPECTED_ENGINE_FAMILY，但引擎属于 $AMBER_ENGINE_FAMILY。" >&2; return 2
    fi
    if [[ -n ${EXPECTED_MPI_MODE:-} && $AMBER_USE_MPI != "$EXPECTED_MPI_MODE" ]]; then
        echo "模板的单进程/MPI 模式与引擎不一致。" >&2; return 2
    fi
    export AMBER_ENGINE_REQUESTED="$requested"
    export AMBER_ENGINE_BIN="$resolved"
    export ENGINE="$PWD/hpc/launch_engine.sh"
    "$ENGINE" --check
}
