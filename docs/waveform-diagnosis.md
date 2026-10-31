# 波形异常识别与大模型解释

面向课题组演示人员和分析模块维护者，将已接收的原始波形转为可检查的正常/异常判断、异常位置和数值依据，再由大模型解释。该入口对应筹建计划第15条“示例波形提供：正常波形和异常波形原始数据，用于模型识别”。

当前方法适用于显式选择 dip 的正基准电平跌落，以及选择 rise 的上升过程回落。正常表示指定规则和窗口内未检出事件。具体故障原因和控制器性能需要测点、工况与相应评价依据。

## 运行演示

先按[外部数据接收](external-waveforms.md)完成 analyze-waveforms / verify-waveforms。已有完整且复核通过的数据包可以直接作为 source-run；下面使用原 tu 数据包。每次指定新的输出目录：

```powershell
.\lab.ps1 diagnose-waveforms --source-run results/agent-tasks/20261023-capability-intake/tu-evidence --rules configs/tu_diagnosis_rules.json --output-dir results/填写新的识别目录 --json
.\lab.ps1 verify-diagnosis --run-dir results/填写新的识别目录 --write --json
```

输出的 report.html 包含全部图像，可离线打开；report.md 用于文字核对。diagnosis.json 保存规则判断、时间位置及数值证据；llm_request.json 是供大模型阅读的结构化输入。源包完整复制至 source/，包括原始 CSV、截图、元信息、既有方法和代码快照。

复核通过表示原件、结果和从 CSV 重算的指标一致，不代表设备合格。正常和异常两类都属于成功完成的分析；无法适用规则时输出 inconclusive，分析状态为 incomplete。

## 规则及数据含义

规则在运行前由 JSON 固定；当前 tu 批次的配置为 configs/tu_diagnosis_rules.json。三个阈值分别是：

| 参数 | 计算定义 |
|---|---|
| dip_fraction | 相对起始参考值的下降比例；参考值为清单 baseline_fraction 指定起始样本的中位数 |
| rise_drawdown_fraction | 回落幅度除以首尾中位数之差；回落幅度为当前值与此前累计峰值之差 |
| minimum_duration_s | 连续越过幅度阈值的最短采样支撑时长，按连续样本数乘 CSV 间隔计算 |

幅度使用严格大于，最短持续时间包含等号，并容许采样间隔的微小浮点误差。dip 使用清单分析窗口；rise 在该窗口内进一步检查首次 10%–90% 向上穿越区间，沿用已有方法定义。rise 的穿越时间只描述首次边沿，未评价完整响应、稳定时间或最终平台。事件区间表示越限段，不等于故障开始到恢复的完整物理区间。

方法使用清单声明的单位和窗口，不进行平滑、重采样、跨文件同步或探头倍率补偿。数据质量失败、单位缺失、方法不适用或采样间隔大于最短持续时间时，返回无法判定。

分类只读取波形、显式方法、窗口和阈值。label_context 是来源和逐文件参考标签，分类完成后才用于比较，不参与预测。逐文件标签的 confirmed / inferred / unconfirmed 状态独立保留。原 tu 群聊说明批次有两正常、两异常；tu1/tu2 和 tu3/tu4 的具体配对是形态推断。群聊的“us 精度、200 MSa/s、131 kpts”保留为来源陈述；截图参数与 CSV 网格仍分别记录。

该演示使用已查看的四组样本选择规则，因此即使与参考标签全部相符，也不应报告为独立识别准确率。规则阈值是当前演示选择，未建立设备验收依据。

## 大模型解释及复现范围

将 llm_request.json 交给选定大模型，按其中的结构要求生成 JSON 回答。回答应携带该请求文件的 SHA-256，以及提供方、模型、传递方式和上下文说明。用 PowerShell 获取哈希时，Get-FileHash 的哈希字符串应转成小写，与项目 sha256 的写法一致：

```powershell
(Get-FileHash -LiteralPath 'results/填写新的识别目录/llm_request.json' -Algorithm SHA256).Hash.ToLowerInvariant()
.\lab.ps1 explain-waveforms --run-dir results/填写新的识别目录 --response '填写模型回答.json' --output-dir results/填写新的解释目录 --json
.\lab.ps1 verify-diagnosis --run-dir results/填写新的解释目录 --write --json
```

explain-waveforms 先验证原识别包和回答，再创建新目录。回答不能改写数值分类，必须保留 cause_status=undetermined，并引用已存在的 evidence 字段或 events。报告显示模型解释及其来源。请求、回答和规则分别留证，后续可对接独立 API 或本地推理服务。

本次演示由当前 Codex 会话读取请求并生成回答，再通过 JSON 导入，尚未接通自动推理服务。会话已看过原样本及推断标签，不作为独立盲测。请求哈希、分类及引用字段可由工具校验，解释中的自然语言仍需人工复阅。

## 接口和记录约定

三条命令均支持统一 --json 信封，相对路径按项目根目录解析。diagnose-waveforms / explain-waveforms 返回0表示分析完成，1表示有无法判定记录，2表示参数或执行错误。模型解释未导入时 explanation_status=pending，导入成功后为completed；分类完成状态与解释状态分别表达。

独立记录类型为 waveform_diagnosis，规则结构和分析方法版本均为1。manifest 保存来源、原数据包清单哈希、源码快照、产物哈希及状态。性能保持 not_evaluated，experiment_status 为 null。verify-diagnosis 默认只读，--write 才保存 verification.json；通用 verify 也支持该类型并沿用默认写入行为。复核从包内 CSV 重算分类和事件，并检查大模型请求与回答的关联，不重新运行大模型。

需要调整规则或重新解释时创建新结果目录；旧包保留。实际验证结果见[当前状态](validation.md)和[历史证据](validation-history.md)。
