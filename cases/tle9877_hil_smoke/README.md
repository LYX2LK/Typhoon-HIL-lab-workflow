# TLE9877 实体正常工况计划

本目录保存首次板卡—HIL 正常闭环的 [plan.json](plan.json)。目标是记录一个已确认转速命令、板卡响应、模型反馈、停止及恢复。参数与阈值由提供方和现场负责人结合实际固件填写。

当前状态为待接入：实体 HIL 后端、LIN 厂家驱动、栅极调理、无感反馈模型和目标参数尚未完成。计划中的 execution_enabled=false 表示尚无执行实现；修改这个字段不能启用实体设备。

本目录没有 case.json，因此不进入现有 Virtual HIL 的 list-cases/run-case 注册。实际设备和反馈路径齐备后再实现实体执行器及其结果协议，完成首轮实测后登记可执行案例。无需为一个计划放宽当前案例校验规则。

准备入口：[I/O 合同](../../configs/tle9877_hil_contract.json)、[电机参数接收表](../../configs/tle9877_motor_pending.json)、[现场步骤](../../docs/tle9877-field-commissioning.md)、[记录模板](../../docs/templates/tle9877-field-record.md)。独立的 [PMSM 软件预演](../pmsm_software_preview/README.md)继续用于已有理想反馈下的软件检查。
