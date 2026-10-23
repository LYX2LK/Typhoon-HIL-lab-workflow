# 光伏电站 HzWatt 稳态特性

本案例面向有电力电子基础的读者，观察电网处于额定频率和过频工况时，光伏电站模型的稳态有功是否符合参考曲线。两工况分别独立启动，改变的变量是电网频率。

## 运行与结果核对

模型标识为 generic_pv_plant，案例标识为 pv_hzwatt。在项目根目录执行：

```powershell
.\lab.ps1 prepare-models
.\lab.ps1 validate-case --case pv_hzwatt --json
.\lab.ps1 run-case --case pv_hzwatt --json
```

按返回的实际批次目录执行 verify、report、verify。批次中的两个子目录分别保存 50 Hz、51 Hz 的原始数据、模型副本、配置、指标和报告。

| 工况 | 电网频率命令 | 参考有功 | 固定条件 |
|---|---:|---:|---|
| 额定频率 | 1 pu = 50 Hz | 250 kW | HzWatt、250 kW 额定功率、opc_pu=0.3 |
| 过频 | 1.02 pu = 51 Hz | 170 kW | 同上 |

每次启动等待 12 s 仿真时间，再以 10 kHz 采集 2 s。所有采样点参与 1% 误差判定，频率反馈、使能、功率参考与报警状态一起核对。来源及完整定义见[判据](acceptance.md)。以 verification.json 的 record_status 判断记录一致性，以 experiment_status 判断工况是否达标。

## 接口与适配方式

官方模型从匹配的 THCC 安装按哈希准备，作为本机依赖。原模型默认模式为 LVRT，适配器在每次运行的副本中改为 HzWatt，并回读核对参数；初始化的 SCADA 命令也保存读回结果。

| API 信号（前缀 PV Power Plant (Generic) UI1.） | CSV 列 | 单位/含义 |
|---|---|---|
| Pmeas_kW | ActivePower_kW | 有功 kW |
| Pref_fb_kW | PowerReference_kW | HzWatt 前的限额参考 kW |
| Fmeas_Hz | Frequency_Hz | 频率 Hz |
| Enable_fb | Enable | 使能状态 |
| alarm_msg | AlarmCode | 报警码 |
| Qmeas_kVAr | ReactivePower_kVAr | 无功 kVAr，作为辅助观测 |

电网命令使用 Grid UI1.Grid_freq_cmd，单位为额定 50 Hz 的 pu。适配器支持官方表中的 0.985、0.996、1.0、1.02 四个离散频率点；本案例实测后两点。接口声明的参数范围仍需结合实际配置、模型条件和运行证据使用。

新增部分是模型适配器、对应分析与报告；模型准备、串行执行、采集、案例索引和记录复核继续使用公共流程。该案例覆盖微电网方向的单个光伏子系统。动态频率变化、多控制器协同、EMS 和实体 HIL 按后续具体任务验证。当前实测见[验证状态](../../docs/validation.md)。
