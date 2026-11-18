#!/usr/bin/env bash
# 海光 hx1hdnormal 的站点设置，依据用户提供的 Amber 示例。
# 仅适用于该站点/该架构；其他平台应通过 SITE_ENV 指定自己的环境脚本。
# 本文件供 source 使用，不要在这里启动模拟或修改设备可见编号。
module purge
source /public/home/aci37mn59u/apprepo/amber/26-dtk26.04_hx/scripts/env.sh
export HSA_FORCE_FINE_GRAIN_PCIE=1
export HIP_COMGR_ARCH=gfx936
export ROCBLAS_GPU_ARCHNAME=gfx936
export I_MPI_PMI_LIBRARY=/opt/gridview/slurm-3.1.0/lib/libpmi.so
ulimit -l unlimited
# 本站多卡示例使用 pmix_v4；其他站点不能机械复制这个值。
export MPI_TYPE=${MPI_TYPE:-pmix_v4}
