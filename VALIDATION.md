# 本版实际验证范围

验证日期：2026-11-18。下述测试在制作环境进行，不是海光/NVIDIA 真机结果。

## 已完成

| 检查 | 结果 |
|---|---|
| Bash 语法 | run.sh、4 个公共/站点 .sh、8 个 Slurm 模板，共 13 个文件通过 bash -n |
| Python 语法 | 3 个工作脚本和 2 个测试文件通过 AST 解析 |
| 启动和续跑回归 | unittest 共 16 项通过，部分测试内部覆盖多种引擎/全部八种模板 |
| 原始输入一致性 | input、reference、mdin、protocol.json、environment.yml 共 14 个文件与原包逐字节一致 |
| 分析算法一致性 | analyse.py 和 check_system.py 去掉模块文档字符串后的 AST 与原包一致，仅补中文说明 |
| 原始参照校验 | reference/SHA256SUMS 通过 |
| 包装 | ZIP 校验、解压后文件 SHA256、可执行权限与文件索引覆盖在发布前核对 |

16 项测试覆盖：单进程 CPU/CUDA/HIP；CPU/CUDA/HIP 的 MPI 启动；精度后缀名称；带空格/特殊字符路径；未设引擎时停止；禁止把命令串当引擎；MPI 进程数检查；srun/mpiexec/mpirun；底层错误码传递；小盒子选项显式启用；模板与引擎类型一致；check 不启动动力学；实际主循环每重复只调用一次；analyse/analyze 别名；写锁阻止第二个主流程；八种提交模板的选型；完成段复用与损坏检测；中断段重算。

回归测试使用临时替身引擎和临时文件，测试数据不作为科学结果打包。可复现命令：

```bash
python3 -B -m unittest discover -s tests -v
bash -n run.sh
sha256sum -c PACKAGE_SHA256SUMS
bash run.sh plan
```

## 未完成的真机验证

制作环境没有 tleap、sander、cpptraj、pmemd.cuda.MPI 或 pmemd.hip.MPI；未进行真实建模、数值积分、设备占用确认、MPI/驱动兼容性验证或性能测量。海光环境路径、gfx936 与 pmix_v4 来自用户提供的站点示例。

因此首次上平台必须先执行 pilot，检查几何、温度/密度、帧数与重启、分析输出、实际设备使用和 ns/day。check 通过不等于引擎已经在卡上运行，多卡资源分配正确也不等于具有良好加速比。

本次没有改变科学方案，也没有重新宣称验证旧版所有统计细节。原先的 3 × 100 ns 是首轮采样预算；是否足够仍需针对实际观测量评估。旧运行目录的工作流指纹与新版不同，不能直接覆盖旧代码后无条件继续运行。
