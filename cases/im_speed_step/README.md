# 感应电机运行中转速参考阶跃

本案例供有电机基础、尚不熟悉 Typhoon/Python 的组员观察一次运行中的转速参考变化及闭环响应。模型接口沿用[感应电机接入说明](../im_speed_tracking/README.md)，判据和来源见[阶跃判据](acceptance.md)。

在项目根目录运行：

```powershell
.\lab.ps1 validate-case --case im_speed_step --json
.\lab.ps1 run-case --case im_speed_step --json
```

`run-case` 返回批次目录，子目录中保存本次原始 CSV、`events.json`、`metrics.json`、完整启动波形、事件局部图和报告。`SpeedReference_rpm` 是送入控制器的实际参考，`Speed_rpm` 是机械速度反馈；`ElectromagneticTorque_Nm` 与 `LoadCommand_Nm` 分别是电磁转矩与施加的负载指令。

先检查事件是否于约 2 s 发生，再看事件前稳定状态及实际生效后 2 s 起的全窗口 ±1% 跟踪。调节时间和沿降速方向的超出量用于解释动态过程。`record_status` 表示记录与复算一致，`experiment_status` 表示事件及性能判据结论。软件结果仅对应 Virtual HIL。
