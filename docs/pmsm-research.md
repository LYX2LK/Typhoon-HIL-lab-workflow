# PMSM 搜索、诊断查询与反馈故障核验

本文面向研究开发与实验人员，说明如何从现有软件案例开展真实反馈搜索、整理开发参照、核验闭环故障，并运行基于观测的诊断查询与证据更新。工作安排见[执行计划](research/2026-11-11-hil-ai-selection/execution-plan.md)，研究主张与正式比较条件见[技术方案](research/2026-11-11-hil-ai-selection/technical-selection.md)。

## 模型反馈搜索

在项目根目录执行，输出目录每次使用一个新路径：

```powershell
.\lab.ps1 pmsm-research --action search --strategy llm --output-dir results/pmsm-search-example --json
.\lab.ps1 pmsm-research --action search --strategy random --output-dir results/pmsm-random-example --json
.\lab.ps1 pmsm-research --action verify --output-dir results/pmsm-search-example --json
```

`configs/pmsm_search_pilot.json`固定模板、允许参数、评分、提案预算与随机种子。首轮问题覆盖调速/减速、负载和事件顺序。LLM 自主选择连续参数和间隔，先记录假设、预计响应及反馈使用，再由程序校验和运行；实际波形计算的恢复、累计误差、电流与尾段特征进入下一轮输入。非法提案保留原响应与拒绝理由，并消耗提案预算。

研究调用模块独立于演示 Agent，只复用服务配置和本地凭据。`configs/ai_service_research.json`指定模型、连接与生成设置，凭据仍从本地环境读取；密钥不进入记录。各轮保存实际HTTP请求、原始响应、返回模型、usage、结束原因和耗时，不自动修补或重发JSON。

恢复时间按末实际事件后回到±50rpm并持续至记录终点计算，至少20ms尾段；评分是100ms减恢复时间。未能确定恢复时保留截尾。参考阶跃造成的瞬间跟踪误差与实际速度跌落分别解释；控制器电流指令限幅与实测相电流峰值也分别解释。

`feedback_rounds`为已返回轮次编号的整数数组。后续提案应引用已有轮次，并说明反馈如何影响选择；引用合法与表达完整只说明协议可用，反馈解释及工程假设的正确性另行审核。

验证入口检查源运行、提案到配置的映射、反馈复算、各轮实际历史以及模型请求/响应绑定。`workflow_status`表示原型流程完成度，子运行的`experiment_status`保留原软件判据。小预算开发实例用于查问题和校准场景，正式方法增益需独立重复与匹配的执行/时间/费用预算。

## 既有运行索引

```powershell
.\lab.ps1 pmsm-research --action index --output-dir results/pmsm-history-index-example --json
```

该入口读取两轮已有PMSM实验，按运行路径去除跨报告重复引用，只读复核并保存来源摘要。索引保留模型来源、配置、单位、采样、判据状态与完整配置分组；复跑用于确定性核对。按对应模型、工况及运行阶段使用参照，开发/测试先按运行或配置族划分再切窗。软件判据通过与实体正常范围分别验证。

## 速度反馈偏置与正常对照

```powershell
.\lab.ps1 run --config configs/pmsm_feedback/normal.json --json
.\lab.ps1 run --config configs/pmsm_feedback/bias150.json --json
.\lab.ps1 verify --run-dir <实际返回目录> --json
```

适配器`pmsm_feedback_probe`使用原PMSM模板的运行副本。在`Rate Transition1.out → speed_regulation.w`之间加入偏置，控制器仍使用该节点形成速度误差。偏置Step的时间、数值和执行周期逐项回读；加法由固定的`out = in + in1`加法数值块实现，输入输出显式声明为real标量。

保留原七通道的独立模型速度，并增加控制器使用的速度反馈、偏置命令，共九通道。`fault.kind`首批仅支持`speed_feedback_bias`，`bias_rpm=0`为相同仪表结构的正常对照，`bias_rpm=150`为偏置实例；范围及时间由适配器校验。软件原型范围不作为实体故障注入范围。

分析分别检查偏置前零值、偏置后电平和生效时刻，以及后段反馈差与注入量的关系。后段取注入后100—200ms、关系误差容差2rpm，用于核验存在控制周期传播的采样链；同时保存真实速度与控制器反馈各自相对参考的误差。原±50rpm性能判据保留：故障使真实跟踪未达标时，`experiment_status=failed`，记录一致性可以仍为`passed`。

该实例验证的是模型内速度反馈偏置及观测路径。下面的诊断器仅接收预先开放的观测与工具，故障配置和隐藏真值由评价器保管；原因区分还需补充相似症状的不同机制与独立运行。

## q轴电流反馈偏置与正常对照

```powershell
.\lab.ps1 run --config configs/pmsm_current_feedback/normal.json --json
.\lab.ps1 run --config configs/pmsm_current_feedback/bias3.json --json
.\lab.ps1 run --config configs/pmsm_current_feedback/bias_minus3.json --json
.\lab.ps1 verify --run-dir <实际返回目录> --json
```

`pmsm_current_feedback_probe`在运行副本的`From15（iq信号）→ Current_regulation.iq`之间加入q轴电流反馈偏置，实际改变电流调节器的输入。原三相电流、机械速度、给定、负载与转矩保留；新增原始q轴电流、控制器使用的q轴电流和注入量，共十通道。该机制位于dq变换后，具体相电流传感器故障与绕组匝间短路需要各自的模型和路径。

`fault.kind=q_current_feedback_bias`，`bias_a`范围为−5至5A，0为相同观测结构的正常对照；发生时间位于控制网格且前后保留分析窗口。范围是当前软件原型范围。准备阶段核对原连接、输出连接及Step属性回读；分析检查初始零值、后段电平、首次变化时刻，以及注入后100—200ms内“使用电流−原始电流−偏置”的绝对均值≤0.1A、RMS≤0.5A。时刻允许采样与四个控制周期的传播范围。

原有速度跟踪及三相电流和判据继续使用。注入是否生效、软件性能是否通过、记录是否一致分别保存；电流环受到扰动后可由速度环补偿，后段恢复与暂态超差分别解释。当前正常、正负偏置的实际结果见[验证记录](validation-history.md)。

## 在同一模型上比较速度反馈、电流反馈与负载变化

使用 `pmsm_feedback_comparison` 可在每种工况下同时采集模型机械速度、控制器速度反馈、原始与控制器使用的 q 轴电流。以下配置把两处偏置都设为零，作为同测点正常对照。

```powershell
.\lab.ps1 run --config configs/pmsm_comparison/normal.json --json
.\lab.ps1 verify --run-dir <返回的运行目录> --json
```

复制配置后，以 `fault.bias_rpm` 或 `fault.bias_a` 设置一处偏置，两项共享 `fault.at_s`。正常负载扰动使用零偏置并添加 `load_torque_nm` 事件。每次运行都在两条控制路径设置相同结构的加法块与探针。分别检查偏置命令、实际反馈差、性能判据和记录复核。运行报告保留全部十二个信号；诊断使用匿名的十个观测，排除两条注入命令和原文件名。

## 实测六相/dq查询与条件化参照

已下载的双三相实测数据通过独立的`pmsm-measured`入口查询，保留原生通道、单位证据和台阶工况，不转换为本地八通道数据。通道表、工况匹配规则、命令及标定缺口见[实测映射](pmsm-measured.md)。它提供诊断查询层；现有`pmsm-diagnosis run`的本地速度偏置任务与评价器继续按原协议运行，实测任务的初始证据、原因标签和正式评分需按数据特点单独冻结。

## 诊断查询与证据更新

先将已复核的正常、故障运行投影为匿名观测包，再对一个观测条件运行模型。以下源目录是已有软件记录；数据包和会话的输出目录均须使用新路径。

```powershell
.\lab.ps1 pmsm-diagnosis --action prepare --normal-source results/20261115-115154-pmsm_feedback_probe-51481c --anomaly-source results/20261115-115320-pmsm_feedback_probe-e217ef --output-dir results/pmsm-diagnosis-data-example --json
.\lab.ps1 pmsm-diagnosis --action run --dataset-dir results/pmsm-diagnosis-data-example --case-id C03 --query-budget 3 --output-dir results/pmsm-diagnosis-session-example --json
.\lab.ps1 pmsm-diagnosis --action verify --output-dir results/pmsm-diagnosis-session-example --json
```

数据包将转速统一为rpm，保留独立模型速度、控制器反馈、给定、负载、转矩与三相电流；偏置命令、原始路径和真值不进入模型请求。当前生成正常、完整故障、隐藏控制器反馈三个条件，编号固定种子打乱。隐藏条件与完整条件复用同一故障波形，来源仍是两份软件运行。`private.json`供评价与复核使用，模型仅能通过受限工具查询开放信号。

| 工具 | 用途与边界 |
|---|---|
| `statistics` | 指定窗口的均值、最小/最大值、RMS和峰峰值，保留单位 |
| `difference` | 同单位测点的left−right差值，保留窗口与样本数 |
| `events` | 给定或负载指令的实际变化 |
| `availability` | 核对是否开放测点；不可用表示缺少观测 |
| `controller_knowledge` | 速度环关系、40A电流指令限幅含义及未记录状态 |

模型自主选择工具和窗口，查询前保存候选、引用和预期数值区间；工具返回数值及预测符合/冲突检查，随后由模型更新判断。工具禁止任意程序与文件访问，缺失数据返回`unavailable`，参数错误返回`invalid_query`。默认预算为3次查询，可设1—5次，至多调用预算加1次模型；非法模型响应或预算耗尽均保留失败记录，不自动修补和重发。

初始证据I0是0.6—0.7s的“模型速度−给定”。新数据包使用`observation_schema_version=2`，显式保存左右测点；首批版本1曾被通用definition字段覆盖，历史包保留当时内容，复核按原版本解释。控制关系说明真实速度偏离给定与反馈偏置可以同时成立。相电流与限幅前后指令是不同信号，当前数据不能确认指令限幅是否介入。

`workflow_status`报告流程是否完成，`evaluation.json`检查本例发现与限幅观测状态，`record_status`检查来源、原始请求/响应、预测先后、数值复算与历史一致性。解释正确性另行审核；单例检查通过不表示整段解释均正确。诊断记录的`experiment_status`为空，源运行性能状态保持原值。

评价版本2接受最终引用的直接测点差，或同一窗口、同一样本集的代数等价差值。例如“控制器反馈−给定”减“模型速度−给定”可得到反馈与模型速度的差异。评价规则修订时创建复核副本：

```powershell
.\lab.ps1 pmsm-diagnosis --action review --source-session results/pmsm-diagnosis-session-example --output-dir results/pmsm-diagnosis-reviewed-example --json
```

该操作不调用模型，保存原评价、来源摘要和复核代码；原会话保持不变。不同窗口或没有最终引用的证据不能合并。版本1的原评分仍可复现。

`fixed_reference`提供同权限工程规则参照：先用初始50rpm跟踪带，再在反馈开放时查询2rpm测点差，缺少区分观测时保留未决。本轮规则用0、0、1次查询取得与修订后模型相同层次的发现，模型各用3次；这些简单开发样例尚未支持LLM额外收益。

## 搜索反馈理解复查

```powershell
.\lab.ps1 pmsm-diagnosis --action feedback-check --search-dir results/agent-tasks/20261115-111428-pmsm-research-start-92b9/llm-search-current --output-dir results/pmsm-feedback-review-example --json
```

该入口从既有两轮搜索复算恢复裕度、IAE与原预测区间，先直接请模型判断，再提供数值和控制知识后复查；两次原始调用分别保存。评价区分数值方向、预测是否兑现与限幅证据是否充分。本轮两次均正确，标记`already_correct`：此前连续搜索中的误解未在这一明确复查格式中复现，仍需在实际连续任务中验证。

## 当前验证与待办

后续样例按[来源与生成机制](pmsm-case-generation.md)准备。当前少量开发样例用于联调与错误检查，研究方向由覆盖实际问题的样例和独立比较评价；公开实测与机理生成同步补充。

实际运行、失败尝试、修订与适用范围见[验证记录](validation-history.md)和[诊断研发结果](../results/agent-tasks/20261115-152610-pmsm-diagnosis-927a/summary.md)。当前已有首批搜索与诊断查询更新；下一步优先补充条件化正常参照、相似症状的不同机制和独立留出运行，并检查缺失证据引用、峰值/峰峰值及负载解释。数值搜索基线、正式方法比较和分任务多模型筛选按各自数据条件推进。
