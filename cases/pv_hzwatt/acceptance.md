# Generic PV plant HzWatt 判据

## 实验问题与来源

面向接入人员，比较独立启动的 50 Hz 与 51 Hz 工况，验证频率升高时有功稳态目标由 250 kW 变为 170 kW。模型来自 THCC 2026.3 的 examples/models/microgrid/pv plant/pv plant (generic)/pv plant gen.tse；参考来自安装附带 examples/tests/109_pv_plant_generic/test_pv_plant_generic.py 中的频率—功率表。

官方表按额定 50 Hz、250 kW 归一化，(0.985,1.2)、(0.996,1.0)、(1.0,1.0)、(1.02,0.68)。本轮运行后两点；其他点作为官方依据保留，未宣称本轮实测。分析不从实测功率反推目标。

## 运行前固定的条件

- 采用 Virtual HIL；固定 HzWatt 模式、opc_pu=0.3、Pnom=250000 W。
- 电网电压命令 1 pu；连接、使能、HzWatt 使能及功率限额均为 1；Pcurtailment 与 MPPT 变化率设为 1。
- 每工况独立启动，至少等待 12 s 仿真时间，以 10 kHz 采集 2 s（20,000 点）。
- 全部采样点均参与评价；误差为 abs(Pmeas-Ptarget)/abs(Ptarget)，上限 1%，来自官方测试 tol_p=0.01。Pref_fb_kW 按固定 Pcurtailment=1 pu 与额定功率计算，目标为 250 kW，使用相同 1% 限值检查。
- 频率反馈距命令不超过 0.01 Hz、Enable_fb 全程为 1，作为本项目输入生效/有效性检查；缺少有效激励或完整数据按 error 处理。
- 报警码全程为 0，作为教学运行状态检查；报警或功率越限保留 failed。

官方原脚本在共享仿真中连续改频，以 10 kHz 采集 20 s，并检查后 10 s；本案例采用独立启动、等待 12 s 后采集 2 s。该调整用于建立最小稳态接入案例，未验证动态响应或标准符合性。

## 功率参考信号的含义

本机生成的模型 C 代码显示：Pcurtailment 经额定功率缩放和限幅、再转换成 kW 后接到 Pref_fb_kW；HzWatt 输出则另外叠加频率支持量。因此 Pref_fb_kW 不是 HzWatt 调整后的有功目标。分析方法版本 2 按该映射检查 250 kW 的固定限额参考；实测有功仍按官方频率—功率表检查。

接入初期方法 1 将该信号直接与 HzWatt 有功目标比较，在 51 Hz 工况记录了 failed。原数据、原判据、代码和当时复核全部保留；映射修正后重新运行，不回写旧结论。当前复核器明确拒绝方法 1 的复算，历史查看使用其已保存报告。差异与证据见[验证索引](../../docs/validation-history.md)。

## 证据与状态

同时采集实际有功、功率参考、频率、使能、报警码与无功。参数设置读回、原始 CSV、采集时间、指标、报告及最终 verification.json 均应留存。record_status 表示记录复算一致性，experiment_status 表示上述判据结果。
