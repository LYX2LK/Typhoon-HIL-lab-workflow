# 术语、资料与图片索引

[学习入口](README.md)

本页用于读图和查词。第一次学习时优先跟随各章，遇到缩写再回来。

## 常用术语

| 词 | 中文或通俗解释 | 主要章节 |
|---|---|---|
| IC / chip | 芯片，集成电子功能的器件 | [2](02-chip-board-and-wires.md) |
| PCB / board | 电路板，连接芯片和外围器件 | [2](02-chip-board-and-wires.md) |
| MCU | 微控制器，执行控制程序的小计算机 | [2](02-chip-board-and-wires.md) |
| firmware | 固件，运行在板卡上的程序 | [2](02-chip-board-and-wires.md) |
| peripheral | 外设，芯片内的定时、采样和通信等功能模块 | [2](02-chip-board-and-wires.md) |
| register | 寄存器，程序读写硬件配置或状态的位置 | [2](02-chip-board-and-wires.md) |
| ADC | 模数转换器，把电压转成数字 | [2](02-chip-board-and-wires.md)、[4](04-feedback-and-hil.md) |
| OP AMP / CSA | 运算放大器／电流采样放大器 | [4](04-feedback-and-hil.md) |
| MOSFET / G / D / S | 功率开关；栅极／漏极／源极 | [2](02-chip-board-and-wires.md) |
| gate driver | 栅极驱动器，控制功率开关栅极 | [2](02-chip-board-and-wires.md) |
| inverter | 逆变器，本场景中将直流电经开关转换成三相输出 | [2](02-chip-board-and-wires.md) |
| DC bus | 直流母线，功率电路的直流供电侧 | [1](01-electricity-and-system.md)、[2](02-chip-board-and-wires.md) |
| shunt | 分流电阻，通过小压降测量电流 | [1](01-electricity-and-system.md)、[4](04-feedback-and-hil.md) |
| differential / common mode | 差分／共模，两个端点的差值／整体参考位置 | [4](04-feedback-and-hil.md) |
| gain / offset | 增益／偏置，倍率／零点位置等校正量 | [4](04-feedback-and-hil.md) |
| PMSM | 永磁同步电机 | [3](03-motor-and-control.md) |
| BLDC | 无刷直流电机；相关驱动产品资料常出现此名称，具体电机与控制方式仍看对应定义 | [3](03-motor-and-control.md) |
| stator / rotor | 定子／转子，固定部分／随轴旋转部分 | [3](03-motor-and-control.md) |
| pole pairs | 极对数，成对 N/S 磁极的对数 | [3](03-motor-and-control.md) |
| torque / load / inertia | 转矩／负载／惯量 | [3](03-motor-and-control.md) |
| FOC | 磁场定向控制，按转子磁场方向组织电流控制 | [3](03-motor-and-control.md) |
| sensorless / observer | 无位置传感器控制／根据测量估计状态的算法 | [3](03-motor-and-control.md) |
| PWM / duty cycle | 脉宽调制／占空比 | [3](03-motor-and-control.md)、[5](05-lin-and-pwm.md) |
| dead time | 死区，同桥臂切换时预留的空档 | [2](02-chip-board-and-wires.md) |
| LIN / LDF | 本次使用的通信总线／描述节点、帧和信号的文件 | [5](05-lin-and-pwm.md) |
| frame / signal | 帧，一次组织好的通信单元／其中定义的字段 | [5](05-lin-and-pwm.md) |
| ID / PID / checksum | 帧标识／带保护位的标识／数据校验和 | [5](05-lin-and-pwm.md) |
| raw / physical value | 原始码／按规则换算的物理值 | [5](05-lin-and-pwm.md) |
| schedule / slot | 调度表／其中安排给一项通信的时隙 | [5](05-lin-and-pwm.md) |
| post-run | 后运行，触发后继续执行特定动作的状态流程 | [5](05-lin-and-pwm.md) |
| HIL / plant | 硬件在环／被仿真的对象 | [4](04-feedback-and-hil.md) |
| C-HIL / DUT | 控制器硬件在环／被测设备，本案例为真实控制板及固件 | [8](08-ti-launchpad-chil.md)、[9](09-pmsm-to-tle9877-chil.md) |
| eQEP / A、B、Z | TI 编码器接口／编码器的两路正交信号与索引信号 | [8](08-ti-launchpad-chil.md) |
| UniFlash / .out | TI 烧录工具／本案例供 TI 控制器使用的固件映像 | [8](08-ti-launchpad-chil.md) |
| Virtual HIL | 在电脑中运行的虚拟仿真环境 | [4](04-feedback-and-hil.md)、[6](06-typhoon-walkthrough.md) |
| DI / DO / AI / AO | 从对应设备看，数字输入／数字输出／模拟输入／模拟输出 | [4](04-feedback-and-hil.md) |
| compile / load / run | 编译／加载／运行 | [6](06-typhoon-walkthrough.md) |
| sample rate / time step | 保存数据的采样速率／模型计算推进的时间步长 | [6](06-typhoon-walkthrough.md) |
| reference / feedback | 希望达到的参考值／实际测量或估计反馈 | [1](01-electricity-and-system.md) |
| overshoot / settle | 超过目标的暂态偏差／逐步进入较小误差范围 | [6](06-typhoon-walkthrough.md) |
| acceptance / verification | 按事先要求评价实验／核对记录与复算一致性 | [6](06-typhoon-walkthrough.md) |

## 你提供的材料，建议怎样读

| 材料 | 第一轮读什么 | 后面用来回答什么 |
|---|---|---|
| [引线 Excel](../../../docs/电机控制板引线连接位置信号及方案说明.xlsx) | 引脚分配、各页原图 | 本板的引出点、供电说明、电机方案和协议 |
| [芯片手册 PDF](../../../docs/Infineon-TLE9877QXA40-DataSheet（试样的样机控制芯片）.pdf) | 第 10、11、79～82 页 | 内部模块、芯片脚、桥驱动、采样链 |
| [LIN.ldf 项目副本](../../data/tle9877/LIN.ldf) | Nodes、Frames、Schedule_tables、Signal_encoding_types | 节点、字段位置、换算、枚举和调度 |
| [电机参数截图](assets/motor-parameters.png) | 四个参数的名称、值和单位 | 与模型需要的参数逐项对应 |
| [控制电路截图](assets/control-boundary.png) | 芯片、右侧功率桥、下方分流电阻 | 驱动与反馈的物理路径 |
| [会议纪要](../../../docs/联合实验室建设方案研讨会议纪要.md) | 本次样机、材料、平台和分工相关内容 | 确定谁提供资料、谁确认方案及测试目的 |

外层原材料在本机 D:\Typhoon\docs。学习用图片另存到本教程 assets 中，便于配合正文阅读；完整板级事实以[接入记录](../tle9877-hil-intake.md)与[样机配置](../../configs/tle9877_sample.json)为准。

### 芯片手册怎样查

先按“我想知道什么”查目录，再定位图表。看电气参数时，同时读**条件、最小值、典型值、最大值和脚注**。典型值帮助理解某些代表条件，保证范围与适用条件要看具体表述。

**Absolute maximum ratings，绝对最大额定值**用于描述器件承受极限相关条件；日常运行设定应使用对应的推荐或规定工作条件，并结合板级设计。查看某个芯片的能力，也要确认实际芯片型号与版本。

本教程手册截图来自你提供的 Rev.2.2，2025-09-15 版本，按 PDF 页序渲染；所选页的印刷页码与 PDF 页序一致。

## 图片索引

原始截图及 Excel 内嵌图片按字节保存，手册页为整页渲染。原图文字、名称和图间差异保留，正文在相关位置说明含义。

| 图片 | 来源位置 | 教程用途 |
|---|---|---|
| [电机结构和规格](assets/motor-specification.png) | Excel“电机方案”，xl/media/image1.png | 认识定子、转子与额定参数 |
| [控制系统方案](assets/motor-solution.png) | 同页，image2.png | 认识命令、芯片、功率与反馈 |
| [PWM 表格](assets/pwm-protocol-table.png) | Excel“PWM控制协议”，image3.png | 读命令区间与接口说明 |
| [PWM 曲线](assets/pwm-protocol-curve.png) | 同页，image4.png | 对照表格并识别边界待确认项 |
| [LIN 曲线与周期](assets/lin-protocol-1.png) | Excel“lin控制协议”，image5.png | 理解平台区与周期问题 |
| [LIN 方向与 ID](assets/lin-protocol-2.png) | 同页，image6.png | 对照帧方向与标识 |
| [LIN 字段表](assets/lin-protocol-3.png) | 同页，image7.png | 练习字节、位、比例和偏置 |
| [电路截图](assets/control-boundary.png) | 你提供的截图 | 沿驱动和采样路径读电路 |
| [参数截图](assets/motor-parameters.png) | 你提供的截图 | 认识参数名称和定义 |
| [手册第 10 页](assets/datasheet-p010.png) | Figure 1 | 芯片内部功能 |
| [手册第 11 页](assets/datasheet-p011.png) | Figure 2 | 封装引脚编号 |
| [手册第 80 页](assets/datasheet-p080.png) | Figure 29 | 栅极驱动及参考 |
| [手册第 82 页](assets/datasheet-p082.png) | Figure 30 | 差分放大、偏置与 ADC |
| [PMSM 完整波形](assets/pmsm-preview-waveforms.png) | 已留存预演记录 | 学习调速、负载变化与零速响应 |
| [TI 逆变器输入配置](assets/ti-chil-inverter-official.jpg) | 官方 TI PMSM 应用说明 Figure 2，本机帮助原图 | 对照六路 DI 与有效极性 |
| [TI SCADA 面板](assets/ti-chil-scada-official.jpg) | 同案例 Figure 3，本机帮助原图 | 找到串口、使能、转矩和观察量 |

具体来源、文件摘要和手册页序见[图片来源清单](assets/sources.json)。

离线阅读页另配五张本教程绘制的简化示意图：[要求与反馈](assets/system-loop.svg)、[转速环与电流环](assets/control-loops.svg)、[拟接入 HIL 闭环](assets/hil-loop.svg)、[TI C-HIL 三条路径](assets/ti-chil-loop.svg)、[单分流反馈链](assets/tle9877-shunt-path.svg)。它们解释功能关系，实际接口以对应方案为准。

## 官方补充资料

按需要阅读即可，第一遍无需把英文材料从头读完。

- [Infineon TLE9877QXA40](https://www.infineon.com/part/TLE9877QXA40)：核对芯片功能及外部功率级边界。
- [Typhoon PMSM 组件](https://www.typhoon-hil.com/documentation/typhoon-hil-software-manual/References/three_phase_permanent_magnet_synchronous_machine.html)：对照模型参数、星形／三角形连接及机械量。
- [Typhoon 虚拟 I/O 回环](https://typhoon-hil.com/documentation/typhoon-hil-software-manual/concepts/vhil_analog_digital_io_loopback.html)：理解 Virtual HIL 的软件回环方式。
- [TI LaunchPad PMSM C-HIL](https://www.typhoon-hil.com/documentation/typhoon-hil-application-notes/References/ti_pmsm_torque_control.html)：配合[第 8 章中文实训](08-ti-launchpad-chil.md)阅读，学习真实控制器接入结构。
- [Typhoon 硬件接口指南](https://www.typhoon-hil.com/documentation/typhoon-hil-hardware-manual/hil_interfacing_guide/topics/abstract.html)：按实际控制器和转接电路选择接口方案。
- [HIL404 电压规格](https://www.typhoon-hil.com/documentation/typhoon-hil-hardware-manual/hil404_user_guide/References/hil404_IO_voltage_levels.html)、[I/O 时序](https://www.typhoon-hil.com/documentation/typhoon-hil-hardware-manual/hil404_user_guide/References/hil404_IO_timing.html)：对应实际设备查量程、精度、更新率与延迟。
- [TI 单分流无感 FOC 应用说明](https://www.ti.com/lit/pdf/spract7)：先看第 2 节框图，需要时再看采样时间和重构。
- [Microchip 单分流 PMSM 示例](https://onlinedocs.microchip.com/oxy/GUID-686B08E8-FD18-4AAD-87B9-32B527406A88-en-US-3/GUID-942885A0-341F-425F-94BD-714A4351EF12.html)：理解一种实际无感启动、估计与采样实现。
- [ST AN3055 LIN 介绍](https://www.st.com/resource/en/application_note/an3055-getting-started-with-stm8a-lin-package-stswstm8alin-stmicroelectronics.pdf)：优先读第 2 节，认识帧头、响应、校验与调度。

## 继续到项目操作

学过这套教程后，日常命令用[软件准备说明](../tle9877-software-preparation.md)快速查询，板级细节查[接入记录](../tle9877-hil-intake.md)，实际完成范围查[验证状态](../validation.md)。
