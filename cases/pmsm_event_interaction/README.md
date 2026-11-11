# PMSM 调速与负载事件交互

比较单独调速、单独加负载、同时施加及相隔5/20/100 ms的两个事件顺序。使用现有PMSM软件预演的电机、控制器和参数假设。完整配置与预先固定判据见[实验方案](acceptance.md)。

```powershell
.\lab.ps1 validate-case --case pmsm_event_interaction --json
.\lab.ps1 run-case --case pmsm_event_interaction --json
```

批次包含10种配置和2次复跑。运行后对实际返回的`run_dir`执行`lab.ps1 verify --run-dir <run_dir> --json`。每次运行保留模型副本、原始CSV、实际事件、配置、指标、报告和代码快照。

离线分析使用安装配套Python调用`scripts/analyze_pmsm_interaction.py --batch <实际批次目录> --output <新分析目录>`。输出恢复时间、误差积分、电流峰值、重复差异、独立复算和图表；该脚本不调用设备或仿真API。

`acceptance.window_policy="event_group"`评价启动稳定段和最后事件后的稳定段，允许两事件间尚未恢复；最多3个事件，同一时刻仅允许不同目标，允许空事件列表作为对照。省略此字段继续采用原预演的每段评价规则。

软件探索判据和参数假设不替代样机要求。首轮仅比较固定工况的响应，不进行LLM搜索或故障诊断。实际结果见[验证索引](../../docs/validation-history.md)。

在固定判据下扩大幅值并加密间隔，使用[后续幅值扩展实验](../pmsm_boundary_coarse/README.md)。首轮配置及原始结果保持，后续实验分别记录选点依据、执行异常和完整性能样本。
