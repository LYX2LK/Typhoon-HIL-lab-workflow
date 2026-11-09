# 文献、工具与项目证据表

核验日期：2026-11-06。对应 [技术选型方案](technical-selection.md)。本表记录本轮实际阅读深度，方便后续补读、复现及调整选型；未执行这些论文的复现实验。

证据 ID 采用 `ER-20261106-主题-编号`。正文的工具选择是结合资料与项目条件作出的工程判断；论文效果仅在其数据、任务和评价设置内成立。下表中的“正文”表示核对了有关方法、实验或限制章节，不表示逐行审阅全部附录。

## 1. 测试生成、覆盖与搜索

### R01 · FaultGene

- **证据 ID：** `ER-20261106-faultgene-01`。
- **来源：** Chaoran Yuan, Fadi Kurdahi. *FaultGene: LLM-Assisted Fault-Augmented Test Generation for Hardware-in-the-Loop Validation of Autonomous Driving Systems*. arXiv:2610.29969，2026-10-21。[条目](https://arxiv.org/abs/2610.29969)、[正文](https://arxiv.org/html/2610.29969v1)。
- **类型与阅读：** 预印本；核对 HIL 平台、生成/离线修正/部署阶段与实验设置。
- **支持：** 结构化故障规约与执行反馈可以组成测试生成流程。研究使用 Scenic/CARLA 及嵌入式自动驾驶平台，评估留出的场景—故障组合。
- **适配与限制：** 本项目应改为配置与波形指标；论文部署阶段为微调后的单次生成，不能描述成部署时持续迭代。编译率与编译后的执行率有不同分母。本轮未确认可直接用于 Typhoon 的作者实现。
- **决定：** 借鉴流程；不把论文准备时间收益或执行成功率作为本项目预期性能。

### R02 · 机电系统测试边界条件生成

- **证据 ID：** `ER-20261106-boundary-mbse-02`。
- **来源：** Matthias May 等. *Identification of Physical Boundary Conditions for Mechatronic Test-Case Generation Using Large Language Models and MBSE System Models*. Systems 14(3), 302，2026。[期刊页](https://www.mdpi.com/2079-8954/14/3/302)、[DOI](https://doi.org/10.3390/systems14030302)。
- **类型与阅读：** 期刊论文；检索工具返回了正文方法与部分结果，包括需求关系分类、分步映射与上下文流程；后续独立打开全文受到 429 限制。
- **支持：** 为需求到测试规约提供关系分类与物理边界组织线索；对机电对象较相关。
- **限制：** 本轮不依据其结果宣布 Graph RAG 或某一提示方法优于本项目基线，完整评测与材料仍待复核。
- **决定：** 采用可审查的规约组织方式；完整补读进入后续清单。

### R03 · NIST ACTS / Combinatorial Testing

- **证据 ID：** `ER-20261106-acts-03`。
- **来源类型：** 官方工具与方法资料。[项目页](https://csrc.nist.gov/projects/automated-combinatorial-testing-for-software)、[工具页](https://csrc.nist.gov/projects/automated-combinatorial-testing-for-software/downloadable-tools)、[NIST 覆盖数组定义](https://math.nist.gov/coveringarrays/coveringarray.html)。
- **核对：** t-wise 覆盖、约束与混合强度相关官方资料；官网说明软件免费、公有领域，当前要求邮件申请下载链接。
- **支持：** 在已定义的离散有效空间中系统覆盖因素交互。
- **限制：** 离散组合覆盖与连续空间、动态序列、需求及实际故障激活分别统计；免费、公有领域和可直接取得源码是不同事项。
- **决定：** 方法采用；已有安装时可直接作为组合生成器。获取申请未在本任务中代发。

### R04 · Microsoft PICT

- **证据 ID：** `ER-20261106-pict-04`。
- **来源类型：** 作者官方实现。[仓库](https://github.com/microsoft/pict)、[使用与约束文档](https://github.com/microsoft/pict/blob/main/doc/pict.md)、[MIT 许可证](https://github.com/microsoft/pict/blob/main/LICENSE.TXT)。
- **核对：** 参数分区、组合阶数、约束、seed、导出格式与许可证。
- **支持：** 通过独立 CLI 生成紧凑组合集合，适合当前文件/配置工作流。
- **限制：** 用例被约束或下游校验删除后，需重新核算实际覆盖；因素模型与物理正确性由项目定义。
- **决定：** 首个组合生成实现候选，固定版本后试用。

### R05 · PSY-TaLiRo

- **证据 ID：** `ER-20261106-psy-taliro-05`。
- **来源：** Quinn Thibeault 等. *PSY-TaLiRo: A Python Toolbox for Search-Based Test Generation for Cyber-Physical Systems*. 2021。[论文条目](https://arxiv.org/abs/2106.02200)、[当前实现](https://github.com/cpslab-asu/psy-taliro)、[包元数据](https://github.com/cpslab-asu/psy-taliro/blob/main/pyproject.toml)、[许可证](https://github.com/cpslab-asu/psy-taliro/blob/main/LICENSE)。
- **类型与阅读：** 论文元数据/摘要＋当前实现 README、依赖与许可证。
- **支持：** 黑盒轨迹、规约监测及可扩展优化器接口；README 列出 UniformRandom、DualAnnealing。所查包版本 3.2.0，Python `>=3.10,<3.13`，BSD-3-Clause。
- **限制：** 本轮未安装或运行；旧版本在线文档与当前包接口需区分，README 示例也应通过最小调用检查。
- **决定：** 作为搜索框架候选。Typhoon 回调、执行串行化、错误分流和记录仍由项目适配。

### R06 · RTAMT

- **证据 ID：** `ER-20261106-rtamt-06`。
- **来源类型：** 作者官方实现与说明。[仓库与方法说明](https://github.com/nickovic/rtamt)、[许可证](https://github.com/nickovic/rtamt/blob/master/LICENSE)。
- **核对：** STL、离散/稠密时间、离线/在线监测、采样设置和 bounded-future 延迟；BSD-3-Clause。
- **支持：** 把响应时限和保持时间等时序要求转为定量监测。
- **限制：** 数学轨迹语义、实际采样点与点间行为需要明确；质量检查和完整观察窗口由项目先检查。在线未来时算子存在等待时间。
- **决定：** 新时序需求的监测候选，先以人工构造轨迹逐例核对。

### R07 · 贝叶斯反例搜索

- **证据 ID：** `ER-20261106-cps-bo-07`。
- **来源：** Zahra Ramezani, Kenan Šehić, Luigi Nardi, Knut Åkesson. *Falsification of Cyber-physical Systems Using Bayesian Optimization*. ACM Transactions on Embedded Computing Systems，2025。DOI: 10.1145/3711922。[期刊 DOI](https://doi.org/10.1145/3711922)、[作者预印本正文 v3](https://arxiv.org/html/2209.06735v3)。
- **类型与阅读：** 期刊元数据＋作者预印本正文的方法、比较设置与结果表。
- **支持：** 局部 BO、先验及采集函数用于降低黑盒反例搜索成本。论文在多类 CPS 基准上比较，结果随任务和输入参数化变化。
- **限制：** 反例搜索能力不等于安全证明或失效概率估计，论文仿真次数收益不能直接换成当前墙钟收益。
- **决定：** 引入同预算候选；保留随机、边界和直接搜索基线。

### R08 · BoTorch TuRBO 示例

- **证据 ID：** `ER-20261106-botorch-turbo-08`。
- **来源类型：** 官方工具文档。[TuRBO 教程 v0.15.1](https://botorch.org/docs/v0.15.1/tutorials/turbo_1)、[BO 入门](https://botorch.org/docs/getting_started)。
- **支持：** 可以实现局部信赖域 BO，教程展示闭环优化及候选选择。
- **限制：** 教程任务与当前 HIL 不同；最大化/最小化符号、重启、输入量化、噪声和预算需要适配。本轮读取该教程版本，不据此声称它是最新版本。
- **决定：** 原型代码参考；先低维标准 BO，困难任务再评估 TuRBO。

### R09 · Adaptive Stress Testing

- **证据 ID：** `ER-20261106-ast-09`。
- **来源：** Mark Koren, Anthony Corso, Mykel J. Kochenderfer. *The Adaptive Stress Testing Formulation*. 2020 预印本。[作者条目](https://arxiv.org/abs/2004.04293)。
- **阅读：** 元数据与摘要，作为后续方法线索。
- **支持范围：** 确认 AST 这一方法方向及其黑盒失效搜索主题；未据摘要作具体效果结论。
- **决定：** 暂缓。先完成当前低维、可参数化且可复位的测试，再判断是否需要序列决策及概率化扰动建模。

## 2. 异常检测、时序表示与定位

### R10 · TSB-AD

- **证据 ID：** `ER-20261106-tsbad-10`。
- **来源：** Qinghua Liu, John Paparrizos. *The Elephant in the Room: Towards A Reliable Time-Series Anomaly Detection Benchmark*. NeurIPS 2024 Datasets and Benchmarks。[论文](https://papers.neurips.cc/paper_files/paper/2024/file/c3f3c690b7a99fba16d0efd35cb83b2c-Paper-Datasets_and_Benchmarks_Track.pdf)、[作者项目](https://thedatumorg.github.io/TSB-AD/)。
- **类型与阅读：** 正文的数据与指标问题、基准范围及比较讨论。
- **支持：** 基准包含 1070 条单/多变量序列，覆盖 40 个数据集及多类算法；讨论 point adjustment 等评价偏差，提出使用 VUS-PR。
- **限制：** 公共时序基准不能代表本项目所有电力电子/电机工况。VUS-PR 是辅助排序指标，工程决策还要关注固定误报预算下的事件召回与延迟。
- **决定：** 借鉴评价方法；算法实际采用以独立 HIL 数据比较为准。

### R11 · 基础模型与简单基线的重新比较

- **证据 ID：** `ER-20261106-oneliners-11`。
- **来源：** Xiaokun Zhu, Louis Carpentier, Mathias Verbeke. *When Foundation Models are One-Liners: Limitations and Future Directions for Time Series Anomaly Detection*. ICLR 2026。[论文页](https://proceedings.iclr.cc/paper_files/paper/2026/hash/cf70320e93c08b39b1b29a348097a376-Abstract-Conference.html)、[正文](https://proceedings.iclr.cc/paper_files/paper/2026/file/cf70320e93c08b39b1b29a348097a376-Paper-Conference.pdf)。
- **类型与阅读：** 正文方法、评估设置、讨论与表示学习例子。
- **支持：** 在 TSB-AD-U 留出集合及所用设置中，考察多个基础模型家族，与方差、差分等基线比较；提供隐藏表示检测的示例。
- **限制：** 主要是单变量误差式检测，不能扩写为所有多变量模型或所有诊断任务的结论；文中表示学习示例也不构成普遍优势。
- **决定：** 加入简单基线，MOMENT 同时评估冻结特征路线。

### R12 · MOMENT

- **证据 ID：** `ER-20261106-moment-12`。
- **来源：** Mononito Goswami 等. *MOMENT: A Family of Open Time-series Foundation Models*. ICML 2024，PMLR 235:16115–16152。[论文页](https://proceedings.mlr.press/v235/goswami24a.html)、[官方实现](https://github.com/moment-timeseries-foundation-model/moment)、[许可证](https://github.com/moment-timeseries-foundation-model/moment/blob/main/LICENSE)。
- **类型与阅读：** 论文页、官方 README 的接口、教程说明与许可证；未重现论文实验。
- **支持：** 开放时序表示/重建等接口，可用于建立冻结特征对照；代码 MIT，README 推荐 Python 3.11。
- **限制：** 代码许可与具体权重、数据条款分别核对；README 的 A6000/48 GiB 复现实验配置不能直接当作推理显存最低要求。
- **决定：** 冻结表示＋简单检测器为对照候选；重建误差另列，微调按学习曲线决定。

### R13 · TimeRCD

- **证据 ID：** `ER-20261106-timercd-13`。
- **来源：** Tian Lan 等. *Towards Foundation Models for Zero-Shot Time Series Anomaly Detection: Leveraging Synthetic Data and Relative Context Discrepancy*. ICML 2026，PMLR 306:62494–62529。[正式论文页](https://proceedings.mlr.press/v306/lan26b.html)、[作者正文 v5](https://arxiv.org/html/2509.21190v5)、[官方实现](https://github.com/thu-sail-lab/Time-RCD)。
- **类型与阅读：** 正文的方法、限制与部分资源评估；核对当前 Tutorial 和包元数据。
- **支持：** 以相对上下文差异训练异常头，提供单/多变量零样本推理；多变量输出仍是时间点分数。代码 Apache-2.0，有本地权重加载接口。[Tutorial](https://github.com/thu-sail-lab/Time-RCD/blob/main/Tutorial.md)
- **限制：** 长窗口中大量异常可能污染正常参照；窗口长度及动态尺度有影响。分数不直接给部件标签或校准故障概率。
- **决定：** 优先前沿候选，与物理/统计基线同协议比较。采用正式发表的 2026 年版本元数据，仓库仍保留的 2025 预印本引用按不同版本处理。

### R14 · AERCA

- **证据 ID：** `ER-20261106-aerca-14`。
- **来源：** Xiao Han, Saima Absar, Lu Zhang, Shuhan Yuan. *Root Cause Analysis of Anomalies in Multivariate Time Series through Granger Causal Discovery*. ICLR 2025。[论文页](https://proceedings.iclr.cc/paper_files/paper/2025/hash/6fde96479648d71e4fd9724374bf76eb-Abstract-Conference.html)、[官方实现](https://github.com/hanxiao0607/AERCA)。
- **类型与阅读：** 论文元数据/摘要＋完整 README 与代码许可线索；全文方法尚待补读。
- **支持范围：** 确认方法方向和实现入口。作者仓库为 MIT，说明 Ubuntu/Python 环境并标注实现仍在建设。
- **限制：** 本轮不引用其定量效果，也不依据摘要宣布能定位本项目物理根因。
- **决定：** 待补读候选；先建立同步多变量数据、标签及结构对照。

### R15 · 电机数据上的基础模型迁移边界

- **证据 ID：** `ER-20261106-motor-transfer-15`。
- **来源：** *Applicability Boundaries of Time-Series Foundation Models: Data-Layer Mismatch in Industrial Motor Fault Diagnosis*. IEEE Access，2026。DOI: 10.1109/ACCESS.2026.3690553。[期刊 DOI](https://doi.org/10.1109/ACCESS.2026.3690553)、[论文所列仓库](https://github.com/Andychen2018/Applicability-Boundaries-of-Time-Series-Foundation-Models)。
- **类型与阅读：** 核对 DOI、期刊索引内容及仓库目录；期刊全文页面触发浏览器验证，未完成独立全文方法复核。
- **支持范围：** 确认原附件条目存在，且有公开复现材料入口可继续检查。
- **限制：** 未根据索引结果采信平均提升、泛化或设备级结果；具体划分、标签和原始数据可用性需补查。
- **决定：** 领域相关补读对象，不作为本方案性能门槛或收益的定量依据。

## 3. 新增线索及附件条目审计

### R16 · AutoHIL

- **证据 ID：** `ER-20261106-autohil-16`。
- **来源：** Sichen Gong, Qicai Chen, Bihuan Chen, Wenzhuo Zhang, Yukun Gao, Xin Peng. *AutoHIL: LLM-Based ECU Functional Test Generation through Domain Knowledge Augmentation*. ISSTA 2026。[会议页](https://conf.researchr.org/details/issta-2026/issta-2026-research-papers/64/AutoHIL-LLM-Based-ECU-Functional-Test-Generation-through-Domain-Knowledge-Augmentati)、[作者主页](https://chenbihuan.github.io/)。
- **类型与阅读：** 收录元数据与会议摘要；作者主页同样列出收录，但本轮未获得全文与实现。
- **支持范围：** 确认存在直接面向 ECU HIL 功能测试生成的相关研究。
- **决定：** 优先补读并寻找 artifact；摘要数字不进入选型收益测算或复现结论。

### R17 · TestEval

- **证据 ID：** `ER-20261106-testeval-17`。
- **来源：** *TestEval: Benchmarking Large Language Models for Test Case Generation*. Findings of NAACL 2025。[ACL 正式条目](https://aclanthology.org/2025.findings-naacl.197/)。
- **类型与阅读：** 核对正式条目；本轮未据其全文开展 HIL 方法选择。
- **决定：** 保留为软件测试背景阅读；不能用程序路径覆盖成绩直接估计 HIL 工况覆盖。

### R18 · Z3

- **证据 ID：** `ER-20261106-z3-18`。
- **来源类型：** 官方方法与工具资料。[Programming Z3](https://z3prover.github.io/papers/programmingz3.html)、[项目 Wiki](https://github.com/Z3Prover/z3/wiki/)。
- **支持：** SMT 求解可表达变量与跨字段可满足性约束。
- **决定：** 当前先复用适配器校验；约束复杂且确有收益时增加，避免维护两套不一致的规则。

### 附件条目核对结论

| 附件条目 | 本轮核对 | 使用方式 |
|---|---|---|
| FaultGene | arXiv 编号、作者、日期与相关正文已核对 | 方法参考，保留预印本状态及领域差异 |
| 机电边界条件 / MBSE | 题名、期刊与方法正文节选已核对 | 规约组织线索，全文评测待补读 |
| NIST ACTS | 官方项目与获取方式已核对 | 修正“可直接下载的开源工具”这一笼统印象 |
| BO 反例搜索 | 期刊元数据与作者正文已核对 | 搜索候选，不预设必优于直接搜索 |
| TestEval | ACL 正式收录已核对 | 背景线索，不替代 HIL 评价 |
| TSB-AD | 论文与作者项目已核对 | 基准方法参考，另建领域评价 |
| MOMENT | 正式条目与作者实现已核对 | 冻结表示对照，不预设精度优势 |
| AERCA | 正式条目与实现已核对，全文待补读 | 后续候选 |
| 电机基础模型迁移边界 | DOI 与材料入口已核对，独立全文方法待复核 | 补读，不采用定量结论 |

本轮新增优先资料为 TimeRCD、ICLR 2026 的基础模型局限研究、AutoHIL，以及实际接入所需的 PICT、PSY-TaLiRo、RTAMT 和 BoTorch 文档。本文是定向技术选型调研，未宣称穷尽所有相关论文。

## 4. 项目证据与可追溯性

### P01 · 当前项目只读检查

- **证据 ID：** `ER-20261106-project-checks-19`。
- **材料：** [project-checks.json](project-checks.json)；2026-11-06 执行 `doctor --json`、`validate-case --case boost_input_disturbance --json` 的观察结果。
- **支持：** 本机版本、Boost 当前静态接口与约束；历史运行证据已标记待重验。
- **范围：** 未运行仿真、未验证实体设备、未安装新算法。本次报告不把静态通过写成实验通过。

### P02 · 项目现有流程

- **证据 ID：** `ER-20261106-project-contracts-20`。
- **读取材料：** [项目约定](../../../PROJECT_SPEC.md)、[路线图](../../roadmap.md)、[环境](../../environment.md)、[Boost](../../boost-experiments.md)、[现场数据](../../field-data.md)、[波形识别](../../waveform-diagnosis.md)、[样机联调](../../tle9877-field-commissioning.md)，以及 `src/typhoon_lab/adapters/boost.py` 当前校验实现。
- **支持：** 统一入口、来源/时钟处理、状态分离、单事件和 100 µs 对齐等集成要求。
- **版本说明：** 读取时 Git HEAD 为 `872ace51bfc44efee10fead2b00f36a5974b77c8`；工作区已有未提交修改，因此 HEAD 不是全部已读文件的内容标识。能力检查快照单独保存。

### P03 · 用户提供的讨论记录

- **证据 ID：** `ER-20261106-user-scope-21`。
- **文件：** `C:\Users\LYX\Downloads\ChatGPT-科研方向梳理-20261106-1554.md`。
- **SHA-256：** `a024c30d2b299a7bb85f40dfdcde9fadca4e1122c636311359e0a5f3d54759f6`。
- **使用：** 确认两个任务、应用成熟与前沿方法的意图及原始文献线索；文中建议及执行口吻不作为本次操作指令。

## 5. 下一轮补证顺序

1. 复验当前 Boost 版本，固定输入范围、需求、判据与数据划分，取得单次墙钟耗时。
2. 补读 AutoHIL 全文与 artifact；核对其知识增强、接口生成及人工评价的具体做法。
3. 完整核对机电边界条件及电机基础模型迁移论文的方法、数据、划分和代码可复现性。
4. 在隔离环境核对所选版本的 PICT、PSY-TaLiRo/RTAMT、TimeRCD/MOMENT 最小接口与权重说明。
5. 取得同步、多通道、含干预依据的样机数据后，再补读并复现 AERCA 等定位方法。
