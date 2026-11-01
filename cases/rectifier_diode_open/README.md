# 三相整流桥二极管开路

面向电机驱动和电源前端测试的使用者，演示从波形发现导通缺失，再通过可追溯的注入配置和对照运行核对解释。

公开问题依据为 Mehdi Rahiminejad（2016）的 [Open-circuit fault diagnosis in three-phase power rectifier driven by a variable voltage source](https://unbscholar.lib.unb.ca/items/1481f82f-78d4-4fe2-a52d-489c0a3f4dd4)。论文研究包含变幅变频输入及后级变换器，使用分类器和相位关系定位故障；本例采用固定源、纯电阻负载和确定性波形特征，是该诊断问题的简化复现。

## 模型与工况

模型由 `rectifier_fault.build_model` 从空白原理图建立，保存在 `models/three_phase_rectifier_fault.tse`，来源及哈希登记于 `models/origin.json`。六个独立二极管分别为 D_ap/D_an、D_bp/D_bn、D_cp/D_cn，p 表示上桥臂，n 表示下桥臂。故障运行副本在编译前删除 D_ap，其余五个支路保持。

固定相电压有效值230 V、50 Hz，ABC相序（0/−120/+120°），100 Ω纯电阻负载。使用 HIL404 Pro 3 编译目标，在 PC 上通过 Virtual HIL 运行。该配置支持六个LC二极管；数值电阻参数1 Ω、电路步长0.25 μs，表示LC数值模型参数。采集仍为20 kHz、0.3 s、6000点，分析最后0.2 s的4000点。

采集 Va/Vb/Vc、Ia/Ib/Ic、Vdc/Iload；相电流正方向从源流向整流桥。默认不加直流平滑电容，以便观察正常六脉波与导通缺失造成的输出变化。

## 使用

```powershell
.\lab.ps1 agent --case rectifier_diode_open --port 8767
.\lab.ps1 validate-case --case rectifier_diode_open --json
.\lab.ps1 run-case --case rectifier_diode_open --json
```

Agent首轮运行正常和开路两个工况。模型输入包括从原始CSV复算的指标与导通方向，不包括故障参数、模型删除记录和参考误差。分析后在折叠区查看实际注入配置，再与解释核对。后续正常、故障或重复工况经选项预览、确认后执行。

电流中的A相正向导通缺失支持A相上桥臂通路异常。二极管开路与同通路接线开路仍需要额外观测区分。具体数值验收见 [acceptance.md](acceptance.md)，实际证据见 [验证索引](../../docs/validation-history.md)。
