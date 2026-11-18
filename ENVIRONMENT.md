# 环境要求与部署

## 软件要求

| 用途 | 要求 |
|---|---|
| 主流程 | Linux、Bash、Python 3.10+；建议环境文件中的 Python 3.11 |
| 文件锁 | util-linux 提供的 flock；共享结果盘应支持文件锁和目录重命名 |
| 建模/最小化/分析 | AmberTools 的 tleap、sander、cpptraj |
| Python 分析 | NumPy、SciPy、ParmEd、netCDF4、Matplotlib |
| CPU MPI | sander.MPI 或 pmemd.MPI，以及同一构建配套的 MPI 运行时 |
| NVIDIA 单卡/多卡 | pmemd.cuda / pmemd.cuda.MPI，兼容的 NVIDIA 驱动和 CUDA 库 |
| 海光 DCU 单卡/多卡 | 平台适配的 pmemd.hip / pmemd.hip.MPI，兼容 DTK 和驱动 |
| 其他 HIP 平台 | 对该设备编译的 pmemd.hip / pmemd.hip.MPI，兼容 HIP/ROCm 与站点 MPI |
| 调度 | 随包模板为单节点 Slurm；其他调度器需自行适配资源申请 |

本包只提供输入和工作流，不含 Amber 可执行程序、驱动或许可证。所需引擎必须由平台提供或在允许的环境中安装。安装 Conda AmberTools 不等于已经安装 GPU/DCU 版 PMEMD。其他品牌加速卡和昇腾 NPU 不能仅换名字使用这些模板。

## 海光 hx1hdnormal 的已知配置

`hpc/env_dcu_hx.sh` 保存用户示例中的内容；单卡和多卡提交模板会在计算节点、开启 Bash 严格模式前各自加载一次，并检查必需可执行文件：

```bash
module purge
source /public/home/aci37mn59u/apprepo/amber/26-dtk26.04_hx/scripts/env.sh
export HSA_FORCE_FINE_GRAIN_PCIE=1
export HIP_COMGR_ARCH=gfx936
export ROCBLAS_GPU_ARCHNAME=gfx936
export I_MPI_PMI_LIBRARY=/opt/gridview/slurm-3.1.0/lib/libpmi.so
ulimit -l unlimited
export MPI_TYPE=pmix_v4
```

此配置是站点专用信息，不能推断为所有海光卡或所有 HIP 平台通用要求。单卡用 pmemd.hip，多卡用 srun --mpi=pmix_v4 ... pmemd.hip.MPI；多卡模板默认 4 卡。若 ulimit 或环境加载失败，应查看原错误并按平台说明处理，不能将失败当作成功继续运行。

## Python/AmberTools 依赖

先检查平台环境是否已经齐全。在加载所需环境后运行：

```bash
command -v tleap sander cpptraj python3
python3 -c 'import numpy, scipy, parmed, netCDF4, matplotlib; print("Python dependencies OK")'
```

若平台没有分析依赖，可在允许安装软件的环境中使用：

```bash
conda env create -f environment/environment.yml
conda activate cd3-md
```

然后按站点要求加载 GPU/DCU 引擎。Conda、Amber 自带 Python 和站点模块可能改变 PATH 或动态库搜索路径；最终必须在实际作业环境中运行 check，确认真实程序路径和依赖都正确。不要同时盲目叠加不同 DTK、CUDA 或 MPI 版本。当前工作流用 PATH 中的 python3。

需要持久化环境初始化时，创建自己的 site-env.sh，里面写入本机真实的 Conda 初始化/激活命令和站点 Amber 环境加载命令；用绝对路径通过 SITE_ENV 传入。DCU 使用自定义 SITE_ENV 后会替代默认 env_dcu_hx.sh，需在自定义脚本中 source 它或完整配置同等环境。

## NVIDIA、其他 HIP 与 CPU 平台

这三类模板的分区为 CHANGE_ME，需要替换。加载的软件模块名、srun 的 MPI_TYPE、卡资源名称、账户和设备绑定均由站点确定。可在登录终端先加载环境，再用默认 --export=ALL 提交；更可复现的做法是使用 SITE_ENV：

```bash
export SITE_ENV=/你的绝对路径/site-env.sh
sbatch --partition=实际分区 hpc/submit_nvidia_multi.slurm pilot
```

MPI_LAUNCHER 支持 srun、mpirun、mpiexec。本包未内置跨节点通信/绑定方案，多卡模板均 --nodes=1。单卡/串行模板要求 --ntasks=1。分配 16 个 CPU 配额不表示串行 sander 会自动使用 16 核，最小化仍为串行设计。

GPU/DCU 的可见设备与 rank 绑定优先遵循站点示例和调度器，不统一写死设备 0。通用 HIP 多卡模板可能需要站点特定的逐 rank 绑定；LUMI 等平台的设置不能直接复制到海光。

## 真实试跑与性能

check 只检查程序和依赖，不执行模拟、不确认卡占用。pilot 在分配的计算节点运行，检查：

1. 环境记录中的真实引擎、MPI 和站点路径。
2. 最小化几何、温度、密度、轨迹帧数和重启文件。
3. 引擎日志/平台监控中的设备使用与 ns/day。
4. 续跑是否从完整段边界恢复；分析是否生成完整输出。

多卡加速先比较单卡/双卡/四卡。默认 pilot 的生产仅 200 ps，用于启动及粗略性能筛查；精确效率测试应使用相同含水拓扑、坐标、参数和足够长的生产段。一个重复的预计生产天数约 100/ns_per_day，顺序三个约 300/ns_per_day，不含其他阶段与排队。

## 存储和结果管理

所有输出写入 RUN_ROOT/full 或 RUN_ROOT/pilot。保留含水 wet.nc、配套 system.parm7、重启文件、日志和输入；去水轨迹不能替代界面水分析所需的原始含水轨迹。

坐标轨迹的未压缩量级约为 原子数 × 12 字节 × 帧数。full 生产共 30,000 帧；若实际体系约 60,000 原子，则仅生产坐标约 21.6 GB，另留平衡、分析、检查点和临时空间。实际原子数由建模决定；以 pilot 测得占用为准。

同目录不可并发两个主流程。作业时限需覆盖至少一个生产段；未完成的 5 ns 段会重算。修改协议、代码或输入会触发指纹检查，应使用新 RUN_ROOT。不同平台部署应记录环境版本；本包 environment.jsonl 会保存部分版本、路径及启动器校验和。

参考：[AmberTools](https://ambermd.org/AmberTools.php)、[CSC Amber CPU/CUDA/HIP](https://docs.csc.fi/apps/amber/)、[超算互联网 Amber 示例](https://www.scnet.cn/help/docs/mainsite/hpc/software-examples/use/science/Amber/index.html)、[Slurm](https://slurm.schedmd.com/srun.html)。
