# 感应电机转速阶跃判据

本案例面向课题组组员，回答运行中的目标转速从 1430 rpm 降至 850 rpm 后，实际参考是否按时进入控制器，以及闭环转速能否在规定窗口稳定跟踪。运行模式为 Virtual HIL；电源为 230 V 相电压 RMS、50 Hz，Load_sel=1、IM_Load=0.5，经模型 Gain6=4 对应 2 N·m 常值负载指令。控制器和电机属性保留官方模型值。

模型副本中的 Step 在仿真时刻 2 s 改变参考，经 Sum 接入原 `rpm_to_w_elec` 通路。`LabSpeedReference` 记录实际送入该通路的参考。`manifest.json` 保存 Step 属性读回；`events.json` 保存请求时刻、模型触发时刻、首次变化样本和前一样本组成的检测区间。实际生效允许在请求时刻前一个采样间隔至请求时刻后一个控制周期加一个采样间隔内；前后电平允许 0.001 rpm 误差。未观测到事件、错时或电平不符为 `error`。

采集 0～5 s，20 kHz 请求采样，共 100,000 点；实际采样率至少 10 kHz，且与请求偏差不超过 1%。事件前 `[1.5,2)` s 全部样本需位于 1430 rpm ±1% 内。事件后的评价窗口从 `max(4 s, 实际生效时刻+2 s)` 开始，至 5 s 结束；全部样本需位于 850 rpm ±1% 内。边界 1% 算通过，仅允许 1e-12 浮点余量。有效数据越限为 `failed`；缺失、非有限、时间轴异常或采集不足为 `error`。

调节时间定义为事件实际生效后，首次进入 850 rpm ±1% 且此后至采集结束保持在带内的时长。沿降速方向低于 850 rpm 的最大量除以 580 rpm 阶跃幅值，作为描述性超出量，不单设合格阈值。原始采样不滤波、不插值；同时展示转速、实际参考、电磁转矩和负载指令。

±1% 及“改速后 2 s 起”的依据是 THCC 2026.3 安装附带 `examples/tests/101_indm_closed_loop_control/test_indm_closed_loop_control.py` 中的 `test_indm_speed_check`；本案例将其转成固定仿真时刻、固定负载和明确事件证据的项目教学判据。IEC 61800-2:2021 给出交流调速传动系统的性能和测试规范框架，国内 GB/T 12668.2-2002 仍为现行版本，GB/T 12668.2-2025 将于 2027-01-01 实施；本案例不声称满足标准产品认证或实体电机要求。来源：[IEC](https://webstore.iec.ch/en/publication/62105)、[现行国标](https://std.samr.gov.cn/gb/search/gbDetailed?id=71F772D7967CD3A7E05397BE0A0AB82A)、[后续国标](https://std.samr.gov.cn/gb/search/gbDetailed?id=D0I1%2BGI%2BZOg%3D&mode=p)。
