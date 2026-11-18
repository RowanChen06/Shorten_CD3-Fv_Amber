#!/usr/bin/env bash
# 中文说明：这是整个模拟的唯一主入口；多卡时也只启动本脚本一份。
# MPI 只作用于每个 Amber 动力学步骤，由 hpc/launch_engine.sh 负责。
set -euo pipefail
cd -- "$(dirname -- "$0")"
export PYTHONDONTWRITEBYTECODE=1
mode=${1:-full}
if [[ $# -gt 1 ]]; then echo "用法：bash run.sh [full|pilot|check|plan|analyse]" >&2; exit 2; fi
case "$mode" in
    -h|--help|help) echo "bash run.sh [full|pilot|check|plan|analyse]；动力学需显式设置 ENGINE，见 README.md。"; exit 0 ;;
    plan) exec python3 scripts/workflow.py plan ;;
    check) ;;
    full|pilot) profile=$mode ;;
    analyse|analyze) mode=analyse; profile=${PROFILE:-full} ;;
    *) echo "未知模式：$mode" >&2; exit 2 ;;
esac

# 禁止按 nvidia-smi 是否存在来静默回退 CPU；设备由用户/提交模板明确选择。
if [[ $mode != analyse ]]; then
    source hpc/configure_engine.sh
    configure_engine
fi
if [[ $mode == check ]]; then exec python3 scripts/workflow.py check; fi
export PROFILE=$profile
export RUN_ROOT=${RUN_ROOT:-"$PWD/runs/manual"}
work="$RUN_ROOT/$profile"
mkdir -p -- "$work"

# 同一输出目录只能有一个主流程写入；锁在进程退出或作业终止后自动释放。
exec 9>"$work/.writer.lock"
flock -n 9 || { echo "已有作业正在写入 $work" >&2; exit 1; }
if [[ $mode == analyse ]]; then export ANALYSIS_ONLY=1; else unset ANALYSIS_ONLY || true; fi
python3 scripts/workflow.py prepare
if [[ $mode != analyse ]]; then
    python3 scripts/workflow.py build
    python3 scripts/workflow.py minimize
    replicas=$(python3 scripts/workflow.py replicas)
    # 独立重复依次运行；多卡共同计算当前重复，不是多个重复同时运行。
    for ((rep=1; rep<=replicas; rep++)); do
        python3 scripts/workflow.py equilibrate "$rep"
        python3 scripts/workflow.py produce "$rep"
    done
fi
python3 scripts/workflow.py analyse
printf '结果目录：%s/summary\n' "$work"
