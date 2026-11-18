# 提交脚本与引擎启动说明

## 调用关系

每个 `submit_*.slurm` 只调用一次 `job_runner.sh`。海光模板先在计算节点加载 `env_dcu_hx.sh`，再由 `job_runner.sh` 启动一次 `run.sh`；其他后端可由 `job_runner.sh` 加载 `SITE_ENV`。`run.sh` 通过 `configure_engine.sh` 解析引擎，在每个动力学阶段调用 `launch_engine.sh`。单卡/单进程直接 exec 真实引擎；多卡/多进程由启动器调用一次 MPI 步骤。整个 Python/Bash 工作流不会被复制到每张卡。

## 模板差异

- `submit_dcu_single.slurm` / `submit_dcu_multi.slurm`：已填海光队列，每次提交在计算节点加载 `env_dcu_hx.sh`，检查必需程序，再使用 HIP 引擎。
- `submit_nvidia_single.slurm` / `submit_nvidia_multi.slurm`：使用 CUDA 引擎，分区和环境需按 NVIDIA 站点填写。
- `submit_hip_single.slurm` / `submit_hip_multi.slurm`：供其他已部署 Amber HIP 的站点使用；未预设海光架构变量，资源名称和卡绑定需按站点适配。
- `submit_cpu_serial.slurm` / `submit_cpu_mpi.slurm`：不申请加速卡；默认使用 sander / sander.MPI。可设置 ENGINE_BIN=pmemd 或 pmemd.MPI 切换对应 CPU 引擎。

各模板默认运行 pilot。参数 full 启动正式模拟；analyse/analyze 只做分析；check 只检查环境。分析默认 full，可用 ANALYSIS_PROFILE=pilot 选择短测试。

## 环境变量

| 变量 | 作用 |
|---|---|
| SITE_ENV | 需要 source 的站点脚本。海光提交模板默认 env_dcu_hx.sh（可覆盖）；其他模板不设置时继承提交环境 |
| ENGINE_BIN | 提交模板中的真实引擎名称/路径覆盖；必须与模板类别和 MPI 模式一致 |
| ENGINE | 手动调用 run.sh 时的真实引擎名称/路径；模板会主动选择，不沿用旧 ENGINE |
| MPI_LAUNCHER | srun、mpirun 或 mpiexec，可为绝对路径；Slurm 作业默认 srun |
| MPI_TYPE | srun 的 --mpi 值；海光默认 pmix_v4，其他站点未预设 |
| MPI_RANKS | 手动运行时的进程数；默认 SLURM_NTASKS，不能超过 Slurm 分配 |
| RUN_ROOT | 持久输出根目录，不包含末尾的 full/pilot |
| PROFILE | 不传脚本位置参数时选择模式；位置参数优先 |
| ANALYSIS_PROFILE | 模板 analyse 时选择 full/pilot，默认 full |
| AMBER_ALLOW_SMALL_BOX | 默认 0；明确设置 1 才向 GPU/DCU 引擎传入 -AllowSmallBox |
| OMP_NUM_THREADS | 默认 1；不把 CPU 配额误当成所需 OpenMP 线程数 |

ENGINE/ENGINE_BIN 只接收单个可执行文件名称或路径，不能写成 `srun -n 4 pmemd.hip.MPI`。所有参数用数组传递，路径中的空格会保留。

MPI 模板按一进程一卡设置；切换卡数必须同步修改 --ntasks 和 --gres。本包能检查进程数和已知模板配置，并在有 SLURM_GPUS_ON_NODE 时检查 CUDA 卡数；不是所有 DCU 站点都会暴露卡数环境变量，实际卡数/绑定仍需结合分配信息和运行日志核实。

## 改卡数和继续运行

海光多卡模板默认 4 卡，可在 sbatch 中覆盖：

```bash
sbatch --ntasks=2 --gres=dcu:2 hpc/submit_dcu_multi.slurm pilot
```

同一种模板和进程数的默认 RUN_ROOT 固定，重提同一命令可以续跑。不同卡数默认不同目录。若需要换卡数继续同一条轨迹，先确认原作业已退出、引擎和软件版本兼容，再显式指定原 RUN_ROOT；不得同时写入同一目录。跨硬件/精度结果的浮点轨迹不保证逐帧相同。

不要把 `run.sh` 整体交给多进程 srun，也不要用 job array 直接启动三份相同 full。当前版本没有“每张卡各跑一个重复”的并发实现。

## 站点绑定

本海光模板保持用户示例的启动方法，未自行覆盖 HIP/CUDA/ROCR_VISIBLE_DEVICES。对于其他 HIP 平台，卡可能按逻辑设备/GCD 计数，MPI 与 CPU/设备亲和性也可能不同；须采用该站点提供的绑定方式。本模板不保证任意 AMD/国产硬件无需适配即可运行。

参考：[Slurm sbatch](https://slurm.schedmd.com/sbatch.html)、[Slurm srun](https://slurm.schedmd.com/srun.html)、[Amber HIP/CUDA 和多卡扩展性](https://docs.csc.fi/apps/amber/)。
