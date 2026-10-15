# 验证记录索引

本页按验证日期索引已保存的实际记录，供维护者追溯当时的模型、代码、配置和结论。使用者判断现行能力时查看 [验证状态](validation.md)，实验操作从 [README](../README.md) 开始。

## 2026-10-15：统一执行与闭环动态实验

范围包括最小回环、RLC 基准与三工况扫描、Boost 基准、参考阶跃及两项输入电压扰动。脚本测试 54 项通过，全部最终记录复算一致；Boost 两项扰动的最大输出偏差超过 10%，保留 failed。

- [验证说明与全部实际目录](../results/20261015-112422-v2-validation-dd212b/summary.md)
- [实际命令和运行目录](../results/20261015-112422-v2-validation-dd212b/actual-runs.json)
- [报告重建与复核结果](../results/20261015-112422-v2-validation-dd212b/final-checks.json)
- [历史记录副本兼容检查](../results/20261015-112422-v2-validation-dd212b/historical-compatibility.json)
- [独立数值复核](../results/20261015-112422-v2-validation-dd212b/independent-numeric-audit.json)
- [模型保留范围](../results/20261015-112422-v2-validation-dd212b/model-preservation.json)
- [图表核对](../results/20261015-112422-v2-validation-dd212b/plot-qa.json)

## 2026-10-14：环境、回环与 RLC 实验

记录包含软件环境、模型检查、最小回环、RLC 基准和 Rin=1/5/10 Ω 扫描。基准与扫描通过当时配置的 3% RMS 相对误差判据，并保留原始数据、报告和复核结果。

| 项目 | 原始记录 |
|---|---|
| 环境与基准模型设置 | [运行清单](../results/20261014-211038-rlc-18c288/manifest.json) |
| 最小回环 | [清单](../results/20261014-212943-smoke-a2a022/manifest.json)、[实际读数](../results/20261014-212943-smoke-a2a022/readings.json) |
| RLC 基准 | [报告](../results/20261014-211038-rlc-18c288/report.html)、[指标](../results/20261014-211038-rlc-18c288/metrics.json)、[复核](../results/20261014-211038-rlc-18c288/verification.json) |
| RLC 三工况扫描 | [报告](../results/20261014-211142-sweep-db63f4/report.html)、[比较数据](../results/20261014-211142-sweep-db63f4/comparison.csv)、[复核](../results/20261014-211142-sweep-db63f4/verification.json) |

## 索引维护

完成一次验证后保存独立结果目录，再按日期登记范围、结论与证据链接，同时更新验证状态中的能力和实测结论。历史结果及代码快照保留原貌；操作教程直接反映现行用法。
