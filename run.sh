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
    check) exec python3 scripts/workflow.py check ;;
    full|pilot) profile=$mode ;;
    analyse) profile=${PROFILE:-full} ;;
    *) echo "Unknown mode: $mode" >&2; exit 2 ;;
esac
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
