# 现场数据接收、时间关联与离线判定

本文面向样机采集、联调和数据维护人员。目标是将同一次测试的 LIN、驱动、反馈和模型文件整理为可搬迁、可复算的记录，并按已确认的项目评价。工具只读输入文件，不连接设备。

## 从可运行样例开始

```powershell
.\lab.ps1 analyze-field-data --intake configs/field_demo_pass.json --input-dir data/field_demo --output-dir results/field-demo-pass --json
.\lab.ps1 verify-field-data --run-dir results/field-demo-pass --write --json
.\lab.ps1 analyze-field-data --intake configs/field_demo_fail.json --input-dir data/field_demo --output-dir results/field-demo-fail --json
.\lab.ps1 verify-field-data --run-dir results/field-demo-fail --json
```

输出目录必须是新目录，与输入目录互不嵌套。相对命令路径由项目根目录解析。两个样例使用相同的合成 CSV 和不同的示例阈值，分别预期通过与失败；失败记录仍应复核通过。样例说明见[数据说明](../data/field_demo/README.md)。打开输出目录的 `report.html` 即可离线阅读。

真实文件从 [现场清单模板](../configs/tle9877_field_intake.template.json) 另存一份修改。模板保留未知单位、事件和阈值；实际数据按[采集交接说明](tle9877-data-collection.md)准备。

## 清单及三类输入

顶层为 `schema_version=1`、`dataset_id`、`purpose`、非空 `sources`，以及可选 `ldf`、`events`、`criteria`、`references`。`ldf` 为相对输入目录路径；不填时使用项目已归档的样机 LDF。两种方式都会把 LDF 保存到结果包并据其重算，不使用缓存解码字段。本版本适用于已接收 TLE9877 板的三个业务帧，不是任意 LDF 通用导入器。

每个来源需填写：

| 字段 | 含义 |
|---|---|
| id / file / format | 唯一英文标识、相对输入目录的原文件路径、`waveform_csv` / `lin_csv` / `lin_jsonl` |
| source_kind | `physical` / `virtual_hil` / `mock` / `synthetic` / `unconfirmed`；按实际来源填写 |
| provenance | `{value, status, source}`，说明数据来源、确认状态和依据 |
| device / metadata | 设备及版本、测点、量程、探头、采样和导出设置等；未知内容留空 |
| encoding / delimiter / skip_rows | 编码默认 `utf-8-sig`；CSV 分隔符默认逗号，另支持分号或制表符；可跳过已明确的说明行 |
| time | `field` 指定时间列或 JSONL 字段路径，`unit` 为元信息对象，`clock_domain` 为时钟标签，`max_gap_s` 为可选采样缺口上限 |
| alignment | 有同步依据时填写显式时间变换，否则为 null |
| signals / columns | 数值 CSV 的信号映射 / LIN CSV 的原始帧列映射 |
| detail_window_s | 可选局部图范围，使用本来源换算为秒后的时间轴 |

元信息对象统一为 `{ "value": "ms", "status": "confirmed", "source": "仪器导出设置及记录编号" }`。状态还可为 `inferred` 或 `unconfirmed`；本入口仅将 confirmed 的单位用于物理量计算，其余保留原始值。来源声明和文件一致性不能相互替代。

### 多通道数值 CSV

需要表头。每项 `signals` 包含 `id`、`column`、`role`、`unit`，可附测点。`role` 区分 requested_speed、encoded_speed、board_target_speed、board_speed、model_speed、gate、feedback_voltage、current、model_response、other。

支持 V/mV、A/mA、rpm/RPM/rad/s、Nm、1、degC；统一转换为 V、A、rpm 等。机械转速换算为 `rad/s × 30/π`。`scale` 和 `offset` 默认 1、0；非默认值必须填写 `conversion_basis`，换算顺序为 `(原值 × scale + offset) × 单位比例`。探头倍率不会自动应用，已补偿的导出值不要重复补偿。

允许非均匀采样。时间须严格递增；空值、非有限值、缺列和转换溢出形成质量问题，原件及行序保留。声明 `time.max_gap_s` 后，超限缺口会记录并在图上断开。未知单位使用原始数值绘图，不套用秒窗口或阶段线。

### LIN 帧 CSV

`columns` 明确指定 direction、identifier、identifier_kind、data、checksum、driver_status 的实际列名；时间列由 `time.field` 指定。例如：

```csv
time_s,direction,identifier,identifier_kind,data,checksum,driver_status
0.000,tx,0xA6,pid,64 00,0xF4,ok
0.001,rx,0x25,pid,64 64 5A 50 0A 00 00 00,0x5D,ok
```

direction 为 tx/rx，identifier_kind 为 id/pid，标识符和校验用十进制或带 `0x` 的十六进制整数，data 为两位十六进制字节串。空 checksum 标为 unverified，不用于派生有效测量值。driver_status 为 ok 才按有效帧处理；错误、超时、未知 ID 和无效字段均保留。PID、校验政策还需结合实际固件抓包确认。

### 现有 LIN JSONL

直接导入 `lin-mock` 的 `bus.jsonl`，`time.field` 显式选择 `session_time_s` 或 `raw.device_time_s`。没有设备时间戳的行不会回退到主机时间。生命周期事件与原始错误保留；解码从 raw 重算，不信任日志中已有的 decoded。

请求转速若原日志没有记录，保持缺失；可另外提供有明确来源的数值 CSV。编码值来自控制帧，Setspeed 和 ActualSpeed 分别为板卡回报目标和板卡回报转速。TX 完成只表示本机发送记录，不证明板卡收到。

## 时间关联与事件

`clock_domain` 是来源标签，单独同名不会自动同步。共享已确认时钟时，可显式填写相同 alignment.group、scale=1、offset_s=0，并写明依据。其他已确认关联使用：

```json
{"group":"test1","scale":1.00001,"offset_s":-0.01,"uncertainty_s":0.0001,"valid_range_s":[0,10],"basis":"同步触发记录及偏差测量"}
```

变换为 `t_common = scale × t_source_seconds + offset_s`；有效范围外不关联。uncertainty_s 是变换到共同时间轴后的误差上界。无依据时保留 null，分别出图。不同来源的开始时间、主机写文件时间或相似波形不能充当同步证据。

events 每项包含 id、label、source_id、time_s、confirmed、basis。time_s 属于指定来源换算为秒后的原时间轴，正常运行、停止和恢复分别记录。停止必须是明确的操作事件，不由零速报文、断 LIN 或关闭适配器推断。

## 可配置判据

公共字段为 id、type、signal（`来源.信号`）、window_s、confirmed、basis、max_gap_s、min_samples（默认 3）。窗口及 max_gap_s 使用信号来源换算为秒后的原时间轴。缺少依据、窗口、阈值、有效单位、足量样本或覆盖时，返回 not_evaluated 和具体原因。来源存在质量问题时先检查原始行，不据此判通过。

| type | 额外字段 | 计算 |
|---|---|---|
| speed_tracking | target_rpm、max_error_rpm | 固定目标下窗口内最大 `abs(实测转速−目标)`；响应来源须为 board_speed 或 model_speed |
| max_current | limit_a | 窗口内最大 `abs(电流)`，要求 current 角色及 A 单位；不从反馈 mV 自动推电流 |
| stop | event_id、threshold_rpm、deadline_s、hold_s、max_time_uncertainty_s | 明确事件后，截止时间内进入绝对转速阈值，并有连续记录样本保持给定时长 |

停止窗口须覆盖事件、截止时间及完整保持区间。无时间变换时，持续时间按来源秒计算；存在有效 alignment 时，deadline_s、hold_s 和不确定性按其修正后的共同秒计算。跨来源事件要有共同 group，组合误差不得超过指定上限。响应时间给出相邻采样及同步误差构成的区间，区间跨越截止边界时保持未评估，不插值出一个通过时刻。保持时长是对记录样本的检查，不证明采样点之间的连续物理状态。

## 结果、退出码与复核

| 结果项 | 含义 |
|---|---|
| data_quality_status | 原始数据结构、时间及值是否通过检查 |
| analysis_status | 描述性分析 completed / incomplete；独立于判据是否齐备 |
| criteria_status | 已配置项目的 passed / failed / not_evaluated，失败优先；全部项目通过才汇总通过 |
| performance_status | 仅在判据所用来源均声明为 physical 且来源已确认时汇总；其他情况保持 not_evaluated |
| record_status | 执行复核后才填写；复核一致不改变原判据结果 |

分析返回 0 表示处理完成且没有失败，1 表示质量或已执行判据失败，2 表示配置、调用或执行错误。判据缺失可完成整理并返回 0；这不等于测试达标。复核仅按记录一致性返回 0/1。CLI 信封 experiment_status 始终为 null，不冒充设备执行器。

结果包包含 intake/provenance、原始 inputs、normalized、metrics、代码快照、Markdown/HTML/PNG、plot-index、manifest；显式 `--write` 才新增 verification。未知版本停止复算，不执行保存的代码。搬迁后可从包内原件和 LDF 复核。重新分析使用新目录，现有两列 CSV 工具及历史记录保持原用途。

图表保留完整导出与显式局部窗口；颜色配合线型、缺失和声明的缺口保留断点，原始数据可从报告链接访问。图表设计参照 Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026), [Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents](https://arxiv.org/abs/2609.00065)。
