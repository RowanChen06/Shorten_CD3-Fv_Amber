# CD3δε–Fv 模拟系统：CPU / CUDA / HIP 多后端版

版本：2026-11-18。模拟对象为 418 残基的 CD3δε 胞外区–双链 Fv 复合物。本包保留原始结构、ff14SB/TIP3P 建模方案和分析定义，统一了 CPU、NVIDIA CUDA、海光 DCU 及其他具备兼容 Amber HIP 引擎的平台启动方式。

**本版的多卡方式是：多张卡共同推进当前一条轨迹；三个独立重复仍顺序执行。** 最小化使用 CPU `sander`，升温、平衡、生产使用所选引擎。没有内置任何厂商引擎或驱动，也不提供昇腾 NPU 加速实现。

发布包不包含真实模拟轨迹。已完成 16 项启动/续跑回归测试、脚本语法检查和科学输入一致性检查；没有在真实 GPU/DCU 上运行 Amber。验证范围见 [VALIDATION.md](VALIDATION.md)。

## 你当前海光平台：先运行四卡短测试

```bash
cd /public/home/aci37mn59u/CYX/Shorten_CD3-Fv_Amber
# 如经 Windows 文件拷贝丢失执行权限，重新设置：
chmod +x run.sh hpc/*.sh
sha256sum -c PACKAGE_SHA256SUMS
bash run.sh plan
sbatch hpc/submit_dcu_multi.slurm pilot
```

海光模板已填写 `hx1hdnormal`、4 个 MPI 进程、4 张 DCU、每进程 16 个 Slurm CPU 配额，环境路径与架构设置来自你提供的示例。时限暂定 24 小时；该值须符合分区限制。脚本从提交目录定位项目根目录，仓库改名后仍须在此目录运行 `sbatch`。启动前的 `check` 会检查 AmberTools 与 Python 依赖，缺少依赖时停止。

查看作业日志 `cd3-dcu_multi-作业号.out`，以及 `runs/dcu_multi-4r/pilot/`。确认几何检查、轨迹分析及设备使用正常后，再提交：

```bash
sbatch hpc/submit_dcu_multi.slurm full
```

详细操作见 [QUICKSTART_DCU.md](QUICKSTART_DCU.md)。正式配置为 **3 个独立重复 × 100 ns，每个重复 20 × 5 ns**。卡数不会改变轨迹条数或模拟物理时间。

## 提交模板一览

| 用途 | 提交文件 | 默认动力学引擎 | 默认资源 |
|---|---|---|---|
| 海光 DCU 单卡 | `hpc/submit_dcu_single.slurm` | `pmemd.hip` | 1 卡、1 进程、16 CPU |
| 海光 DCU 多卡 | `hpc/submit_dcu_multi.slurm` | `pmemd.hip.MPI` | 4 卡、4 进程、每进程 16 CPU |
| NVIDIA 单卡 | `hpc/submit_nvidia_single.slurm` | `pmemd.cuda` | 1 卡、1 进程、4 CPU |
| NVIDIA 多卡 | `hpc/submit_nvidia_multi.slurm` | `pmemd.cuda.MPI` | 4 卡、4 进程、每进程 4 CPU |
| CPU 单进程 | `hpc/submit_cpu_serial.slurm` | `sander` | 1 进程、1 CPU |
| CPU MPI | `hpc/submit_cpu_mpi.slurm` | `sander.MPI` | 8 进程、每进程 1 CPU |
| 其他 HIP 单卡 | `hpc/submit_hip_single.slurm` | `pmemd.hip` | 1 卡、1 进程、4 CPU |
| 其他 HIP 多卡 | `hpc/submit_hip_multi.slurm` | `pmemd.hip.MPI` | 4 卡、4 进程、每进程 4 CPU |

除海光模板外，分区是 `CHANGE_ME` 占位符，必须填入站点真实分区；GPU 资源名称、CPU/卡比例、账户、PMI 类型和设备绑定要求也以该站点为准。通用 HIP 模板没有写入海光的 `gfx936` 环境变量，不应直接把海光站点脚本用到其他硬件。

各模板都支持 `pilot`、`full`、`check`、`analyse` 参数，默认 `pilot`。更详细的适配说明见 [hpc/README.md](hpc/README.md) 和 [ENVIRONMENT.md](ENVIRONMENT.md)。

## 统一运行入口

在已分配的计算资源中，先配置环境，再明确选择引擎：

```bash
ENGINE=pmemd.hip bash run.sh pilot
# NVIDIA 单卡：ENGINE=pmemd.cuda
# CPU 单进程：ENGINE=sander 或 ENGINE=pmemd
# 多进程：ENGINE=pmemd.hip.MPI / pmemd.cuda.MPI / sander.MPI / pmemd.MPI
```

多卡一般使用提交模板；直接使用 MPI 入口需要有效的 Slurm 分配或显式 `MPI_RANKS` 和站点 MPI 启动器。多卡的默认 Slurm 启动器为 `srun`，海光站点设为 `--mpi=pmix_v4`。本版不再自动判断显卡后回退 CPU；未设置引擎会明确报错。

| 命令 | 含义 |
|---|---|
| `bash run.sh plan` | 只读配置并显示模拟规模，不需要 Amber |
| `ENGINE=... bash run.sh check` | 检查引擎、启动器与分析依赖；不启动 MD，不证明已使用加速卡 |
| `ENGINE=... bash run.sh pilot` | 建模、最小化、升温、平衡、200 ps 生产与分析 |
| `ENGINE=... bash run.sh full` | 完整 3 × 100 ns 流程及分析 |
| `PROFILE=full RUN_ROOT=... bash run.sh analyse` | 对指定目录已有完整轨迹重新分析；不需要动力学引擎 |

`analyze` 也作为 `analyse` 的别名。裸命令 `bash run.sh` 仍代表 full，但必须事先 `export ENGINE=...`。提交模板会替你选择引擎。

## 输出目录、续跑与版本

每种模板/进程数默认使用独立根目录，例如海光四卡为 `runs/dcu_multi-4r/full/`，海光单卡为 `runs/dcu_single-1r/full/`，NVIDIA 四卡为 `runs/nvidia_multi-4r/full/`。手动调用 run.sh 默认为 `runs/manual/`。可显式 `export RUN_ROOT=/共享工作盘/自定义目录` 覆盖；重新分析和续跑必须沿用同一个根目录。

每个阶段只在进程成功、文件和检查点通过核验后写入 `complete.json`。重提同一命令会核验并跳过已完成段；中断段从上一个已完成段重算，**不能从中断段中间自动恢复**。同一结果目录的写锁阻止多个主流程并发写入。不要 `srun -n 4 bash run.sh full`，也不要用三份相同的 full 提交来模拟三个重复并行。

本版改动了工作流代码及其指纹。建议在新目录解压并使用新输出目录；旧包已生成的运行目录应保留原配套代码，不要直接覆写旧包后续跑。模型、参数、随机种子与分析算法保持原方案。

## 模型与采用的假设

| 原链 | 原 CIF 中保留的编号 | Amber 编号 | 角色 |
|---|---:|---:|---|
| A1 | 22–105 | 1–84 | CD3δ 胞外区 |
| A2 | 23–126 | 85–188 | CD3ε 胞外区 |
| B1 | 1–123 | 189–311 | 重链可变区 |
| B2 | 1–107 | 312–418 | 轻链可变区 |

原始参照有 461 个残基。工作结构有 418 个残基，其 3,265 个原始重原子的坐标逐项来自原 CIF；额外删除了跨膜残基和保留的信号肽末位。所研究的是未糖基化的可溶性构建体。四条肽链均采用常规带电自由末端，五个 His 暂设中性 HIE（A1 89；A2 61、81；B1 32、54，均为原编号）。真实构建体的标签、末端、pH、His 互变异构与 CD3δ Asn38/74 糖基化情况如有实验信息，应对照修订。

使用 ff14SB、TIP3P 和截角八面体水盒；solvateOct 的溶剂缓冲距离设为 12 Å，这不是盒边长。显式建立六对链内二硫键。按初始水数 × 0.15 / 55.5 四舍五入估算 NaCl 对数，另加 Na+ 中和。保留最终含水拓扑与初始状态，即可复用实际的离子放置。二硫键对应原编号 A1 37–73、93–96；A2 49–98、119–122；B1 22–96；B2 23–88。

原始 A1 Cys93–Cys96 的 SG–SG 距离为 4.50 Å，A2 Cys119–Cys122 为 1.23 Å；原始 A1 Arg32 NH2 与 B2 Asp92 主链 O 仅 1.40 Å。建拓扑时指定氧化状态，先在 Cα 位置约束下作局部松弛，再作无位置约束最小化。对比 build、min_ca、min_free 的 geometry.txt，区分解除碰撞与后续的热运动。若本地几何仍异常，检查具体键、侧链和末端，并结合实验结构处理。自动检查只是筛查。

## 运行顺序与默认参数

| 阶段 | 正式 full | 短测试 pilot | 结果与用途 |
|---|---|---|---|
| 建模 | 两次 LEaP，先计水再中和加盐 | 相同 | system.parm7、system.rst7；检查电荷、盒子、链边界和二硫键 |
| 最小化 | Cα 约束 3 kcal/(mol·Å²)，再完全解除；分别最多 8,000、12,000 步 | 相同 | 两次 min 的坐标、局部距离、能量和梯度；迭代步数没有物理时间 |
| 升温 | 各重复独立设置随机种子；NVT 10→300 K，50 ps，1 fs 步长，Cα 约束 2 | 相同 | 温度曲线、第一份含速度检查点 |
| 平衡 | 300 K、目标 1 bar；Cα 约束 0.5 的 NPT 500 ps；解除位置约束后 NPT 1,500 ps | 100 ps + 200 ps | Langevin 温控、Berendsen 调密度；用 thermo.csv 查看温度、密度、体积和势能 |
| 生产 | 各重复在各自平衡末盒体积下以 NVT 300 K 跑 20 × 5 ns；2 fs 步长，每 10 ps 保存一帧 | 1 × 0.2 ns，每 2 ps 保存一帧 | 无蛋白位置约束；约束涉及氢的键。每重复 10,000 帧，pilot 100 帧 |
| 分析 | 分重复处理后汇总 | 同一套指标 | RMSD、姿势、接触、盐桥、直接氢键、水桥、时间分块、重复间统计与代表构象 |

脚本做技术完整性检查后自动转入下一阶段。研究者可在运行期间查看每个重复的 eq_free/thermo.csv；持续漂移时应延长平衡，再解释生产段。脚本按完整配置执行，完成标记表示计算和文件检查通过，不代表采样已经收敛。full 的 3 × 100 ns 为首轮预算，三个重复均从同一最小化构象出发，独立生成速度。全程目标温度按当前方案取 300 K。

## 随包文件逐项索引

| 文件 | 用途 |
|---|---|
| `README.md` | 总入口：模型、模板、运行、结果和本文件索引。 |
| `QUICKSTART_DCU.md` | 针对 hx1hdnormal 的单卡/四卡/改卡数、提交、监控、续跑和分析步骤。 |
| `ENVIRONMENT.md` | 所需软件、站点环境加载、MPI 与设备绑定、依赖检查、时间/存储估算。 |
| `CHANGELOG.md` | 本版变化、兼容范围与旧输出迁移说明。 |
| `VALIDATION.md` | 实际验证范围、可复现测试命令与未验证部分。 |
| `PACKAGE_SHA256SUMS` | 本发布包其他文件的 SHA256；在解压目录内运行 sha256sum -c PACKAGE_SHA256SUMS。 |
| `run.sh` | 唯一主入口：配置引擎、加锁、顺序执行各阶段和各重复。 |
| `config/protocol.json` | pilot/full 的种子、时长、分段数、帧间隔；不因卡数变化。 |
| `config/README.md` | JSON 各字段的中文解释及时间单位。 |
| `environment/environment.yml` | Conda 的 CPU 建模/分析依赖清单；不包含 GPU/DCU PMEMD 引擎。 |
| `hpc/README.md` | 各提交模板与公共启动器的关系、适配参数。 |
| `hpc/configure_engine.sh` | 识别标准 Amber 引擎、检查类别与模板一致，并设置统一启动器。 |
| `hpc/launch_engine.sh` | 单进程直接启动；MPI 用 srun/mpirun/mpiexec 启动当前 Amber 阶段。 |
| `hpc/job_runner.sh` | 各 Slurm 模板共用作业主体，加载环境、确定输出根目录并启动一份 run.sh。 |
| `hpc/env_dcu_hx.sh` | 用户提供的海光站点环境路径、gfx936 变量和 pmix_v4 设置。 |
| `reference/output.cif` | 461 残基原始结构，作为结构变化参照。 |
| `reference/SHA256SUMS` | 原始 CIF 校验和。 |
| `input/ecto.pdb` | 418 残基四链工作结构；CYX/HIE 命名与 TER 链边界。 |
| `input/residue_map.csv` | 原始 CIF 编号到 Amber 编号、残基名的逐项映射。 |
| `input/original_contacts.csv` | 最初 44 对界面残基接触及其编号。 |
| `mdin/build.leap` | ff14SB/TIP3P、二硫键和水盒，工作流补入离子数。 |
| `mdin/min_ca.in` | Cα 约束最小化。 |
| `mdin/min_free.in` | 无位置约束最小化。 |
| `mdin/heat.in` | NVT 升温及位置约束。 |
| `mdin/eq_ca.in` | 带较弱位置约束的 NPT 调密度。 |
| `mdin/eq_free.in` | 无位置约束 NPT 平衡。 |
| `mdin/production.in` | NVT 生产模板；种子、步数、输出间隔由工作流填充。 |
| `scripts/workflow.py` | 生成输入、调用 Amber、核验输出、记录真实引擎和执行环境、管理阶段恢复。 |
| `scripts/check_system.py` | 检查链边界、六对二硫键、电荷、周期盒和链间过近接触。 |
| `scripts/analyse.py` | 重映像、对齐、RMSD/位姿、接触、氢键、水桥、代表构象和跨重复统计。 |
| `tests/test_launchers.py` | 启动器、八种模板、参数传递、退出状态、主循环与写锁的替身测试。 |
| `tests/test_resume.py` | 已完成段复用、截断/篡改检查点检测、中断段重算的测试。 |
| `hpc/submit_cpu_serial.slurm` | CPU 单进程提交模板，调用 job_runner.sh。 |
| `hpc/submit_cpu_mpi.slurm` | CPU MPI提交模板，调用 job_runner.sh。 |
| `hpc/submit_nvidia_single.slurm` | NVIDIA 单卡提交模板，调用 job_runner.sh。 |
| `hpc/submit_nvidia_multi.slurm` | NVIDIA 多卡提交模板，调用 job_runner.sh。 |
| `hpc/submit_dcu_single.slurm` | 海光单卡提交模板，调用 job_runner.sh。 |
| `hpc/submit_dcu_multi.slurm` | 海光多卡提交模板，调用 job_runner.sh。 |
| `hpc/submit_hip_single.slurm` | 通用 HIP 单卡提交模板，调用 job_runner.sh。 |
| `hpc/submit_hip_multi.slurm` | 通用 HIP 多卡提交模板，调用 job_runner.sh。 |

## 结果从哪里看

以下路径相对于 `$RUN_ROOT/full` 或 `$RUN_ROOT/pilot`。海光四卡默认根目录为 `runs/dcu_multi-4r`。rep01、prod001 分别表示第一个重复及第一个生产段。

| 输出 | 用法 |
|---|---|
| protocol.json、environment.jsonl | 固化实际模拟输入的 SHA256、参数、软件路径、Python 包版本及作业信息 |
| build/system.parm7、build/system.rst7 | 含水盐的拓扑与初始坐标；build.leap、build.log 记录实际离子数和建模过程 |
| min_ca/、min_free/ | 各阶段的 end.rst7、md.out、geometry.txt；与 build/geometry.txt 对照检查结构松弛 |
| rep01/heat/、eq_ca/、eq_free/（均在同一重复内） | 温度、密度等在 thermo.csv；原始能量、约束与警告在 md.out；轨迹在 wet.nc |
| rep01/prod001/ 至 prod020/ | wet.nc 为含水轨迹，end.rst7 含坐标、速度和盒子；md.in、md.out、thermo.csv 给出实际参数和能量记录 |
| rep01/analysis/protein.parm7、protein.nc | VMD 用。先加载 parm7，再在该分子中加载 nc。第 1 帧是平衡末态，后续为生产帧；metrics.csv 的第 1 帧对应 VMD 的第 2 个构象（VMD 帧索引 1） |
| rep01/analysis/metrics.csv | 生产时刻、两种参照的 RMSD、Fv 几何中心位移和转角、原始接触及平衡末态接触保持率、新接触数和盐桥数。几何中心按 Cα 等权平均 |
| rep01/analysis/contacts.csv、salt_bridges.csv | 按原链和原残基列出界面占有率；原始接触即使后来完全消失也会保留在 contacts.csv |
| rep01/analysis/interface_hbonds.csv、water_bridges.csv | 跨抗原–抗体的直接氢键和单水桥统计。原始 cpptraj 输出保存在 direct_all.dat、bridge_ids.dat、bridge_trace.dat，参数见 hbond.in |
| rep01/analysis/representative.pdb、representative.txt | 代表帧及其生产时间，按 Fv 姿势 RMSD 与原始接触保持率的标准化空间选最靠近平均值的实际帧 |
| summary/traces.png、replica_stats.csv、blocks.csv | 各重复时间曲线、单重复均值/中位数/时间序列标准差，以及每条轨迹四等分的分块均值 |
| summary/across_replicas.csv、cross_replica_contacts.csv | 重复均值之间的样本标准差、各残基对逐重复占有率。一次 pilot 的重复间标准差留空 |
| 每阶段的 complete.json、运行中的 *.partial | 前者记录完成文件大小和重启/拓扑校验和。失败时最近日志在 .partial 中；同一命令重试会重新生成未完成段。 |

## 如何理解这些分析

- 对每帧分别以原始 CIF 或本重复平衡末态作参照。对齐抗原的 188 个 Cα 后计算 Fv 的姿势 RMSD、几何中心移动、相对旋转角；再对齐 Fv 自身的 230 个 Cα 计算内部 RMSD。由此区分整个 Fv 的位姿变化和自身构象变化。
- 两残基只要有一对原始蛋白重原子距离 ≤4.0 Å，就计为一对接触。Q_original 的分母为 44，四个链对的分母依次为 26、6、10、2。Q_eq 以各自平衡末态的接触为分母。同一帧里新接触和原有接触可同时出现。
- 盐桥判据为异号侧链原子间距离 ≤4.0 Å，正侧链取 Lys NZ 或 Arg NE/NH1/NH2，负侧链取 Asp OD1/OD2 或 Glu OE1/OE2。氢键采用 CPPTRAJ 供受体识别，重原子距离 ≤3.2 Å、D–H···A 角 ≥135°。水桥要求同一水分子在同一采样帧分别与抗原和抗体形成氢键。多颗水桥接同一残基对时，该残基对在该帧只计一次。
- 为控制分析量，用全部生产帧找出曾在 7 Å 范围内接近另一结合伙伴的残基，再在这些残基上分析直接氢键与水桥。默认 full 的含水轨迹每 10 ps 保存，每段从首帧起每 10 个保存帧计算一次氢键（间隔 100 ps）。pilot 使用全部生产帧。占有率描述保存时刻的出现频率；快水交换寿命需要更密的输出。
- 含水原始轨迹和配套拓扑须一同保留。跨重复标准差和时间分块用于发现分歧或漂移；结论限定于这套未糖基化胞外区模型及已采样时段。仅凭接触保持率不能推导结合亲和力。

## 运行后检查

- 先看 `min_free/geometry.txt` 与 `summary/traces.png`；几何检查通过仅表示自动筛查通过。
- 核对 `rep01/prod001/md.out` 的 `ns/day`、引擎和设备报告；结合站点监控确认申请的卡被使用。
- 阅读 `environment.jsonl`：本版记录真实引擎路径、MPI 模式、rank 数、可见设备变量、站点脚本及启动器校验和。
- 查看平衡阶段温度、密度、势能，以及生产段的分块和重复间差异；完成标记不代表充分采样或收敛。
- 故障时保留 `.partial/console.log` 和 `.partial/md.out`；再次提交会重算该未完成段。

方法资料：[AmberTools](https://ambermd.org/AmberTools.php) · [ff14SB](https://doi.org/10.1021/acs.jctc.5b00255) · [CPPTRAJ 氢键](https://amberhub.chpc.utah.edu/hbond/) · [Amber CPU/CUDA/HIP 运行示例](https://docs.csc.fi/apps/amber/) · [Slurm srun](https://slurm.schedmd.com/srun.html)
