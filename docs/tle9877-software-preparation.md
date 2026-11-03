# 样机软件准备：参数、LIN 与 PMSM 预演

本文供准备样机联调的组员和维护代码的人员使用，说明到货前可以执行的工具、其结果含义和下一步接入位置。板级事实来自本次引线 Excel、LIN.ldf、芯片手册、会议纪要和两张截图，原理与接口问题见[样机接入记录](tle9877-hil-intake.md)。

零基础学习从[图文教程](beginner/README.md)开始；需要逐步解释命令和波形时，阅读其中的 [LIN/PWM 练习](beginner/05-lin-and-pwm.md)和 [Typhoon 预演导读](beginner/06-typhoon-walkthrough.md)。

## 参数与接口检查

在项目根目录执行：

```powershell
.\lab.ps1 check-tle9877 --current-a 10 --json
```

输入为 [样机配置](../configs/tle9877_sample.json) 和[原始 LDF 副本](../data/tle9877/LIN.ldf)。命令检查文件摘要、业务帧布局、接口数量与部分参数一致性，列出缺失电机参数和剩余接入条件。工作区外层资料缺失会标为 missing；存在但摘要变化则报告 failed，以便先核对新版本。

`status=passed` 表示这组离线准备检查通过。`sample_model_ready`、`hardware_ready` 仍为 false，待实际模型和设备条件另行验收。`--current-a 10` 只计算 10A×0.5mΩ=5mV 的理想分流关系；返回的 output_voltage_command 为 null，不会产生 HIL 输出命令。

配置将相电阻 0.005Ω、采样电阻 0.0005Ω、相电感 11μH 分别保存。R/L 的绕组支路或等效相口径尚待确认。实际芯片、固件、栅极调理、反馈注入与采样窗口等列入 pending。

## LIN 离线操作

```powershell
.\lab.ps1 lin-encode --rpm 2240 --post-set 0 --json
.\lab.ps1 lin-decode --frame control --data "64 00" --identifier 0xA6 --identifier-kind pid --checksum 0xF4 --json
.\lab.ps1 lin-decode --frame status --data "64 64 5A 50 0A 00 00 00" --checksum 0x5D --json
.\lab.ps1 lin-decode --frame version --data "01 00" --json
```

四条命令均为离线操作，不连接接口设备、不发 LIN 帧头或数据。三个 frame 别名为 control、status、version。数据为数据域，不包含 PID、checksum、break 或 sync；可用空格或逗号分隔两位十六进制字节。

编码结果包含 6 位 ID、PID、数据、增强校验和、请求转速及量化后的编码转速。转速按最近有效码取整，中点向上；超出 0～5689.6rpm 时拒绝输入，不自动限幅。PostSet 允许 0～5；6 未定义、7 为初始状态，均不作为普通运行指令发送。未分配的控制帧位按 Excel 约定填零。固件低速/高速平台和限幅尚待确认，因此 firmware_target_rpm 为 null。

解码保留每个字段的 raw、value、unit、label 和 validity：

| validity | 含义 |
|---|---|
| valid | LDF 定义范围或枚举内的值 |
| invalid | 资料标为无效的值，例如转速 255 |
| undefined | 无定义的编码，例如温度 211 或多数两位状态的 2 |
| initial | PostSet/ST_PRM 的初始状态 7 |
| reserved | 保留字段 |
| unencoded | 文件没有提供物理换算，例如 Version |

`status=passed` 表示解析完成，不表示所有字段有效或板卡正常。未提供 `--checksum` 时 checksum_verified=false；提供错误校验和、错误 ID/PID 或错误长度时返回错误。增强校验政策仍需与实际固件抓包确认。LIN 状态更新不能用来测定高频电流反馈或快速保护动作。

LDF 的 EWPTEST 循环含两个 10ms 时隙，同一业务帧名义重复周期为 20ms。CheckVersion 是独立调度表。新增的 [LIN 设备接口与 Mock](tle9877-lin-adapter.md)可预演调用、调度、超时和总线日志，实际设备驱动及线上的调度仍待实现。

```powershell
.\lab.ps1 lin-mock --json
```

此命令只使用脚本化响应和模拟时钟，返回的 output_dir 中保存原始日志、场景及输入摘要。错误 PID/校验和、超时和设备异常保留原始信息并结束后续调度；不自动补发停止命令。

## PMSM 软件预演

```powershell
.\lab.ps1 prepare-models --json
.\lab.ps1 validate-case --case pmsm_software_preview --json
.\lab.ps1 run-case --case pmsm_software_preview --json
```

模型来源为本机 THCC 2026.3 的 PMSM closed loop SVPWM control 示例，按字节复制并在 origin.json 登记摘要。运行时只修改结果目录的副本。配置为 [pmsm_software_preview.json](../configs/pmsm_software_preview.json)，判据见[案例说明](../cases/pmsm_software_preview/acceptance.md)。

预演包含模型内控制器、逆变器、电机和负载。使用内部角度反馈，电机选择假设的等效星形口径：9V、5 极对参考已提供资料；Rs=5mΩ、Ld=11μH 暂按模型口径使用，Lq、磁链、惯量和控制参数是明确列出的预演假设。该配置与样机事实配置分开管理。

示例原电流指令模块只处理正值请求。预演副本保留其 MTPA 最优 d 轴关系，采用避免相近数相减的等价公式，并为 q 轴电流增加转矩符号，使零速命令能够使用正负转矩调节。这属于模型内控制器改动，代码和回读保存在运行记录中。

| 仿真时刻 | 请求条件 |
|---|---|
| 启动 | 1800rpm，负载 0.01Nm |
| 0.2s | 参考改为 2400rpm |
| 0.35s | 负载改为 0.03Nm |
| 0.55s | 给零转速命令 |
| 0.8s | 完成采集并停止仿真 |

采集机械速度、三相电流、电磁转矩、实际参考和负载命令，100kSa/s，共约 80000 点。报告将速度换算为 rpm，标出事件时刻，列出每段变化后 0.1s 起的评价窗口。命令电平容差为 0.001rpm/1e-7Nm，用于容纳模拟器浮点量化；转速跟踪判据仍使用预先设置的 50rpm 绝对误差。零速段同样使用绝对误差。

运行返回批次 run_dir，子记录包含源模型来源、实际参数回读、初始化代码、配置、采集元数据、原始 CSV、事件、指标、图和报告。run-case 自动复核并保存案例索引；若后续代码或配置变化，查询会显示旧证据需要重新核对。运行与记录状态分别返回，性能失败保留 failed。

单条记录需要离线复核或重建报告时，对本次新产物按顺序执行：

```powershell
.\lab.ps1 verify --run-dir <实际子记录目录> --json
.\lab.ps1 report --run-dir <实际子记录目录> --json
.\lab.ps1 verify --run-dir <实际子记录目录> --json
```

预演用于检查模型结构、低压工况、命令事件和数据流程。零速命令由示例控制器调节，不代表样机停止/关断/后运行行为。样机的 Δ 绕组参数对应、无感启动、真实六路栅极信号接收、单分流采样注入和驱动诊断条件，仍须按实际固件与转接电路实现。

## 下一步接入

[I/O 合同](../configs/tle9877_hil_contract.json)逐条记录端口、方向、参考电位、电压范围、调理和确认依据，允许注明不连接；[实体参数表](../configs/tle9877_motor_pending.json)接收 Δ 与模型口径、缺失参数和负载资料。填写方法见[现场说明](tle9877-field-commissioning.md)。这些是逐步补充的工作表，原有静态检查行为保持。

1. **板卡提供方确认**：实际芯片和固件版本；唤醒、运行、停止与后运行流程；LIN/PWM 优先级和超时行为。
2. **板卡方与汉象确认**：功率级保留/断开范围，栅极调理与参考点，U/V/W/VM/SL 接法，SHP/SHN 注入范围、共模和有效采样窗口。
3. **电机参数补齐**：R/L 口径、Δ 接法对应、Ld/Lq、磁链/反电动势、惯量及负载资料。确认后新建对应配置并与预演假设比较。
4. **设备条件明确后**：选择 LIN 主节点接口和 SDK，先记录版本/状态，再接入已验证命令；实时调度与反馈交给对应设备，项目负责配置、编排和证据管理。

首次实物正常工况单独使用 [tle9877_hil_smoke 计划](../cases/tle9877_hil_smoke/README.md)和[现场记录模板](templates/tle9877-field-record.md)，待驱动和反馈模型完成后再登记为可执行案例。

设备日志需保留原始 ID/PID、数据、校验/接收状态、方向和设备时间戳，注明时间来源与同步方式。请求转速、编码转速、板卡反馈转速、模型转速分别记录；超时和无效码保留原始值。高频电流反馈的时间证据与 LIN 状态日志分开采集，再按已验证的时钟关系关联。

本次工作的实际结果与失败记录见[验证状态](validation.md)，后续更新按模型和设备条件逐项推进。
