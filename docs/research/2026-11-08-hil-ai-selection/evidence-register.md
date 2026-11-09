# 文献、工具与选型依据

检索/核对日期：2026-11-08。读者为需要核对技术推荐、准备复现实验的成员。对应 [主方案](technical-selection.md)。本表记录与本次决策直接相关的资料，旧方案的其他文献保留在 [11 月 6 日记录](../2026-11-06-hil-ai-selection/evidence-register.md)。

阅读“正文”表示获取全文并核对相关方法、设置或限制段，不表示完整复现或逐行核对所有附录。官方实现文档可支持接口/实现存在性，不能支持本机运行效果。所有 HIL 效果预期均为待检验的工程假设。

## 1. 调研范围与取舍

| 检索角度 | 代表检索/查阅 | 对选型的作用 |
|---|---|---|
| ECU 需求到 HIL 测试 | AutoHIL 原始会议页、PICT/PSY-TaLiRo 作者文档 | 保留生成、组合和搜索分工；AutoHIL 仍列优先补读 |
| 动态特征与系统辨识 | SciPy signal、SysIdentPy；PMSM 电流特征/模型诊断论文检索 | 增加分析主干；闭环辨识与测量缺口进入方案 |
| 未知异常 | TimeRCD 正文/教程、MOMENT、TSB-AD | 保留异常专用候选与强基线，单独评价正常动态误报 |
| 故障分类与少标签 | MiniRocket、TS2Vec、MantisV2；追踪 TS2Vec-FM | 新增分类路线；分类专用前沿模型进入首轮 |
| 定位与多源关联 | AERCA 正文/实现、Conditional Attribution 预印本 | 残差定位与传播源区分有独立实验，不由检测分数替代 |
| 跨工况及局限 | 以上论文的输入/训练设置；2026 域泛化与物理诊断检索 | 采用工况留出和物理融合消融；不直接移用轴承振动论文成绩 |

检索到多篇轴承/旋转机械域泛化研究，但对象、故障机制和测量通道与控制板 HIL 不一致，本轮未把其排名作为主选依据。PMSM 电流特征论文 *Diagnosis of Power Switch Faults in Three-Phase Permanent Magnet Synchronous Motors via Current-Signature Technique* 的 [出版社页](https://www.mdpi.com/2076-0825/13/1/25) 返回 429，机构 PDF 返回 403，因此只留补读线索，不据此声称具体诊断效果。物理残差路线在主方案中作为明确方程与条件的工程设计，需本项目验证。

## 2. 核心记录

### ER-20261108-mantis-01 · 分类专用基础表示

- 来源：[ICML 2026 正式条目](https://proceedings.mlr.press/v306/feofanov26a.html)、[MantisV2 正文](https://arxiv.org/html/2602.17868v1)、[作者实现](https://github.com/vfeofanov/mantis)、[模型卡](https://huggingface.co/paris-noah/MantisV2/raw/main/README.md)。
- 类型/阅读：正式发表条目＋方法技术报告全文＋官方实现说明；核对冻结编码器/分类头、单通道编码与多通道拼接、尺寸变换及公开基准范围。
- 支持（supported，限文献/接口）：提供分类导向的预训练表示，冻结编码器后可训练下游分类器。代码与所查权重卡标 Apache-2.0。
- 限制：zero-shot feature extraction 不是无需下游标签的故障分类；默认固定长度变换和通道拼接可能影响 HIL 短事件及耦合信息。
- 选型推断（speculative）：列入 B3 的前沿候选，与 MiniRocket/物理特征同标签预算比较。
- 允许表述：有公开实现的分类候选。禁止升级为：已能高准确率诊断 TLE9877。下一检查：权重可用性、输入转换、少标签/跨工况收益。

### ER-20261108-minirocket-02 · 分类强基线

- 来源：[作者仓库及论文入口](https://github.com/angus924/minirocket)、[多变量实现](https://github.com/angus924/minirocket/blob/main/code/minirocket_multivariate.py)。
- 类型/阅读：官方实现与 README，核对特征变换、线性分类器用途、数据形状、Numba 编译和多变量扩展说明。
- 支持（supported）：存在低成本卷积特征变换及多变量实现；作者仓库标 GPL-3.0。
- 限制：多变量代码自述为基础扩展；论文速度不是本机承诺，首次编译与训练成本都需记录。
- 决定：B3 必留基线。允许称分类对照，不能称物理故障机理识别器；下一检查为留出工况和许可证/依赖固定。

### ER-20261108-ts2vec-03 · 领域自监督表示

- 来源：[AAAI 2022 论文全文](https://arxiv.org/pdf/2106.10466)、[作者仓库](https://github.com/zhihanyue/ts2vec)。
- 类型/阅读：论文全文及官方使用说明；核对层次对比表示、时间点/子序列聚合、训练与分类应用。
- 支持（supported）：能够从时序学习多尺度表示，适合构造同一表示上的下游任务对照。
- 限制：需要目标训练数据；官方建议环境较旧，不是直接可用的通用预训练 checkpoint。裁剪/掩码对故障语义的影响需测试。
- 决定：未标注本域数据充分时进入第二轮。允许称领域表示候选；不能把公开分类结果当 HIL 泛化结果。

### ER-20261108-timercd-04 · 异常专用模型

- 来源：[ICML 2026 条目](https://proceedings.mlr.press/v306/lan26b.html)、[公开正文版本](https://arxiv.org/html/2509.21190v2)、[官方教程](https://github.com/thu-sail-lab/Time-RCD/blob/main/Tutorial.md)。
- 类型/阅读：正式条目、预印本全文和接口文档；核对相对上下文方法、合成预训练、异常头、基准及输入/窗口/阈值说明。正式 PDF 的 raw URL 未被网页工具解析，方法细节引用所读公开正文版本。
- 支持（supported）：存在单/多变量预训练检测接口；方法目标与复杂上下文异常有关。
- 限制：本项目电机/控制板效果未知；上下文长度、正常切换、持续异常与幅值归一化须独立检查。分数不能未经校准直接解释为故障概率。
- 决定：B2 优先试验，按事件效果选择。允许称异常检测候选；不能由其合成因果标签推断当前接口能输出物理根因。

### ER-20261108-moment-05 · 通用表示对照

- 来源：[MOMENT 官方仓库与教程入口](https://github.com/moment-timeseries-foundation-model/moment)。
- 类型/阅读：官方 README 和任务说明；本次核对开放模型及分类/异常等任务入口，前轮文献记录保留。
- 支持（supported，接口级）：可作为冻结表示对照，代码 MIT；权重依所用模型卡另核。
- 限制：通用表示、重建评分和分类头是不同实验；不由模型规模推断收益。
- 决定：保留为第二轮对照；首轮出现明确表示不足且数据、预算满足后，在 B2/B3 分别评价，有益任务才接入常规流程。

### ER-20261108-aerca-06 · 传播源定位

- 来源：[ICLR 2025 全文](https://proceedings.iclr.cc/paper_files/paper/2025/file/6fde96479648d71e4fd9724374bf76eb-Paper-Conference.pdf)、[作者实现](https://github.com/hanxiao0607/AERCA)。
- 类型/阅读：论文全文的建模、训练与假设段及实现说明。OpenReview 初次返回验证页，改从正式会议 PDF 获取。
- 支持（supported，限论文）：从正常时序学习 Granger 关系与外生变量分布，定位异常来源时序及时间。
- 限制：论文明确不是所有异常都符合外生干预设定，且依赖外生变量独立性等条件；闭环控制的共同输入与未观测量须检查。
- 决定：B4 第二轮，与物理残差/偏差排名比较。允许输出经评价的来源排名；不能未经部件映射与干预验证称已确定物理根因。

### ER-20261108-signal-sysid-07 · 特征和动态建模工具

- 来源：[SciPy signal](https://docs.scipy.org/doc/scipy/reference/signal.html)、[SysIdentPy 官方文档](https://sysidentpy.org/)。
- 类型/阅读：官方工具文档，核对信号处理、NARX/NARMAX 及正常输入输出建模入口。
- 支持（supported，工具级）：提供特征处理和低阶动态建模的实现途径。
- 限制：工具存在性不支持参数可辨识或故障可分结论；闭环输入相关、参数失配与滤波误差需独立评价。
- 决定（工程设计）：B1/残差主干；对已知参考估计误差和留出运行表现进行验证。

### ER-20261108-generation-08 · 组合与搜索

- 来源：[PICT 文档](https://github.com/microsoft/pict/blob/main/doc/pict.md)、[PSY-TaLiRo 作者仓库](https://github.com/cpslab-asu/psy-taliro)、[原方案搜索文献记录](../2026-11-06-hil-ai-selection/evidence-register.md)。
- 类型/阅读：本次重新读取官方文档及 README；其他 BO/RTAMT 文献沿用前轮，不作新的复现声明。
- 支持（supported，工具级）：约束组合和黑盒搜索可分别组织；组合覆盖与连续探索不同。
- 限制：工具不保证发现独立新失效；低维容易失败的空间无法充分区分优化器。
- 决定：PICT 用于多因素电机场景，PSY-TaLiRo 按时序需求复杂度选用，BO 按两类边界任务的成本效益判断。

### ER-20261108-benchmark-09 · 评价基准与反面检查

- 来源：[TSB-AD 正式论文](https://papers.neurips.cc/paper_files/paper/2024/file/c3f3c690b7a99fba16d0efd35cb83b2c-Paper-Datasets_and_Benchmarks_Track.pdf)、[When Foundation Models are One-Liners 正式条目](https://proceedings.iclr.cc/paper_files/paper/2026/hash/cf70320e93c08b39b1b29a348097a376-Abstract-Conference.html)。
- 类型/阅读：TSB-AD 全文获取并核对基准设计概述；One-Liners 本轮只复核摘要，详细论证沿用前轮记录，不新增推广结论。
- 支持（supported，TSB-AD 范围内）：异常评估受数据、度量和调参协议影响，需保留强简单基线。不能把其公开基准整体排名迁移到 HIL。
- 决定：事件评价、正常动态、独立分组及调参预算并列；重建误差另列消融，不用报告规范性替代分析效果。

## 3. 跟踪与补读

| ID | 资料与阅读状态 | 本轮如何处理 |
|---|---|---|
| ER-20261108-autohil-10 | [AutoHIL](https://conf.researchr.org/details/issta-2026/issta-2026-research-papers/64/AutoHIL-LLM-Based-ECU-Functional-Test-Generation-through-Domain-Knowledge-Augmentati)，正式会议摘要；检索作者/全文仍未取得完整材料 | abstract-only；仅支持主题相关和优先补读，论文百分比不用于项目预期 |
| ER-20261108-ts2vecfm-11 | [TS2Vec-FM](https://arxiv.org/html/2610.28602v1)，2026-10 预印本；核对双视图、单通道编码与长序列限制 | observed；提示幅值/形状双分支有研究价值，权重和复现条件本轮未核齐，列跟踪而非首轮必装 |
| ER-20261108-conditional-12 | [Conditional Attribution](https://arxiv.org/html/2604.17616v1)，2026 预印本全文；核对条件化正常参照和方法定义 | observed；作者写代码/模型将发布，本轮未核实可用实现。可借鉴参照设计，不能把归因忠实性当物理因果确认 |

## 4. 项目证据与允许结论

`ER-20261108-project-13`：来源为 [project-checks.json](project-checks.json)、[PMSM 适配器](../../../src/typhoon_lab/pmsm_preview.py)、[实体计划](../../../cases/tle9877_hil_smoke/plan.json)、[GUI 预演文档](../../tle9877-gui-practice.md)。类型为本轮命令产物与当前项目源码/文档。

支持当前静态接口、运行证据待重验和实体计划未启用等观察（observed）；GUI 文档中的反转是既有记录描述，本轮未重算该波形。不能从这些材料推断算法已有效或实体闭环已完成。下一步是当前版本少量复验和按任务采集数据。

## 5. 本轮研究结论的范围

有依据的选择是：任务二需要异常、分类、定位和特征分析的不同方法与评价；新增分类专用候选能补原方案缺口；既有执行/记录能力可用于承载比较。具体哪个算法最好、收益多少、是否适用于实体板卡，均待比较协议验证。本轮不主张算法新颖性，不把技术组合写成已发表或已验证的新方法。
