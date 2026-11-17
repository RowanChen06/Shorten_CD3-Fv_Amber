# 环境要求和平台配置

## 在哪里运行

使用 Linux 计算节点和 Bash，模型与输出位于计算节点可见、支持文件锁及目录重命名的持久文件系统。WSL2 也可用于准备输入或 CPU 短测试。使用 SSH 别名 ZK_Sugon 登录后，先看所在分区的加速卡类型、作业墙钟时间及软件模块。曙光平台不同分区可能有不同的硬件与调度配置；本包没有预设你的分区、计费账户或模块名称。

| 用途 | 程序或环境 | 如何核对 |
|---|---|---|
| 启动、续跑 | Bash、Linux util-linux 的 flock、Python 3.11 建议环境 | `command -v bash flock python3` |
| 构建与最小化 | AmberTools 的 tleap 和 CPU sander；安装内含 ff14SB、TIP3P 与相应离子参数 | `command -v tleap sander` |
| GPU 动力学 | NVIDIA 计算节点、站点兼容的驱动和已编译的 Amber pmemd.cuda | 在实际 GPU 作业中执行 `nvidia-smi` 和 `command -v pmemd.cuda`，再运行 pilot |
| CPU 动力学 | 单进程 sander；可用于没有兼容 GPU 的节点 | `ENGINE=sander bash run.sh check` |
| 轨迹与统计 | cpptraj；Python 的 ParmEd、NumPy、SciPy、netCDF4、Matplotlib | `bash run.sh check` |
| 作业提交 | 随包示例使用 Slurm；有其他调度器时，让站点批作业调用同一 run.sh | `command -v sbatch` |

## 方案 A：平台已有模块

```bash
module avail amber
module list
```

加载管理员提供的 AmberTools、Python 分析环境；如选择 NVIDIA GPU，再加载站点支持的 Amber GPU 模块。在同一个 shell 中执行 `bash run.sh check`。留意 `command -v tleap sander cpptraj pmemd.cuda` 的路径，避免混用冲突的 NetCDF、MPI 或 CUDA 动态库。

## 方案 B：用 Conda 安装 CPU 准备与分析环境

在允许安装软件的登录环境进入项目根目录，执行：

```bash
conda env create -f environment/environment.yml
conda activate cd3-md
bash run.sh check
```

环境文件是可求解的版本范围。每次任务记录实际 Python、包版本、计算机名、可执行程序路径及已加载模块。如需在同架构重建首次成功的环境，可另存精确的软件清单：

```bash
conda list --explicit > conda-linux-explicit.txt
```

GPU 程序由站点单独提供。仅安装上述 Conda 环境可使用 CPU 路径。若平台提供非 NVIDIA 加速卡，仅在管理员确认该引擎和运行时兼容本流程并通过 pilot 后使用；通用回退路径为 CPU。单一 ENGINE 值应为一个可执行程序名称或路径。

## Slurm 和工作目录

在包根目录、已激活环境下提交。以下示例以 NVIDIA GPU 为例。按站点要求在 sbatch 命令中添加实际的 `--partition`、`--account`、GPU 资源语法和墙钟时间。已有 GPU 交互分配时可以直接执行 run.sh。

```bash
sbatch --export=ALL,PROFILE=pilot hpc/submit.slurm
# 短任务完成并检查结果后，提交正式任务
sbatch --export=ALL,PROFILE=full hpc/submit.slurm
```

若该站点的非交互作业需要重新加载模块或激活 Conda，可自备一个 Bash 环境片段，填写站点的 module load 或 conda 初始化命令，提交时传入 `SITE_ENV=/你的绝对路径/site-env.sh`。模板默认申请 1 个节点、1 块 GPU、4 个 CPU 核、24 小时；没有 GPU 的分区用平台 CPU 作业模板调用 `ENGINE=sander bash run.sh pilot`。本包一次在一台节点上依次跑重复。到时限后再次提交同一命令即可从完成段边界恢复。

## 时间与磁盘怎样估算

先用 pilot 记录实际 ns/day，再按正式生产总量 300 ns 估算。顺序单卡生产时长约为 300 除以实测 ns/day，再加最小化、平衡、排队与分析时间。正式每 5 ns 提交一次段结果；若 5 ns 超过单作业时间，应在启动新正式目录前缩短 segment_ns，并相应增加 segments 以维持每重复 100 ns。平衡阶段也应在单次墙钟限额内完成。

未压缩含水坐标的量级约为 总原子数 × 12 字节 × 保存帧数。正式默认 30,000 个生产帧。举例，若实际建模得到 60,000 个原子，仅生产含水坐标约 21.6 GB，另需预留平衡轨迹、蛋白轨迹、检查点、临时分析与备份空间。先读 build/geometry.txt 的原子数。设置 RUN_ROOT 可指定共享工作盘的绝对路径，续跑时保持一致。时间和磁盘示例均为估算，实际数值以本节点 pilot 为准。

参考：[AmberTools 软件包](https://anaconda.org/conda-forge/ambertools) · [集群 Amber 运行示例](https://docs.cscs.ch/software/userapps/amber/)
