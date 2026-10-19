# 感应电机转速跟踪判据

本案例采用独立启动的项目教学工况，1430 rpm 与 850 rpm 各自启动一次。电源为 230 V 相电压 RMS、50 Hz；常值负载选择 Load_sel=1，IM_Load=0.5 经模型 Gain6=4 换算为 2 N·m 负载指令。控制器和电机参数保留官方值。

判据来源是 THCC 2026.3 安装下 `examples/tests/101_indm_closed_loop_control/test_indm_closed_loop_control.py` 的 `test_indm_speed_check`：同一仿真内改变 Speed RPM，采集 4 s、50 kHz，使用 `ranges.around(machine_speed,tol_p=0.01)` 和 `ranges.after('2s')`；断言默认 strictness=1。脚本 SHA-256 与模型 SHA-256 保存于 [模型来源](../../models/origin.json) 的本模型条目。

本项目调整为从零启动、20 kHz 请求采样、实际仿真时间 [2,4) s 评价，并显式选用常值 2 N·m 负载。原脚本未设置 Load_sel；本机预验发现其默认值 0 时负载指令为零。因此本案例不称为原官方测试的完整复现。

在有效窗口的全部原始采样中，计算 `e_max=max(abs(Speed_rpm-reference_rpm)/abs(reference_rpm))`，要求 e_max≤0.01。临界比较仅允许 1e-12 浮点余量。报告同时给出最大绝对误差、平均转速、超限点数与全部超限时刻，不滤波、不插值。

请求采集 4 s、20 kHz；最低实际采样率 10 kHz，依据已核对的 100 µs 控制周期；最低全程采样 40,000 点。实际采样率与请求偏差须≤1%，采集长度及窗口覆盖允许至多一个实际采样间隔的端点量化差。缺样、无效数值、窗口不足或控制输入与配置不一致属于 error，停止性能评估；有效数据越限属于 failed。

参数设置、来源和实测证据按 [接入说明](README.md) 查阅。记录一致性由最终 verify 判定，性能未达标时保持失败结论。
