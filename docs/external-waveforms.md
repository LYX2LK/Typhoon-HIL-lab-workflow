# 外部波形接收、分析与复核

供数据接收人员与项目维护者使用。通过显式数据清单接收两列 CSV，保留原始字节，生成描述性分析与可搬迁的证据包。Agent 的任务判断见 [外部数据 Skill](../.agents/skills/external-test-data-intake/SKILL.md)。

## 输入与运行

当前支持 UTF-8（可含 BOM）、逗号分隔、恰好两列数值的 CSV，可声明一行表头和两列次序；PNG 为可选来源附件。至少三个样本，数值有限、时间严格递增且间隔均匀。时间单位支持 s/ms/us/ns，幅值支持 V/mV/A/mA；计算转换为 s、V 或 A，原始文件与图中坐标保留输入单位。PNG 仅复制留证，工具不自动识别截图内容或验证配对。

使用安装配套 Python 的统一入口；相对命令路径按项目根目录解释：

```powershell
.\lab.ps1 analyze-waveforms --intake configs/external_tu_intake.json --input-dir ../docs/tu/tu --output-dir results/填写新的接收目录 --json
.\lab.ps1 verify-waveforms --run-dir results/本次实际目录 --write --json
```

输出目录须不存在，与输入目录分离且互不嵌套。默认复核不写文件；本次新结果加 `--write` 保存 verification.json。旧脚本保留为薄入口，但现在也要求显式传入 `--intake`；历史报告和未执行的 checks.ipynb 保持原样。

## 数据清单

[当前 tu 清单](../configs/external_tu_intake.json)保存该批次人工读取的截图信息、来源状态和原计算参数。另一批数据另建清单，不根据文件名选择算法或推断单位。顶层包含 schema_version=1、dataset_id、purpose 和非空 records。

每条 record 的字段如下；未列出的字段会被拒绝，避免参数被静默忽略：

| 字段 | 约定 |
|---|---|
| id | 唯一字母、数字、下划线或连字符标识 |
| csv / image | 相对输入目录的 CSV / 可选 PNG 路径，使用 /；不允许越界或绝对路径 |
| format | encoding 固定 utf-8-sig；header 为布尔值；time_column 与 value_column 为不同的 0/1 |
| metadata | time_unit、value_unit、measurement_point、channel、probe_ratio、trigger、label、acquisition、export、image_pairing |
| analysis | method 为 summary/dip/rise；window 为 null 或两个递增端点；对应特征参数见下节 |
| detail_window | 可选局部图窗口；两个递增端点 |

metadata 的每项为 `{"value": ..., "status": "confirmed/inferred/unconfirmed", "source": "依据"}`。已确认或推断值必须提供依据；缺少单位或单位未确认时，只交付原始数值范围和结构检查。未确认状态下的候选值不参与物理量计算。acquisition 可包含 sample_rate_hz、record_points 等来源事实。采集率与 CSV 网格率单独比较，数值一致也不证明采集和导出过程一致。探头倍率仅记录，不自动补偿。

## 方法与适用条件

analysis.window 和 detail_window 均使用输入时间单位；null 表示完整导出范围。结构检查总是覆盖全部采样。全程统计与特征计算窗口分别记录；窗口至少需要三个样本。

- summary：全程范围、均值和总体标准差等统计，不使用平台假设。
- dip：要求正的起始基准。baseline_fraction 指定起始样本比例（0 至 0.5，左端不含），以其样本中位数为基准；drop_fraction 在 0 与 1 之间，阈值为基准乘以 1−drop_fraction。计算最大下降、低于阈值的样本数和最长连续区段。样本支撑时长为样本数乘以间隔，另列首末样本时刻。
- rise：baseline_fraction 指定首尾样本比例，中位数作为低、高参考；要求末尾参考高于起始参考。low_fraction 与 high_fraction 满足 0＜low＜high＜1。记录首次向上穿越的相邻样本区间、两次穿越间隔、期间最大回落和全分析窗口最大单步下降。无法取得先后可分辨的穿越时标为 not_applicable。

当前 tu1/tu2 使用 10% 起始中位数、5% 跌落；tu3/tu4 使用首尾 10% 中位数、10%/90% 首次穿越。端点参考是描述性定义，不证明物理稳态平台；首次穿越间隔不代表完整响应过程。方法不适用时保留原因，图表不平滑、插值或跨文件对齐。

间隔舍入容差为 max(1e-15 s, 中位间隔的 0.01%)，已知时间单位时换算检查；未知单位时在原始时间数值上使用 max(1e-15, 中位间隔的 0.01%)，不宣称物理时间精度。

## 证据包与状态

| 文件 | 用途 |
|---|---|
| intake.json / provenance.json | 规范化输入映射、原清单、来源路径和哈希；元信息状态保留 |
| inputs/ | CSV/PNG 的原始字节副本，支持离开源机器后复核 |
| profile.json | 全程统计、所选方法与窗口、结果、失败或未计算原因 |
| 每个记录 id 对应的 PNG / report.md | 完整导出及可选局部图、当前结果与来源限定 |
| code_snapshot/ / manifest.json | 分析与报告代码、记录和方法版本、必须产物的哈希 |
| verification.json | 显式保存的复核结果；默认只读复核不生成 |

外部记录类型为 external_waveforms，沿用项目哈希与版本机制。复核检查必需产物、来源映射及方法版本，再使用当前兼容实现从包内 CSV 重算。数值比较容差为相对 1e-10、绝对 1e-12；未知版本停止复算，旧代码快照不自动执行。原始来源真实性仍依赖清单中的依据，文件一致性检查不替代来源确认。

data_quality_status 表示结构质量；analysis_status 表示所选分析是否完成；record_status 表示记录与复算是否一致；performance_status 当前固定 not_evaluated。损坏数据或方法不适用可以形成一致的失败记录。

analyze-waveforms 返回 0 表示描述性分析完成，1 表示质量失败或分析不完整，2 表示调用、清单或执行异常。verify-waveforms 返回 0 表示记录一致，1 表示复核失败；不会据此提升数据质量或性能状态。JSON 信封的 experiment_status 保持 null，外部数据状态位于 result 中。通用 verify 也识别此记录类型，但默认写入复核文件；本流程优先使用只读的 verify-waveforms。报告更新通过新建分析目录完成。

## 后续用途

转入实验时移交清单、结果目录与复核、用途、已确认条件及待补条件。回放需确定注入位置、接口、关键幅值/边沿/持续时间和允许误差，再交由 [模型接入流程](model-integration.md)实施。

原 tu 数据的测点、倍率、标签与采集/导出关系仍待提供方确认。具体批次证据见 [验证历史](validation-history.md)，水泵需求见 [专题记录](pump-hil-intake.md)。
