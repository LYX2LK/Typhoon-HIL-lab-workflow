# 教学实验说明：RLC 参数扫描

实验目的：用一个可手算参考值的电路，学习 Typhoon 模型参数修改、Virtual HIL 仿真、波形采集、参数扫描和报告核对。读者应具备交流电路基础；Python 部分由统一入口执行。

模型来源为当前安装中的官方 [RLC circuit 示例](<../../Typhoon HIL Control Center 2026.3/examples/models/basic electrical circuits/rlc circuit/rlc circuit.tse>)，项目使用 [rlc_filter.tse](../models/rlc_filter.tse) 副本和 [rlc_filter.cus](../models/rlc_filter.cus) SCADA 面板；来源记录与文件校验信息见 [origin.json](../models/origin.json)。

## 电路和测量点

```text
Vs1 ── Rin ── I ──●── L ───── 地
                   │
                   └── R ── C ── 地
                  Va1：节点对地电压
```

`L` 支路与 `R` 串联 `C` 的支路并联；`Rin` 串接在电压源与并联网络之间。稳态计算应对应这套连接关系。

| 元件或信号 | 含义 | 原官方示例参考值或单位 |
|---|---|---|
| `Vs1` | 正弦电压源 | V RMS、Hz、相角 ° |
| `Rin` | 输入串联电阻，首个扫描参数 | 5 Ω |
| `R` | RC 支路串联电阻 | 0.1 Ω |
| `L` | 并联电感 | 1e-5 H，即 10 µH |
| `C` | RC 支路电容 | 0.0005 F，即 500 µF |
| `Va1` | 并联节点对地电压 | V |
| `I` | 源电流 | A |

教学配置采用 10 V RMS、1000 Hz 正弦源，扫描 `Rin = 1、5、10 Ω`，基准与三个工况均已通过本机实测判据。实际激励、工况及采集时间记录在 [基准配置](../configs/rlc_baseline.json)、[扫描配置](../configs/rlc_sweep.json) 和运行清单中；数值与证据见 [实测验收](validation.md)。

模型的 `HIL101`、`Pro 1` 是编译目标与配置。它们不表示本机连接了实体 HIL101；本版通过 Virtual HIL 模拟该目标。

## 配置字段与单位

查看现有 JSON 时，先核对字段单位，再调整数值。保留当前配置中的其他字段和判据：

| 字段 | 含义与单位 |
|---|---|
| `source.rms_v` | 输入源有效值，V |
| `source.frequency_hz` | 输入源频率，Hz |
| `source.phase_deg` | 初始相角，° |
| `circuit.rin_ohm` | 输入电阻，Ω |
| `circuit.branch_r_ohm` | RC 支路电阻，Ω |
| `circuit.l_h` | 电感，H |
| `circuit.c_f` | 电容，F |
| `capture.settle_s` | 启动后等待稳态的仿真时间，s |
| `capture.duration_s` | 采集时长，s |
| `capture.sample_rate_hz` | 请求采样率，samples/s |
| `capture.wall_timeout_s` | 等待执行完成的电脑时间上限，s |
| `acceptance.relative_rms_error` | 与解析 RMS 比较的允许相对误差 |
| `acceptance.min_samples` | 数据完整性检查所需最小样本数 |

当前基准配置设定：等待稳态 0.05 s，采集 0.02 s，请求采样率 20000 samples/s，电脑等待上限 60 s；RMS 相对误差阈值为 0.03（3%），最小样本数为 256。1000 Hz 下，20 ms 覆盖 20 个周期，按请求采样率约对应 400 点；实际数量与时间步长由 CSV 核对。400 点的首末采样点跨度为 19.95 ms，按点数乘采样间隔得到的采集窗口为 20 ms；指标记录同时提供这两个值。3% 是本版教学实验的数值核对阈值，新增课题应根据验证目的制定判据。

`settle_s` 和 `duration_s` 使用仿真时间；`wall_timeout_s` 使用电脑经过的实际时间。元件的 API 名称为顶层 `Rin`、`R`、`L`、`C`，源名称为 `Vs1`，捕获信号为 `I`、`Va1`。界面上的模型标题与这些组件名对应不同对象，脚本通过 `inspect` 确认实际组件属性。

扫描配置在相同结构中增加以下部分：

```json
"sweep": {
  "parameter": "rin_ohm",
  "values": [1, 5, 10]
}
```

这是完整配置中的一个字段片段。调整扫描时保留其余配置，只修改参数名和取值；本版首个扫描参数为 `rin_ohm`。

## 两类参数怎样生效

修改 `Rin`、`R`、`L`、`C` 等模型属性时，执行流程为：修改属性、保存模型副本、重新编译、加载编译产物。这样每次运行均能追溯到实际使用的模型。

加载后，电压源的正弦 RMS、频率和相角可通过 HIL API 设定。官方 [`set_source_sine_waveform`](<../../Typhoon HIL Control Center 2026.3/Documentation/html/hil_api.html#typhoon.api.hil.set_source_sine_waveform>) 的 `rms` 参数表示有效值；例如 10 V RMS 对应峰值约 14.142 V。

## 稳态解析参考

令角频率 `ω = 2πf`，采用 RMS 相量：

```text
ZL  = jωL
ZRC = R + 1/(jωC)
Zp  = (ZL × ZRC)/(ZL + ZRC)
I   = Vs/(Rin + Zp)
Va1 = I × Zp
```

`I` 与 `Va1` 的解析 RMS 为上述相量的模。这里的参考值描述正弦稳态。报告应注明实际用于计算 RMS 的时间区间，并检查采集数据是否进入稳态、是否覆盖足够的完整周期。

离散波形的 RMS 计算为：

```text
RMS(x) = sqrt(mean(x[k]^2))
relative_error = abs(measured - reference)/abs(reference)
```

当参考值接近零时，应使用明确的绝对误差判据。判定阈值、采样率、采集时长和稳态区间在配置或指标记录中明确，不由 Agent 根据图像估计。

## 基准和扫描分别检查什么

**基准实验**检查模型操作、加载、激励设定、实际采集和解析核对是否连贯；保存电流、电压波形和每项数值判据。

**扫描实验**逐个改变 `Rin`，保持激励和其他元件参数相同，分别编译并运行。汇总每个工况的电流、电压 RMS、解析参考值、误差及状态。理论比较可根据 `|Rin + Zp|` 随 `Rin` 的变化解释；结论注明当前模型和频率。

## 输出与状态

每次运行应保存 `config.json`、`model.tse`、`waveforms.csv`、`metrics.json`、`manifest.json`、`run.log`、`waveforms.png` 和 HTML/Markdown 报告。扫描目录包含各工况的 `cases/<case_id>` 和 `comparison.csv`、`comparison.png` 及总报告。阅读汇总时先看状态，再看数值：

| 状态 | 解释 |
|---|---|
| `passed` | 本次要求的执行与数值判据通过 |
| `failed` | 已完成相关执行，但一个或多个判据不满足 |
| `error` | 编译、加载、采集或分析过程出现执行异常 |
| `skipped` | 本项没有执行，记录中应给出原因 |

验收需保留真实仿真记录。解析值可用于交叉核对，但波形图和实验指标应来源于实际采集。本次 Virtual HIL 采集返回的 UTC 触发时间为空；CSV 用 `t_relative_s` 表示采集相对时间、`t_simulation_s` 表示仿真时间，电流、电压列为 `I_A`、`Va1_V`。使用这些时间列定位波形区间，使用运行清单中带时区偏移的执行时间定位实验记录。

操作步骤见 [首次实验](first-experiment.md)。接口依据见 [Schematic API](<../../Typhoon HIL Control Center 2026.3/Documentation/html/schematic_api.html>)、[HIL API](<../../Typhoon HIL Control Center 2026.3/Documentation/html/hil_api.html>) 及 [TyphoonTest 采集接口](<../../Typhoon HIL Control Center 2026.3/Documentation/typhoontest_html/api/typhoon.test.capture.start_capture.html>)。
