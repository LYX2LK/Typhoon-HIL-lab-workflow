# 双三相 PMSM 实测通道与工况参照

本文供诊断研发与数据接入人员使用，说明如何把 Brno 原始 MAT 记录转为保留原生通道的受限数值查询，以及如何选取对应工况的健康参照。原始数据来自[发布记录](https://zenodo.org/records/13889418)，试验装置及电流单位参照其关联的[电机论文](https://doi.org/10.1109/IECON49645.2022.9968364)。本地三相软件模型的操作见[研究命令](pmsm-research.md)。

## 接入和查询

在项目根目录运行，输出目录使用新路径。`--input-dir`指向已下载的原始 MAT 文件目录；当前解析器对应发布记录 13889418 的文件命名与字段结构。

```powershell
.\lab.ps1 pmsm-measured --action prepare --input-dir results/agent-tasks/20261115-190017-pmsm-case-sources-b3c7/sources/13889418/raw --output-dir results/pmsm-measured-example --json
.\lab.ps1 pmsm-measured --action verify --output-dir results/pmsm-measured-example --json
.\lab.ps1 pmsm-measured --action query --output-dir results/pmsm-measured-example --case-id M002 --query-file configs/pmsm_measured/reference_query.json --json
```

从生成的`dataset.json`查阅实际编号、开放通道、工况分段和健康参照编号。当前两文件包中 M001 是健康参照，M002 是待查记录；文件数量变化后以新包为准。查询文件包含工具名称与参数，例如：

```json
{
  "tool": "normal_reference",
  "arguments": {
    "channels": ["i1_q", "i2_q", "measured_speed_rpm", "reference_speed_rpm"],
    "window_s": [20, 20.5]
  }
}
```

`statistics`、`difference`、`availability`沿用[诊断数值查询](pmsm-research.md#诊断查询与证据更新)的参数结构，使用本页通道名和单位。`controller_knowledge`返回这套实测装置的说明。`events`仅查询`reference_speed_rpm`，按大于 0.001 rpm 的实际采样变化返回时刻和前后值，每个查询至多20项。这些事件是速度给定变化，故障投入时间没有从文件名推断。

同一实测包的批量离线分析可以调用 `pmsm_measured.query_measured_batch(output, queries)`；每个查询由案例编号、工具名和参数组成。批次开始时复核整个包，然后对各条记录按相同的工具权限和匹配策略计算。批量输出保留每个窗口的匹配状态、双方统计及原始时间范围。

## 通道与单位

所有投影保持原数值，比例为1、偏移为0。`Time`映射为`time_s`，单位秒；按原生10kHz时间轴检查递增、步长、样本数及有限值。

| 原始字段 | 查询通道 | 单位与含义 |
|---|---|---|
| `Currents_SubSys1_A/B/C` | `i1_a`、`i1_b`、`i1_c` | A，子系统1三相电流 |
| `Currents_SubSys2_A/B/C` | `i2_a`、`i2_b`、`i2_c` | A，子系统2三相电流 |
| `Currents_SubSys1_d/q` | `i1_d`、`i1_q` | A，子系统1发布的dq电流 |
| `Currents_SubSys2_d/q` | `i2_d`、`i2_q` | A，子系统2发布的dq电流 |
| `Voltage_SubSys1_d/q` | `v1_d_control`、`v1_q_control` | `native_control_voltage`，子系统1的电压控制量 |
| `Voltage_SubSys2_d/q` | `v2_d_control`、`v2_q_control` | `native_control_voltage`，子系统2的电压控制量 |
| `Speed_rpm` | `measured_speed_rpm` | rpm，测得机械速度 |
| `Speed_requred_rpm` | `reference_speed_rpm` | rpm，要求的机械速度；保留原字段的拼写映射 |
| `Speed_rad_el` | `measured_electrical_speed` | rad_e/s，测得电角速度 |
| `Speed_requred_rad_el` | `reference_electrical_speed` | rad_e/s，要求的电角速度 |
| `SinCos_Electrical_Sin/Cos` | `electrical_sin`、`electrical_cos` | 1，电角度的正弦与余弦 |

电流的物理量由仓库说明确认，关联论文的实测图使用A；发布包未附逐通道标定表。dq量保留原变换约定，不从三相量重新计算，也不跨坐标直接相减。dq电压的控制量语义已确认，导出倍率仍待确认，因此保留原生单位；取得标定依据后再新增有版本的V单位投影。

电角速度与机械速度分别保存，并用论文给出的10极对关系交叉检查：`ωe = rpm × π/30 × 10`，数值误差要求不超过0.01rad_e/s。查询差值要求单位一致；不同相别或坐标的电流差值拒绝执行，可分别查询统计量。

`load_setpoint_nm`是文件名与发布说明中的测功机负载设定，属于工况元信息。测得转矩、独立模型速度、控制器使用的速度反馈及限幅标志均未记录；查询缺失项返回不可用。

## 健康参照如何匹配

每份完整记录建立互不重叠的0.5秒窗口。窗口保存速度给定的均值、范围、拟合斜率、实际变化次数、累计台阶量、距上次已观测变化的时间，以及初始未观测变化、变化中、变化后保持等阶段。

`normal_reference`接收0.5秒目标窗口，只从另一份已标为健康的源记录中选择参照。以下条件同时满足后，按速度与斜率的归一化差异选择最接近的窗口：

- 同一发布装置、拓扑和负载设定；阶段、加减速方向与给定变化次数相同。
- 给定均值差不超过`max(5rpm, 目标均值绝对值×3%)`。
- 拟合斜率差不超过`max(5rpm/s, 目标斜率绝对值×10%)`；方向划分阈值为±2rpm/s。
- 两侧均无此前变化，或距此前变化的时间差不超过50ms。
- 累计台阶量之差不超过`max(1rpm, 目标累计台阶量绝对值×5%)`。

返回目标与健康窗口各自的原始统计、条件差异及均值/RMS/峰峰值的统计差。没有合适参照时返回`unavailable`。当前阈值是开发查询的匹配策略，保存在`reference_policy`中，后续应在不同负载与独立批次上检查敏感性。

匹配不改变两份记录的时间轴，不作逐点相减。来源记录数与候选窗口数分别返回；同一健康记录的多个窗口仍只有一个记录来源，记录之间的统计独立性需另行确认。低速下0.5秒可能不足一个电周期，窗口RMS仅描述该段采样，跨工况诊断需检查电周期覆盖。

## 证据与复核

包内保留原始MAT副本、下载回执、仓库元数据、匿名NPZ观测、通道定义、工况索引、源文件摘要及执行代码快照。文件名中的故障标签放在`private.json`和源文件区；模型接收的数值查询结果不枚举这些路径。数据包由研究人员保管，受限工具不提供任意文件访问。

`verify`核对文件摘要、仓库校验和、MAT到全部通道的逐点一致性、工况复算及健康参照来源。JSON返回中的`record_status`表示记录一致性，`experiment_status`为空；数据包复核不提供实体性能判定。

当前包供开发查询使用，正式诊断比较还需补充标定依据、不同负载/严重度和独立留出批次，并固定任务与评价规则。实际接入与本地电流反馈实验见[验证记录](validation-history.md)。
