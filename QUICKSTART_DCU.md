# 海光 DCU：从四卡试跑开始

适用已知站点：`hx1hdnormal`，平台 Amber 示例为 `26-dtk26.04_hx`。`hpc/env_dcu_hx.sh` 已写入用户提供的绝对路径和环境变量；若平台迁移安装位置，修改该文件。不要把这个文件直接用于 NVIDIA 或其他 HIP 架构。

## 1. 上传并解压

将 CD3_Fv_Amber_MultiBackend.zip 上传到计算节点可见的共享目录，在登录节点执行：

```bash
unzip CD3_Fv_Amber_MultiBackend.zip
cd cd3_amber_multibackend
chmod +x run.sh hpc/*.sh
bash run.sh plan
```

包内所有代码使用 UTF-8、Linux LF 换行。不要把脚本保存为 Word 文件。

## 2. 提交四卡短测试

```bash
sbatch hpc/submit_dcu_multi.slurm pilot
```

默认 1 节点、4 DCU、4 MPI 进程、每进程 16 CPU 配额、24 小时。`job_runner.sh` 加载环境并执行 check，然后依次建模、CPU 最小化、四卡升温/平衡/生产、CPU 分析。每次动力学调用由 `srun --mpi=pmix_v4 ... pmemd.hip.MPI` 启动。

返回 `Submitted batch job 数字` 后，这个数字就是作业号。将下面示例的 123456 替换为实际作业号：

```bash
squeue -j 123456
tail -n 80 cd3-dcu_multi-123456.out
```

作业运行期间或结束后查看：

| 文件/位置 | 核对内容 |
|---|---|
| 作业日志 Dynamics 行 | family=hip、MPI=1、srun、pmix_v4、4 个 rank、真实 pmemd.hip.MPI 路径 |
| runs/dcu_multi-4r/pilot/min_free/geometry.txt | 六对二硫键及链间碰撞自动筛查 |
| runs/dcu_multi-4r/pilot/rep01/prod001/md.out | 设备/引擎信息、完成状态、ns/day |
| runs/dcu_multi-4r/pilot/summary/traces.png | 分析是否完成与指标是否异常 |
| 平台作业监控/设备工具 | 申请的卡是否实际参与计算，不能仅凭 check 通过判断 |

如果某阶段失败，日志可能仍在相应 `.partial` 目录。例如 `rep01/heat.partial/console.log`。最小化仍使用单进程 sander，该阶段卡空闲符合当前设计。

## 3. 短测试通过后提交正式任务

```bash
sbatch hpc/submit_dcu_multi.slurm full
```

正式结果：`runs/dcu_multi-4r/full/`。三个独立重复顺序完成，每个重复由四张卡共同计算，最终仍是 3 条 100 ns 轨迹。24 小时只是单次作业时限，不能保证一次完成所有模拟。超时后重提同一条命令，已完成段自动核验并跳过，中断段重算。

## 4. 切换单卡或其他卡数

```bash
# 单卡使用非 MPI 引擎 pmemd.hip
sbatch hpc/submit_dcu_single.slurm pilot

# 双卡/八卡同时覆盖任务数和资源数
sbatch --ntasks=2 --gres=dcu:2 hpc/submit_dcu_multi.slurm pilot
sbatch --ntasks=8 --gres=dcu:8 hpc/submit_dcu_multi.slurm pilot
```

输出分别在 `runs/dcu_single-1r/pilot`、`runs/dcu_multi-2r/pilot`、`runs/dcu_multi-8r/pilot`。不同目录防止性能测试直接复用旧完成段而没有实际运行。比较相同生产段的 ns/day；不同测试默认会分别建模，因此这是一轮运行效率筛查，严格数值对照应使用相同的含水拓扑和初始坐标。

多卡性能应实测。速度为 v_N（ns/day）时，一条 100 ns 轨迹的理想生产耗时约为 100/v_N 天，顺序三条约 300/v_N 天，还需计入建模、平衡、分析和排队。N 张卡的资源效率可用 v_N/(N*v_1) 比较。

## 5. 单独重新分析

full 正常结束已自动分析。若需再分析，不必重新占用四张 DCU，可用 CPU 模板并指定原结果根目录（CPU 分区需替换为实际值）：

```bash
export RUN_ROOT="$PWD/runs/dcu_multi-4r"
export ANALYSIS_PROFILE=full
sbatch --partition=实际CPU分区 hpc/submit_cpu_serial.slurm analyse
```

这个命令只读取已有轨迹。CPU 作业也需要配置 cpptraj 和 Python 依赖，见 ENVIRONMENT.md；提交后若要恢复默认目录选择，在当前终端执行 `unset RUN_ROOT ANALYSIS_PROFILE`。

也可在已分配的计算资源中执行：

```bash
PROFILE=full RUN_ROOT="$PWD/runs/dcu_multi-4r" bash run.sh analyse
```

## 6. 可选设置

- 设置共享盘：提交前 `export RUN_ROOT=/你的共享目录/cd3_dcu_4card`；续跑和分析沿用同一个值。
- 使用不同环境脚本：`export SITE_ENV=/你的绝对路径/site-env.sh`；它会替代默认的海光环境片段，须自行包含完整 DTK/Amber/PMI 配置。
- `-AllowSmallBox` 默认不启用。仅在核对具体版本和盒子问题后设置 `export AMBER_ALLOW_SMALL_BOX=1`，启动器才会传给 GPU/DCU 引擎。这不是通用加速参数。
- 不在脚本中硬编码 `HIP_VISIBLE_DEVICES=0` 或 `CUDA_VISIBLE_DEVICES=0`；按站点模板/调度器分配设备。需要逐 rank 绑定时，应由该站点的适配代码完成。
