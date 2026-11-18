# 海光 DCU：直接提交完整模拟

海光模板依据根目录 `submit_dcu.slurm`，在计算节点加载平台环境，并直接执行 `bash run.sh full`。不需要单独提交 check 作业。

## 提交

```bash
cd /public/home/aci37mn59u/CYX/Shorten_CD3-Fv_Amber_git
sbatch hpc/submit_dcu_multi.slurm
```

多卡默认 1 节点、8 张 DCU、8 个 MPI 进程，每进程 16 个 CPU 配额，时限 24 小时。全流程依次执行准备、建模、CPU 最小化、升温、平衡、生产和分析。8 张卡共同计算当前轨迹，三个 100 ns 重复依次运行。

单卡使用 `pmemd.hip`，提交命令为：

```bash
sbatch hpc/submit_dcu_single.slurm
```

两份海光脚本都固定运行 full，不读取位置参数。需要 pilot 时，将对应脚本最后一行改为 `exec bash run.sh pilot`。

## 日志与结果

| 模板 | 作业日志 | 正式结果 |
|---|---|---|
| 多卡 | cd3-dcu_multi-作业号.out | runs/dcu_multi-8r/full/ |
| 单卡 | cd3-dcu_single-作业号.out | runs/dcu_single-1r/full/ |

```bash
squeue -j 作业号
tail -n 80 cd3-dcu_multi-作业号.out
sacct -j 作业号 --format=JobID,State,ExitCode,Elapsed
```

最小化使用串行 sander；动力学通过内部启动器调用 srun 和 pmemd.hip.MPI。不要对整个 run.sh 执行多进程 srun。计算节点仍需具备 AmberTools 和 Python 分析依赖；程序会在准备阶段检查依赖。

## 改用四卡

同时覆盖进程数、每节点进程数和 DCU 数：

```bash
sbatch --ntasks=4 --ntasks-per-node=4 --gres=dcu:4 hpc/submit_dcu_multi.slurm
```

结果目录变为 `runs/dcu_multi-4r/full/`。多卡加速效果需结合实际 ns/day 判断。

## 续跑与站点配置

24 小时不保证完成全部模拟。若因时限退出，确认旧作业已结束后，重新提交同一脚本。已完成阶段和分段会核验并跳过，中断段重算；同一输出目录不要同时运行两个作业。

环境路径、项目路径和 RUN_ROOT 都直接写在海光提交脚本中；如需更换，修改对应脚本。海光简化模板不读取 SITE_ENV 或 ENGINE_BIN。其他平台仍使用各自模板。

根目录 submit_dcu.slurm 与 hpc 多卡模板默认写入同一结果目录，因此两者不要同时提交。
