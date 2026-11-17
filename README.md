# CD3δε 胞外区与双链 Fv 的 Amber 分子动力学模拟

本包从人 CD3δε–双链 Fv 的原始结构出发，在显式水中观察双链 Fv 的姿势、内部形变及抗原–抗体接触如何随时间变化。
四条链分别是 A1（CD3δ）、A2（CD3ε）、B1（VH）和 B2（VL）。原始坐标、模拟输入与分析方法均随包提供。发布包内没有已完成的 MD 轨迹。环境与平台部署见 [ENVIRONMENT.md](ENVIRONMENT.md)。

**本次发布验证**：原始 CIF 与工作 PDB 的 3,265 个重原子、44 对原始接触、Bash 分派与锁、60 个正式生产段的衔接和中断恢复均已检查。轨迹分析经过受控的 NetCDF 测试帧验证；这些测试帧没有作为科学结果打包。制作环境没有 Amber 引擎，尚未完成真实的 LEaP 建模或 MD 试跑，平台首测使用 pilot。

## 一键运行

1. 上传并解压 `CD3_Fv_AmberTools.zip`，进入内层 `cd3_ambertools`。在 Linux 计算资源上加载软件，安装方法见环境说明。
2. 查看方案和环境，再用 pilot 实测引擎速度、磁盘占用和分析过程。
3. 在分配好的计算节点执行正式命令，或在登录节点按下一段提交 Slurm 作业。

```bash
cd cd3_ambertools
bash run.sh plan          # 只列出预计轨迹规模，需要 Python 标准库
bash run.sh check         # 检查当前环境能否找到运行依赖
bash run.sh pilot         # 1 个重复，200 ps 生产；包括建模、平衡和分析
bash run.sh full          # 一键正式运行，3 个重复，每个 100 ns
```

`bash run.sh` 与 `bash run.sh full` 等价。上面四条是分开的入口，正式命令本身会完成全部计算阶段。pilot 与 full 写入不同目录；正式模拟独立建模和平衡。默认检测到 pmemd.cuda 与 nvidia-smi 时使用 GPU 引擎，其余用 sander。可指定 `ENGINE=pmemd.cuda bash run.sh full` 或 `ENGINE=sander bash run.sh pilot`。最小化固定使用 sander。

若平台使用 Slurm，并已经按 ENVIRONMENT.md 配好环境，从包根目录提交：

```bash
sbatch --export=ALL,PROFILE=pilot hpc/submit.slurm
# 查看短测试结果后
sbatch --export=ALL,PROFILE=full hpc/submit.slurm
```

建议把 `RUN_ROOT` 设在足够大的共享工作盘。如未设置，项目根目录下自动创建 `runs/pilot` 和 `runs/full`。中断后在同一环境和 RUN_ROOT 下重新执行原命令；完整段会跳过，未完成段从上一个完成段的重启文件重算。默认仅一个写进程，正式的三个重复顺序执行。

## 模型与采用的假设

| 原链 | 原 CIF 中保留的编号 | Amber 编号 | 角色 |
|---|---:|---:|---|
| A1 | 22–105 | 1–84 | CD3δ 胞外区 |
| A2 | 23–126 | 85–188 | CD3ε 胞外区 |
| B1 | 1–123 | 189–311 | 重链可变区 |
| B2 | 1–107 | 312–418 | 轻链可变区 |

原始参照有 461 个残基。工作结构有 418 个残基，其 3,265 个原始重原子的坐标逐项来自原 CIF；额外删除了跨膜残基和保留的信号肽末位。所研究的是未糖基化的可溶性构建体。四条肽链均采用常规带电自由末端，五个 His 暂设中性 HIE（A1 89；A2 61、81；B1 32、54，均为原编号）。真实构建体的标签、末端、pH、His 互变异构与 CD3δ Asn38/74 糖基化情况如有实验信息，应对照修订。

使用 ff14SB、TIP3P、12 Å 截角八面体水盒，显式建立六对链内二硫键。按初始水数 × 0.15 / 55.5 四舍五入估算 NaCl 对数，另加 Na+ 中和。保留最终含水拓扑与初始状态，即可复用实际的离子放置。二硫键对应原编号 A1 37–73、93–96；A2 49–98、119–122；B1 22–96；B2 23–88。

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

| 文件 | 内容与调用关系 |
|---|---|
| README.md | 项目说明、运行入口、输入索引与结果判读，即本文件 |
| ENVIRONMENT.md | 操作系统、CPU/GPU、软件安装、Slurm 适配、机时及磁盘估算 |
| environment/environment.yml | Conda 可读取的依赖清单；不包含 GPU 版 pmemd.cuda |
| run.sh | 用户主入口；加写锁，顺序调用建模、最小化、各重复平衡和生产，最后分析 |
| hpc/submit.slurm | 单节点单 GPU 的 Slurm 模板；从提交目录启动同一 run.sh |
| config/protocol.json | pilot、full 的起始种子、重复数、平衡时长、分段数、段时长和采样间隔 |
| reference/output.cif | 461 残基模型的原始坐标；结构比较的参照 |
| reference/SHA256SUMS | 原始 CIF 的校验和；从项目根目录可运行 sha256sum -c reference/SHA256SUMS |
| input/ecto.pdb | 418 残基工作结构，四链用 TER 分开，使用 CYX 和 HIE 模板命名 |
| input/residue_map.csv | 原链号、原残基编号和名称到 PDB 链、Amber 编号和模板的逐残基映射 |
| input/original_contacts.csv | 原始 CIF 的 44 对 ≤4.0 Å 界面接触，以原编号和 Amber 编号标识 |
| mdin/build.leap | 蛋白与水力场、六对 S–S 键、水盒。运行时补入离子数及最终保存命令 |
| mdin/min_ca.in | 保留骨架 Cα 位置约束的第一阶段能量最小化 |
| mdin/min_free.in | 解除位置约束的第二阶段能量最小化 |
| mdin/heat.in | NVT 升温曲线与 Cα 位置约束 |
| mdin/eq_ca.in | 带较弱 Cα 约束的 NPT 调密度 |
| mdin/eq_free.in | 无 Cα 位置约束的 NPT 平衡 |
| mdin/production.in | NVT 生产段模板；种子、步数与写帧间隔由运行器填充 |
| scripts/workflow.py | 生成实际输入、调用 Amber、保存环境和检查点、核对帧数和末时间、提取热力学记录，管理恢复和分析 |
| scripts/check_system.py | 检查 418 残基、四条肽链边界、六对 S–S、体系净电荷、周期盒与最短链间重原子距离 |
| scripts/analyse.py | 重映像与对齐、两种参照下的几何、残基接触、盐桥、氢键/水桥、代表帧和跨重复统计 |

## 结果从哪里看

以下路径相对于 runs/full 或 runs/pilot。rep01、prod001 分别表示第一个重复及第一个生产段。

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

## 续跑与排查

- 超时、中断后，重新执行同一个 full 或 pilot 命令；不要在同一输出目录同时启动两个任务。
- 已完成的科学输入有指纹记录。改变力场、坐标、运行参数或运行器后，可设置新的 RUN_ROOT 进行新方案。只重新分析已有完整轨迹，执行 `PROFILE=full bash run.sh analyse`，会重新生成分析并替换分析目录，不重新运行 MD。
- 无 GPU 执行权限或 CUDA 报错时，先看批作业分配到的节点，再查具体阶段的 console.log 和 md.out。几何检查失败时看 geometry.txt，核实原子映射及二硫键。
- 技术完成的依据为进程成功、末时间与帧数一致以及输出完整。请同时检查最小化最大梯度、eq_free/thermo.csv、分块统计和逐重复曲线。若平衡阶段明显漂移，可在新方案中延长 eq_free_ps。

方法资料：[AmberTools](https://ambermd.org/AmberTools.php) · [ff14SB](https://doi.org/10.1021/acs.jctc.5b00255) · [CD3 近膜二硫键](https://doi.org/10.1038/s41586-024-07920-0) · [CPPTRAJ 氢键与水桥](https://amberhub.chpc.utah.edu/hbond/) · [采样及不确定性评估](https://doi.org/10.33011/livecoms.1.1.5067)
