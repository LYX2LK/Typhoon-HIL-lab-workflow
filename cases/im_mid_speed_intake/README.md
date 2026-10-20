# 陌生实例接入演练：1000 rpm 转速跟踪

本页供组员练习收到简短测试要求后的处理方法。使用现有感应电机模型和适配器，新增一个案例与配置，不改动已有 1430/850 rpm 案例的判据或历史记录。

接收信息及缺口见[判据](acceptance.md)。判断结果：模型来源、速度参考、负载选择、反馈信号、采样和稳态判据均已有实测映射，所以本例走**配置复用**；无需为 1000 rpm 建新适配器。`case_id=im_mid_speed_intake` 表示新测试问题，`model_id=induction_motor_closed_loop` 仍选择原适配器。

```powershell
.\lab.ps1 validate-case --case im_mid_speed_intake --json
.\lab.ps1 run-case --case im_mid_speed_intake --json
```

先核对 `integrity`、`software_support` 与 `runtime_validation`。`run-case` 返回批次 `run_dir`，在批次报告中找到子运行目录、原始 CSV、速度参考及负载指令的实际波形；再核对 `record_status`、`experiment_status` 和完整 `[2,4)` s 窗口的最大相对误差。软件结果与真人、跨电脑和实体 HIL 验收分别记录。
