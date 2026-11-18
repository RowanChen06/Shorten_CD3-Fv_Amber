#!/usr/bin/env bash
# Single-node entry point. A completed segment is reused when this command is rerun.
set -euo pipefail
cd -- "$(dirname -- "$0")"
export PYTHONDONTWRITEBYTECODE=1
mode=${1:-full}
if [[ $# -gt 1 ]]; then echo "Usage: bash run.sh [full|pilot|check|plan|analyse]" >&2; exit 2; fi
case "$mode" in
    -h|--help|help) echo "bash run.sh [full (default) | pilot | check | plan | analyse]"; exit 0 ;;
    plan) exec python3 scripts/workflow.py plan ;;
    check) ;;
    full|pilot) profile=$mode ;;
    analyse) profile=${PROFILE:-full} ;;
    *) echo "Unknown mode: $mode" >&2; exit 2 ;;
esac
if [[ $mode != analyse ]]; then
    requested=${ENGINE:-auto}
    if [[ $requested == auto ]]; then
        requested=sander
        if command -v pmemd.cuda >/dev/null && [[ -n ${CUDA_VISIBLE_DEVICES-unset} && ${CUDA_VISIBLE_DEVICES-} != -1 ]] &&
           devices=$(nvidia-smi -L 2>/dev/null) && [[ $devices == *"GPU "* ]]; then
            requested=pmemd.cuda
        fi
    fi
    if [[ $requested == */* && $requested != /* ]]; then requested="$PWD/$requested"; fi
    case $requested in
        sander.MPI|*/sander.MPI|pmemd.MPI|*/pmemd.MPI)
            export AMBER_MPI_BIN="$requested"
            export ENGINE="$PWD/hpc/amber-mpi.sh"
            "$ENGINE" --check
            ;;
        ascend)
            if [[ ${ASCEND_AMBER_BIN:-} != /* || ! -f ${ASCEND_AMBER_BIN:-} || ! -x ${ASCEND_AMBER_BIN:-} ]]; then
                echo "ENGINE=ascend requires ASCEND_AMBER_BIN=/absolute/path to a site-provided Ascend Amber-compatible engine or adapter. See ENVIRONMENT.md." >&2
                exit 2
            fi
            export ENGINE="$ASCEND_AMBER_BIN"
            echo "Dynamics: site-provided Ascend adapter $ENGINE (confirm device use in the site runtime)." >&2
            ;;
        *)
            export ENGINE="$requested"
            case ${ENGINE##*/} in
                sander|pmemd) label="CPU serial" ;;
                pmemd.cuda*) label="NVIDIA CUDA" ;;
                *) label="site executable" ;;
            esac
            echo "Dynamics: $label ($ENGINE)" >&2
            ;;
    esac
fi
if [[ $mode == check ]]; then exec python3 scripts/workflow.py check; fi
export PROFILE=$profile
export RUN_ROOT=${RUN_ROOT:-"$PWD/runs"}
work="$RUN_ROOT/$profile"
mkdir -p -- "$work"
# flock releases the lock on exit, including scheduler termination.
exec 9>"$work/.writer.lock"
flock -n 9 || { echo "An active job is using $work" >&2; exit 1; }
if [[ $mode == analyse ]]; then export ANALYSIS_ONLY=1; fi
python3 scripts/workflow.py prepare
if [[ $mode != analyse ]]; then
    python3 scripts/workflow.py build
    python3 scripts/workflow.py minimize
    replicas=$(python3 scripts/workflow.py replicas)
    for ((rep=1; rep<=replicas; rep++)); do
        python3 scripts/workflow.py equilibrate "$rep"
        python3 scripts/workflow.py produce "$rep"
    done
fi
python3 scripts/workflow.py analyse
printf 'Results: %s/summary\n' "$work"
