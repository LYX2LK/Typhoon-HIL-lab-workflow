# Boost 闭环动态实验

本页介绍参考跟踪和抗输入扰动实验的执行方法，以及实际事件、输出误差与调节时间的核对方法。阅读前需具备电力电子基础。先完成 [环境检查](environment.md)，统一入口的操作与结果核对见 [首次实验](first-experiment.md)。

## 模型与测量点

模型来自 THCC 2026.3 安装包的 `general power electronics/boost closed loop`。通过 `prepare-models` 准备本机 `models/boost_closed_loop.tse`、`models/boost_closed_loop.cus` 字节副本，Git 保存 [来源哈希](../models/origin.json)，每次运行使用结果目录中的模型副本。

PI 控制器根据输出电压与参考的差值调节 Boost 的内部 PWM。教学模型同时采集输出电压 Vout、输入电流 Iin、控制器实际参考 ReferenceApplied 和输入电压 VinMeasured，以便把激励与响应对应起来。

| 项 | 基准值／行为 |
|---|---|
| 输入源 Vin | 35 V，恒定电压源 |
| 初始参考 Reference | 50 V |
| PWM Enable | 初始化为 1 并回读 |
| 电感 L、串联电阻 RL | 1 mH、0.1 Ω |
| 电容 C、ESR | 810 µF、0.001 Ω |
| 主负载 R1 | 100 Ω |
| 附加支路 R2、Load | 25 Ω；开关断开并回读 |
| PI 参数 | P=0.0005，I=0.1，积分器初值 0.5 |
| 控制周期、电气步长 | 100 µs、0.5 µs |

运行副本使用 LabReferenceStep 与 LabReferenceSum 生成参考事件，ReferenceApplied 测量实际参考，VinMeasured 测量源两端电压。原面板的 Reference 输入表示初始参考；读图与算指标时使用实际参考探针。

## 选择工况与判据

| 配置 | 激励 | 教学判据 |
|---|---|---|
| boost_baseline.json | 输入 35 V、参考 50 V，保持不变 | 最终稳态相对误差 ≤2% |
| boost_reference_step.json | 0.5 s，参考 50→60 V | 最终误差 ≤2%；超调／10 V ≤5%；调节时间 ≤0.5 s |
| boost_vin_drop.json | 0.5 s，输入 35→28 V，参考保持 50 V | 最终误差 ≤2%；最大输出偏差／50 V ≤10%；恢复时间 ≤0.5 s |
| boost_vin_rise.json | 0.5 s，输入 35→38.5 V，参考保持 50 V | 与输入跌落相同 |

四份配置均采集 0～1.5 s，请求 10 kHz、15,000 点，墙钟等待上限为 180 s。动态工况要求事件前 0.1 s 的输出均值相对初始参考误差 ≤2%。这些数值是运行前确定的教学判据。

## 运行并复核

在项目根目录执行模型检查，然后运行所选配置；完整比较使用以下四个工况：

```powershell
.\lab.ps1 inspect --model boost_closed_loop
.\lab.ps1 run --config configs/boost_baseline.json
.\lab.ps1 run --config configs/boost_reference_step.json
.\lab.ps1 run --config configs/boost_vin_drop.json
.\lab.ps1 run --config configs/boost_vin_rise.json
```

分别记下每个 run_dir，再核对和重建其报告：

```powershell
.\lab.ps1 verify --run-dir 'results/本次实际目录'
.\lab.ps1 report --run-dir 'results/本次实际目录'
.\lab.ps1 verify --run-dir 'results/本次实际目录'
```

先确认事件实际发生，再读输出判据。事件未生效、错时或电平不符属于 error；事件和数据有效但性能超出判据属于 failed。记录复算一致与性能达标分别查看 record_status、experiment_status。已验证结论与实际报告见 [验证状态](validation.md)。

## 事件与采样时间

参考变化由模型内 Step 执行，输入电压扰动通过源的 executeAt 按仿真时间排程。参考通道的内部触发提前一个 100 µs 控制周期，以补偿 LabReferenceSum 的传播；内部触发与补偿量都留在记录中。维护信号处理链时按 [模型接入方法](model-integration.md) 重新验证时序。

分析从 ReferenceApplied_V 或 VinMeasured_V 中找首次跨过变化前后电平中点的样本，核对前后电平、调度时刻和相邻样本检测区间。检测区间为 `(前一未变样本时刻, 首个已变样本时刻]`，左开右闭；events.json 的二元数组仅保存这两个端点。默认分辨率为 100 µs，电平容差为 0.0001 V。监测电平检查的初始化排除时长在指标记录中说明，原始样本全部保留。

采集首点以实际触发时间为准，可能从一个电气步长开始。events.json 保存首次变化样本和检测区间；capture.json 保存采样率与触发元数据。UTC 触发时戳若为空则保留空值。

## 指标与分析窗口

最终稳态窗口为 [1.4,1.5) s，事件前窗口为 [0.4,0.5) s。自定义实验时，窗口随配置中的长度与边界确定。

| 指标 | 计算口径 |
|---|---|
| 带符号稳态误差 | 最终窗口输出均值减最终参考 |
| 稳态相对误差 | 带符号误差的绝对值／最终参考绝对值 |
| 参考超调 | 沿参考变化方向超过最终目标的最大量／参考阶跃幅值；未超出时为零 |
| 调节／恢复时间 | 从实际事件首变样本计时，取输出进入最终参考 ±2% 带并保持至观测末尾的最早样本 |
| 扰动最大偏差 | 事件后输出与目标的最大绝对差／目标绝对值 |
| 输入电流 | 全采集窗口均值、最终窗口均值、绝对采样峰值 |

末尾仍未恢复时，调节／恢复时间为 null，并保存原因和未通过判据。全窗电流指标包含启动过程；采样峰值描述当前采样点，受采样率限制。

CSV 列为 t_relative_s、t_simulation_s、Vout_V、Iin_A、ReferenceApplied_V、VinMeasured_V。分析拒绝缺列、非有限数、重复或倒序时间及缺失采样，不插值补齐。

报告的三个面板共享仿真时间轴，显示输出与实际参考、输入电流、输入电压，并标记事件、容差带和分析窗口。waveforms.png 保留完整启动过程；response_detail.png 明确显示事件区间局部视图。动态性能判据评价事件后的响应。

## 修改实验配置

复制相应 JSON 后修改参数，保留原基准配置。parameters 给出输入电压、初始参考与 PWM 使能；events 为零项或一项，包含 at_s、target、value。target 支持 reference_voltage_v 或 input_voltage_v。

事件时刻须对齐 100 µs，并留够事件前窗口、恢复观察时间和最终窗口。参考须高于输入电压且满足配置范围，PWM 保持使能。判据在运行前写入 acceptance。Boost 工况以独立 run 执行；RLC 参数扫描使用 sweep。

## 接口依据

- 安装包 Boost 测试：`examples/tests/118_boost_closed_loop/test_boost_closed_loop.py`，说明参考变化与输入扰动工况。
- 同版本 Step 说明：`typhoon/help/t-ug002/References/step.html`，说明按仿真时间切换电平。
- [官方 HIL API](https://www.typhoon-hil.com/documentation/typhoon-hil-api-documentation/hil_api.html)：源排程、初始化、采集与回读；本地同版本入口为 `Documentation/html/hil_api.html`。

上述本地文件路径均相对于 `doctor` 实际输出的 `typhoon_home` 安装根目录，定位方法见 [环境配置](environment.md#选择实验与资料)。
