# 验证状态与实测结论

本页维护工作流已验证的能力、实验判据结果和待验事项，供使用者判断实验输出的适用范围。最近一次完整验证日期为 **2026-10-15**，模式为 THCC 2026.3 Virtual HIL。按日期查找其他记录，见 [验证记录索引](validation-history.md)。

脚本与记录检查通过。RLC 基准、扫描及 Boost 基准、参考阶跃满足预设判据；两项 Boost 输入扰动的最大输出偏差超出 10%，实验为 failed。组员独立复现仍待执行。

## 已验证能力

| 项目 | 结论与依据 |
|---|---|
| 环境 | Python 3.11.4、Typhoon-HIL-API 1.32.1、TyphoonTest 1.35.6；见 [环境快照](../results/20261015-112422-v2-validation-dd212b/environment.json) |
| 脚本逻辑 | [完整测试](../results/20261015-112422-v2-validation-dd212b/unit-tests.json) 54 项通过，失败、错误、跳过均为 0；[日志](../results/20261015-112422-v2-validation-dd212b/unit-tests.log) |
| 运行与记录 | 最小回环、两个模型的全部指定工况均实际执行；七项最终记录复算一致，配置、模型、CSV 与指标保持不变，见 [核验记录](../results/20261015-112422-v2-validation-dd212b/final-checks.json) |
| 模型属性 | [核对记录](../results/20261015-112422-v2-validation-dd212b/model-preservation.json) 确认 Boost 官方元件属性及 PI 参数保留，教学参考与监测组件的改动范围可查 |
| 数值与图表 | [独立数值复核](../results/20261015-112422-v2-validation-dd212b/independent-numeric-audit.json) 与分析指标一致；[图表核对](../results/20261015-112422-v2-validation-dd212b/plot-qa.json) 包含原始全程和动态细节 |
| 既有记录兼容 | 在已保存 RLC 记录副本上完成 verify→report→verify，原目录哈希未变，见 [兼容检查](../results/20261015-112422-v2-validation-dd212b/historical-compatibility.json) |

脚本测试、实际 Virtual HIL 运行和人员独立复现是不同的验证项目。HIL101、Pro 1 表示编译目标与配置；本页的运行证据对应 Virtual HIL。

## 实际运行与记录复核

| 实验 | 实验状态 | 记录一致性 | 实际产物 |
|---|---|---|
| 最小回环 | passed | passed | [记录](../results/20261015-113018-smoke-903d97/manifest.json) |
| RLC 基准 | passed | passed | [记录](../results/20261015-113040-rlc-ea344a/report.html) |
| RLC 三工况扫描 | passed | passed | [记录](../results/20261015-113104-sweep-1a2086/report.html) |
| Boost 基准 | passed | passed | [记录](../results/20261015-113207-boost_closed_loop-e9ac14/report.html) |
| Boost 参考阶跃 | passed | passed | [记录](../results/20261015-113237-boost_closed_loop-9e116c/report.html) |
| Boost 输入跌落 | failed | passed | [记录](../results/20261015-113307-boost_closed_loop-caf1cc/report.html) |
| Boost 输入升高 | failed | passed | [记录](../results/20261015-113336-boost_closed_loop-ec9253/report.html) |

record_status 表示文件与指标复算是否一致，experiment_status 表示实验执行和性能判据的结果。记录一致而性能未达标时，总 status 为 failed，verify 退出码为 1。

## RLC 数值核对

条件为 10 V RMS、1000 Hz、0°；Rin=5 Ω、R=0.1 Ω、L=10 µH、C=500 µF。实际采集 400 点、20 kHz，按全部捕获样本计算 RMS；允许相对误差为 3%。公式与窗口定义见 [RLC 说明](experiments.md)。

| 信号 | 实测 RMS | 解析 RMS | 相对误差 | 状态 |
|---|---:|---:|---:|---|
| 电流 I / A | 1.997625439 | 1.997672528 | 0.002357% | passed |
| 节点电压 Va1 / V | 0.152952070 | 0.152645824 | 0.200626% | passed |

| Rin / Ω | 电流 RMS / A | 节点电压 RMS / V | 电流相对误差 | 电压相对误差 | 状态 |
|---:|---:|---:|---:|---:|---|
| 1 | 9.918259404 | 0.759365298 | 0.010922% | 0.186041% | passed |
| 5 | 1.997615788 | 0.152951998 | 0.002840% | 0.200578% | passed |
| 10 | 0.999430006 | 0.076524264 | 0.001677% | 0.202571% | passed |

基准与扫描中的 Rin=5 Ω 为独立运行，各自保留原始数据。

## Boost 动态结果

四个工况均采集 1.5 s、10 kHz、15,000 点。最终均值窗口为 [1.4,1.5) s，动态事件前窗口为 [0.4,0.5) s。模型和判据定义见 [Boost 说明](boost-experiments.md)。

| 工况 | 最终均值 / V | 稳态相对误差 | 调节／恢复 / s | 超调或最大偏差 | 状态 |
|---|---:|---:|---:|---:|---|
| Boost 基准 | 50.000340 | 0.000680% | — | — | passed |
| 参考 50→60 V | 59.998315 | 0.002809% | 0.2489 | 0.02968% | passed |
| 输入 35→28 V | 49.995309 | 0.009381% | 0.3307 | 18.20093% | failed |
| 输入 35→38.5 V | 50.009795 | 0.019589% | 0.2119 | 16.66905% | failed |

参考超调以 10 V 阶跃幅值归一化；输入扰动最大偏差以 50 V 归一化。两项扰动的事件、最终误差和恢复时间通过，最大偏差分别为 18.20093% 和 16.66905%，超过固定的 10%。官方 PI 参数与原判据保持不变，越限项和失败状态均留在报告中。

三次动态事件的首变采样时刻均为 0.5000005 s，相邻样本检测区间约为 (0.4999005,0.5000005] s，默认分辨率为 100 µs。完整图保留启动瞬态，动态细节图标出局部时间范围。

## 待验事项

| 项目 | 状态与完成方式 |
|---|---|
| 组员独立复现 | 待执行；按 [交接流程](handoff.md) 记录实际执行者、机器、任务与结果 |
| GUI 手动操作路径 | 待组员实际点选核对；步骤见 [首次实验](first-experiment.md) |
| 电机模型、实体 HIL 与外部控制器 | 尚未接入；按具体模型、设备和任务建立验证记录 |

完整命令、数据核对与审查材料见 [当日验证记录](../results/20261015-112422-v2-validation-dd212b/summary.md)。
