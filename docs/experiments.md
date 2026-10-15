# RLC 参数扫描：模型、参数与指标

本页供执行 RLC 实验和核对结果的组员使用。实验通过一个可计算稳态参考值的电路，学习结构参数修改、Virtual HIL 采集、RMS 比较与参数扫描。具体操作见 [首次实验](first-experiment.md)。

## 模型与信号

模型来自安装包的 [RLC circuit 示例](<../../Typhoon HIL Control Center 2026.3/examples/models/basic electrical circuits/rlc circuit/rlc circuit.tse>)。项目使用 [模型](../models/rlc_filter.tse) 与 [SCADA 面板](../models/rlc_filter.cus) 的副本，来源和 SHA-256 见 [origin.json](../models/origin.json)。

```text
Vs1 ── Rin ── I ──●── L ───── 地
                   │
                   └── R ── C ── 地
                  Va1：节点对地电压
```

L 与 R 串 C 两支路并联，Rin 位于源与并联网络之间。API 中组件为顶层 Rin、R、L、C；源为 Vs1，采集信号为 I、Va1。

| 对象 | 含义 | 基准值／单位 |
|---|---|---|
| Vs1 | 正弦电压源 | 10 V RMS、1000 Hz、0° |
| Rin | 输入串联电阻、扫描参数 | 5 Ω |
| R | RC 支路电阻 | 0.1 Ω |
| L | 并联电感 | 10 µH |
| C | RC 支路电容 | 500 µF |
| I | 源电流 | A |
| Va1 | 节点对地电压 | V |

## 配置与采集

使用 [基准配置](../configs/rlc_baseline.json) 或 [扫描配置](../configs/rlc_sweep.json)，更改任务时另存配置。

| 字段 | 含义 | 基准值 |
|---|---|---:|
| source.rms_v | 输入源有效值 / V | 10 |
| source.frequency_hz | 频率 / Hz | 1000 |
| source.phase_deg | 相角 / ° | 0 |
| circuit.rin_ohm | 输入电阻 / Ω | 5 |
| circuit.branch_r_ohm | RC 支路电阻 / Ω | 0.1 |
| circuit.l_h | 电感 / H | 1e-5 |
| circuit.c_f | 电容 / F | 0.0005 |
| capture.settle_s | 采集前至少等待的仿真时间 / s | 0.05 |
| capture.duration_s | 采集窗口长度 / s | 0.02 |
| capture.sample_rate_hz | 请求采样率 / samples/s | 20000 |
| capture.wall_timeout_s | 墙钟等待上限 / s | 60 |
| acceptance.relative_rms_error | RMS 相对误差上限 | 0.03 |
| acceptance.min_samples | 最小样本数 | 256 |

修改 Rin、R、L、C 时，执行器回读属性，保存模型副本并重新编译。加载后设置正弦源并回读 RMS、频率和相角。源 API 的 rms 表示有效值，例如 10 V RMS 对应峰值约 14.142 V。

等待与采集窗口均按仿真时间定义，实际采集起点以返回的触发时刻为准。请求窗口必须覆盖至少五个完整源周期，每周期至少 20 个样本。基准的 20 ms 覆盖 20 个周期，按 20 kHz 采样对应 400 点；相邻点间隔为 50 µs，首末点跨度为 19.95 ms，N·Δt 窗口为 20 ms。

原始列为 t_relative_s、t_simulation_s、I_A、Va1_V。UTC 触发时戳若为空则保留空值，使用仿真时间列定位窗口。

## 稳态参考与判据

令角频率 ω=2πf，采用 RMS 相量：

```text
ZL  = jωL
ZRC = R + 1/(jωC)
Zp  = (ZL × ZRC)/(ZL + ZRC)
I   = Vs/(Rin + Zp)
Va1 = I × Zp
```

I 与 Va1 的解析 RMS 为相量的模。参考建立在线性理想 L、C 和正弦稳态条件下；对应拓扑为 Rin 串联 [L 并联 (R 串 C)]。

对全部原始采样计算：

```text
RMS(x) = sqrt(mean(x[k]^2))
relative_error = abs(measured - reference)/abs(reference)
```

配置要求电流与电压 RMS 的相对误差均不超过 3%。同时检查样本数、实际采样率、窗口长度、采样条件和采集前等待时间。达到等待时刻与满足稳态假设需要结合波形、周期覆盖和误差共同核对。

分析拒绝缺列、非有限数、重复或倒序时间、缺失采样和不一致的两套时间坐标。原始样本不做滤波、平滑或插值。参考接近零的其他实验应另外定义绝对误差判据。

## 输入电阻扫描

扫描配置增加以下字段片段：

```json
"sweep": {
  "parameter": "rin_ohm",
  "values": [1, 5, 10]
}
```

sweep 支持 rin_ohm，取值须互不相同，最多 12 个工况。每个工况单独修改模型、编译并运行，其余源与元件参数保持一致。

比较各工况的实测 RMS、解析参考、误差和状态，再依据 |Rin+Zp| 解释变化。不要把指定频率下的观察直接推广到其他电路或频率。

## 核对输出

单次运行保存原始 CSV、采集元数据、指标、清单、代码快照、图与报告；扫描保存各子工况及 comparison.csv、comparison.png。用 verify 复算，实际验证状态与示例结果见 [验证页面](validation.md)。

接口依据：[Schematic API](<../../Typhoon HIL Control Center 2026.3/Documentation/html/schematic_api.html>)、[HIL API](<../../Typhoon HIL Control Center 2026.3/Documentation/html/hil_api.html>)。其他实验可从 [README](../README.md#选择实验) 选择。
