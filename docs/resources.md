# 学习资源与案例导航

本页提供学习材料和测试案例的选择建议，适合有电机或电力电子基础、尚不熟悉 Typhoon/Python 时查阅。目标是先完成一个可解释、可复核的实验，再选择与手头任务相近的案例。核对日期：**2026-10-15（北京时间）**；本机参考安装：**Typhoon HIL Control Center 2026.3**。

感应电机闭环案例的本地模型、官方测试及接口已于 **2026-10-19** 核对；2026-10-20 又完成运行中转速阶跃的 Virtual HIL 实测。操作入口见[独立启动案例](../cases/im_speed_tracking/README.md)与[运行中阶跃案例](../cases/im_speed_step/README.md)。Generic PV plant 的 50/51 Hz 稳态案例已接入，操作与实测范围见[光伏案例](../cases/pv_hzwatt/README.md)。其他资源沿用各行所列核对日期。

## 案例层次与选择依据

| 层次 | 当前材料 | 项目中的用途与维护位置 |
|---|---|---|
| 已有教学与验证案例 | RLC、Boost、单相整流、感应电机、光伏等已有配置与记录 | 学习软件与验证公共流程；运行入口在 cases，实际结论在[验证状态](validation.md) |
| 具体需求接入对象 | 已收到测试要求但模型、接口或判据仍待补齐的任务，例如[水泵控制器](pump-hil-intake.md) | 在专题文档记录测试目的、材料、缺口和完成依据；条件具备后登记可执行案例 |
| 应用案例资源 | 官方公开说明、安装示例及供应商介绍的四个用户案例 | 用于理解不同应用和选择接入候选；本页分别注明材料来源、可获得资源及验证状态 |

下一案例按任务相关性、材料完整度、运行条件和能力增益选择。先明确它要回答的实验问题，以及能检验工作流的哪个新环节，例如事件与动态响应、波形特征分析、外部控制器接口或多子系统编排。比较候选案例的可复用部分、关键缺口和最小验证范围，再确定实施顺序。

收到具体测试任务时优先满足该任务；能力准备阶段优先选择材料可取得、条件可满足且能补足当前能力的案例。不同领域的代表性用于检验方法的适用范围，案例数量本身不作为完成依据。

## 先按任务选择

已接入案例的机器可读入口为 `list-cases --json`，元信息与校验规则见 [案例接口](case-interface.md)。下表中的公开资源仍是选型导航，不自动计为已支持模型。

| 现在要做什么 | 优先入口 | 做到什么程度 |
|---|---|---|
| 第一次使用软件 | 本项目[环境配置](environment.md) → [首次实验](first-experiment.md) | 完成 doctor、smoke、RLC 实验和 verify |
| 自行建模和增添测量点 | [自建 RLC 练习](modeling-practice.md) → 安装内 Schematic API | 从空白图完成连线、改参、编译、Virtual HIL 采集和复核；GUI 操作单独记录 |
| 学模型、面板和采集的 GUI 操作 | 官方 Quick Start、Example Explorer、HIL Specialist 课程 | 能说明打开、编译、加载、启动、改参、采集和停止的对应操作 |
| 让 Agent 执行实验 | 本项目[Agent 工作流](agent-workflow.md) | 能从任务描述追到配置、原始数据、报告及复核结果 |
| 学自动化接口或修改运行器 | Schematic API → HIL API → TyphoonTest | 先区分模型结构操作、运行操作、数据分析和测试断言 |
| 接收一个新测试实例 | 本项目[模型接入方法](model-integration.md) → 下方案例表 | 先核对版本、运行模式、输入、信号、判据和设备条件，再建副本运行 |
| 比较不同应用的案例线索 | [供应商应用案例](#供应商介绍的应用案例)及官方模型表 | 比较研究问题、可借鉴方法和材料缺口，按条件选定下一实例 |
| 观察电机运行中改速 | [感应电机运行中阶跃](../cases/im_speed_step/README.md) | 在同一次 5 s Virtual HIL 中观察 1430→850 rpm 参考、转速与电磁转矩，核对事件和跟踪判据 |
| 比较并网频率对光伏稳态有功的影响 | [光伏 HzWatt 案例](../cases/pv_hzwatt/README.md) | 独立启动 50/51 Hz 工况，核对 250/170 kW 参考及状态 |
| 检查外部示波器数据 | [外部波形检查](external-waveforms.md) | 核对格式、时间轴、数值特征及来源缺口，保存原始数据与方法 |
| 用不完整要求练习案例接收 | [1000 rpm 接入演练](../cases/im_mid_speed_intake/README.md) | 列出缺口、判断配置复用、固定教学判据并交付实测记录 |

## 把测试要求映射到案例

接到任务时，先写清要回答的问题和比较因素，再选择资源。至少核对：被测对象及模型来源、软件版本与运行模式；基准工况、要改变的参数或事件及其单位；能够证明激励生效的信号、待评价信号、采样与分析窗口；判据来源、阈值和交付物。缺少会影响实验成立的条件时，列出缺口，不用现有教学判据代替任务方要求。可按[模型接入任务清单](model-integration.md#接收测试实例时填写的任务清单)记录。

先用 `.\lab.ps1 list-cases --json` 查找项目案例，再对候选案例用 `.\lab.ps1 validate-case --case <案例标识> --json` 检查 `integrity`、`software_support` 和 `runtime_validation`。这两步是只读检查；静态通过不证明当前电脑已编译、运行或满足性能判据。字段与状态见[案例接口](case-interface.md#查找和校验)。

| 要解决的测试问题 | 任务方需明确的输入 | 可复用的现有案例与部分 | 选择时注意 |
|---|---|---|---|
| 元件参数变化如何影响稳态电压、电流，RMS 与解析参考是否一致 | 电路参数及单位、输入幅值和频率、待测信号、采样窗口与误差阈值 | [RLC 基准与扫描](experiments.md)的模型适配、采集、解析比较；现有 `sweep` 只覆盖 Rin 扫描 | 改变拓扑或增加测量点时先走[自建模型练习](modeling-practice.md)或模型接入预验 |
| Boost 参考值阶跃或输入电压变化后，输出误差、超调、偏差和恢复时间如何变化 | 初始值与目标值、事件时刻、输出与实际输入/参考信号、评价窗口及各指标判据 | [Boost 四工况](boost-experiments.md)的闭环初始化、事件留证、动态指标和报告 | 已测输入扰动的峰值偏差未达固定判据，复用方法不等于复用通过结论，见[验证状态](validation.md#boost-动态结果) |
| 单相整流在输入减小或负载加重时，直流均值、纹波和电流如何变化 | 输入与负载条件、测量信号、等待与采样窗口、理论或趋势判据 | [整流基准、低输入与重载](rectifier-experiments.md)的适配器、三工况配置和比较方法 | 新拓扑、信号或判据须重新核对模型接口与参考依据 |
| 感应电机在给定负载下能否达到并保持目标转速 | 模型与电源条件、负载模式和数值、目标转速、反馈信号、稳态窗口及允许误差 | [独立启动](../cases/im_speed_tracking/README.md)的接口映射与稳态判定；[1000 rpm 演练](../cases/im_mid_speed_intake/README.md)示范配置复用 | 其他负载模式或参考范围先核对适配器能力和实际生效信号 |
| 感应电机运行中改速后，事件是否生效、多久恢复到允许区间 | 阶跃前后转速、事件时刻、负载、参考与反馈信号、采样窗口和动态判据 | [转速阶跃](../cases/im_speed_step/README.md)的同次运行事件留证、动态分析和报告 | 现有事件是转速参考变化；负载扰动等新事件需另行检查接口并验证 |
| 光伏电站在不同电网频率下的稳态有功是否符合 HzWatt 参考 | 额定频率和功率、频率点、限额参考、使能、等待与采集窗口、参考曲线及误差限 | [光伏案例](../cases/pv_hzwatt/README.md)的官方表参照、接口读回与全窗口判定 | 当前为单个光伏子系统的独立稳态工况；动态调频、多控制器和 EMS 需专项接入 |

表中案例的实测范围以[验证状态](validation.md)为准。对于下方仅有官方资料或本地示例、尚未接入项目的 EV、实体控制器 PMSM 和 TyphoonSim 模型，先核对设备、许可、仿真模式、模型接口及测试依据；资料可用于选题和接口预验，不能直接当作可运行案例。

确定候选案例后按下表选择实施路径；每条路径都要在本次任务中固定判据，并按[选中案例后的操作顺序](#选中案例后的操作顺序)留存实际证据。

| 核对结果 | 实施路径 |
|---|---|
| 同一模型，所需参数、事件、信号和指标已受支持 | 新建或另存配置；需要独立描述测试问题时新增案例，复用现有适配器和执行器 |
| 同一模型，但缺少所需事件、信号、指标或参数映射 | 按[模型接入方法](model-integration.md)扩展适配器及分析、报告和复核，并实测新接口 |
| 不同模型或外来测试实例 | 先登记来源并完成参数、信号、运行模式与短采集预验，再决定新增适配器和最小对照工况 |
| 任务依赖实体 HIL、外部控制器或其他仿真模式 | 先明确设备、接口、负责人和运行条件，再规划对应执行支持与验收；现有 Virtual HIL 结果只作方法参考 |

## 如何理解核对状态

- **网页已核**：本次打开了对应官方页面并核对正文或资源入口，证明资料存在及其说明内容。
- **安装含例**：本机 2026.3 安装中找到了指定模型、面板或测试脚本，并核对了文件位置；不代表已经编译或运行。
- **方案介绍已核**：已核对供应商方案中的案例概述、图示说明和所述设备；完整模型、脚本及本项目运行证据另行核对。
- **项目实测**：项目保存了实际运行及数据证据；具体判据结果见[验证状态](validation.md)。实验执行成功、性能通过和文件复核通过分别判断。

Virtual HIL 在 PC 上以非实时方式模拟 HIL 设备，没有外部 I/O；TyphoonSim 使用另一种仿真上下文。官方资料会将 HIL/VHIL 归入 real-time context，但这不表示 PC 上的 Virtual HIL 按墙钟实时运行。选择案例时检查组件、属性和接口的支持状态；模型能在界面中显示也不代表本机具备完整运行条件。依据：[官方 Quick Start](https://www.typhoon-hil.com/documentation/typhoon-hil-software-manual/concepts/realtime_quick_start_guide.html)、[Simulation context definitions](https://www.typhoon-hil.com/documentation/typhoon-hil-software-manual/topics/general_simulation_context_definitions.html)。

## 学习与接口资源

| 资源与入口 | 用途、适合读者 | 版本与模式／条件 | 本项目核对或实测状态 | 核对日期 |
|---|---|---|---|---|
| [官方文档总入口](https://www.typhoon-hil.com/resources/documentation/) | 找软件手册、硬件手册、Application Notes 与 API；各学习阶段均可查阅 | 在线资料会更新；操作细节优先对照安装内同版本资料 | 网页已核；不是实验结果 | 2026-10-15 |
| [Quick Start: THCC](https://www.typhoon-hil.com/documentation/typhoon-hil-software-manual/concepts/realtime_quick_start_guide.html) | 安装、工具入口、示例首次运行和 Virtual HIL 概念；新手 | 同页含实体 HIL、Virtual HIL 和 TyphoonSim 路径；按自己的模式阅读 | 网页已核；项目自己的最小运行证据见 validation | 2026-10-15 |
| [Example Explorer](https://www.typhoon-hil.com/documentation/typhoon-hil-software-manual/concepts/example_explorer.html) | 从标题搜索模型，打开模型及配套应用说明；选择案例时查阅 | THCC 内置入口；每个模型的设备、组件及许可条件分别核对 | 网页已核，安装目录含示例；未逐个运行全库 | 2026-10-15 |
| [Application Notes](https://www.typhoon-hil.com/documentation/typhoon-hil-application-notes/concepts/application_notes_introduction.html) | 看模型原理、工况、测试方法及最低实时硬件；已有领域基础者 | 按应用分类；说明中的实时硬件要求不能直接替代 VHIL 兼容性检查 | 网页已核；下方案例另列本地文件与运行状态 | 2026-10-15 |
| [Schematic Editor API](https://www.typhoon-hil.com/documentation/typhoon-hil-api-documentation/schematic_api.html)；`Documentation/html/schematic_api.html`（安装根目录下） | 创建、读取、改参、保存和编译 tse；运行器维护者 | 在线标题为 Typhoon API 2026.3；使用安装配套 Python | 网页及本地入口已核；项目已使用对应模型操作，未执行页面所有示例 | 2026-10-15 |
| [HIL API](https://www.typhoon-hil.com/documentation/typhoon-hil-api-documentation/hil_api.html)；`Documentation/html/hil_api.html`（安装根目录下） | 加载、初始化、启停、运行改参、信号读取与采集；运行器维护者 | 在线标题为 Typhoon API 2026.3；load_model 的 vhil_device 参数选择 Virtual HIL；各函数有可用场景 | 网页及本地入口已核；项目 RLC/Boost 的实际使用见 validation | 2026-10-15 |
| [TyphoonTest Library](https://www.typhoon-hil.com/documentation/typhoon-hil-typhoontest-library/)；`Documentation/typhoontest_html/index.html`（安装根目录下） | 数据采集、信号判定、RMS、谐波和报告接口；自动测试开发者 | 在线标题为 1.35.6；先确认本机版本，逐函数核对输入、单位与分析窗口 | 网页及本地入口已核；库存在不等于每个分析函数均实测 | 2026-10-15 |
| [TyphoonTest IDE](https://www.typhoon-hil.com/documentation/typhoon-hil-software-manual/concepts/typhoontest_ide.html) | 用 GUI 写、运行 pytest 测试并看日志和报告；希望学习官方测试工具者 | 文档标明 real-time/VHIL；HIL SCADA 与 TyphoonTest IDE 不能同时工作 | 网页已核；本项目统一入口与官方 IDE 的验收分别进行 | 2026-10-15 |
| [HIL Academy 官方介绍](https://www.typhoon-hil.com/solutions/academic-research/hil-academy/)、[课程目录](https://hil.academy/courses/)、[HIL Specialist 2.0](https://hil.academy/hil-specialist-certification-2-0/) | 系统学习工具链、HIL 概念和案例；从入门到进阶 | 官网介绍含五门 HIL Specialist 2.0 课程；课程所用版本、账号与设备要求到具体课程核对 | 介绍与课程入口已核；课程学习与认证完成情况需另行记录 | 2026-10-15 |
| [Knowledge Center](https://www.typhoon-hil.com/resources/knowledge-center/) | 按应用补充视频、网络研讨会及论文线索；任务明确后拓展 | 内容覆盖多个年代、产品与设备；演示视频需对照当前安装 | 网页入口已核；视频与论文中的结果不计为本项目实测 | 2026-10-15 |

Schematic API 负责模型结构与编译，HIL API 负责运行控制与采集；TyphoonTest 提供可进一步采用的官方分析与断言库。**当前 lab.ps1 封装的是 Schematic/HIL API、本项目自己的 Python 分析器和记录复核**，指标由项目代码计算，脚本逻辑测试使用 unittest。TyphoonTest 当前作为已安装库和官方学习资料列出，不表示现有指标调用了它的信号断言。直接复用官方测试前仍需阅读其初始化、运行模式、等待和清理逻辑。

## 模型与公开测试案例

下表的安装路径均相对于本机 **THCC 2026.3 安装根目录**，不是 lab-workflow 根目录。先在 Example Explorer 按模型名搜索；需要修改时按[模型接入方法](model-integration.md)复制到教学项目并保存来源。网页中的设备型号表示其列出的最低**实时**硬件配置。

| 案例／官方说明 | 学习问题与适合读者 | 本地模型或测试入口（安装根目录下） | 版本、模式与设备条件 | 核对／实测状态 | 核对日期 |
|---|---|---|---|---|---|
| RLC circuit | 从改参、采集到解析值比较；首次实验 | `examples/models/basic electrical circuits/rlc circuit/rlc circuit.tse`；项目入口见[首次实验](first-experiment.md) | 安装 2026.3；本项目使用 Virtual HIL | 安装含例；项目基准与 Rin 扫描已有实际数据及复核记录 | 2026-10-15 |
| Boost closed loop | 闭环稳态、参考阶跃和输入扰动；完成 RLC 后学习 | `examples/models/general power electronics/boost closed loop/boost closed loop.tse`；[项目教程](boost-experiments.md) | 安装 2026.3；本项目使用 Virtual HIL | 安装含例；四工况均有实测，具体性能状态见 validation | 2026-10-15 |
| 1ph rectifier | 单相二极管整流桥；学习新模型的信号和判据接入 | `examples/models/general power electronics/1ph rectifier/1ph rectifier.tse`，同目录有 cus | 安装 2026.3；项目实测 Virtual HIL；见[项目教程](rectifier-experiments.md) | 基准、低输入、重载三工况及跨工况比较通过；[验收记录](../results/20261015-rectifier-acceptance/actual_runs.json) | 2026-10-15 |
| Induction machine closed loop control | 独立启动，以及运行中 1430→850 rpm 改速；有电机基础者 | `examples/models/electrical drives/indm closed loop control/indm closed loop control.tse`；`examples/tests/101_indm_closed_loop_control/test_indm_closed_loop_control.py` | 安装 2026.3；HIL101 Pro 1 编译目标，Virtual HIL 实测；模型/面板为本机依赖 | 接口与负载模式已核；[独立启动](../cases/im_speed_tracking/README.md)及[动态阶跃](../cases/im_speed_step/README.md)均已实测，结论见[验证状态](validation.md) | 2026-10-20 |
| Basic loopback tests | pytest 测试函数与参数化；有少量 Python 基础者 | `examples/tests/10_basic_model/test_model_basic.py`、`test_model_parametrized.py`、`model.tse` | 安装 2026.3；所核对的参数化脚本明确设置 `vhil_device=True` | 安装含例且已读脚本；项目 smoke 使用同源模型，原官方 pytest 套件未在本轮执行 | 2026-10-15 |
| Induction machine with open loop control；[Quick Start](https://www.typhoon-hil.com/documentation/typhoon-hil-software-manual/concepts/realtime_quick_start_guide.html) | 电机开环控制和 SCADA；有电机基础者 | `examples/models/electrical drives/indm open loop control/indm open loop control.tse`，同目录有 cus | 安装 2026.3；官方 Quick Start 提供 HIL 与可用时 Virtual HIL 加载路径，仍需核对模型编译目标 | 网页已核、安装含例；未纳入本项目自动实验或实测 | 2026-10-15 |
| [Generic PV plant](https://www.typhoon-hil.com/documentation/typhoon-hil-application-notes/References/generic_pv_plant.html) | HzWatt 曲线、设定值与测量值断言；微电网／并网方向 | `examples/models/microgrid/pv plant/pv plant (generic)/pv plant gen.tse`；`examples/tests/109_pv_plant_generic/test_pv_plant_generic.py` | 安装 2026.3；本机模型编译目标 HIL101 Pro 1，使用 Virtual HIL | [光伏案例](../cases/pv_hzwatt/README.md)已接入 50/51 Hz 独立稳态工况；状态及判据映射修正见[验证页](validation.md) | 2026-10-22 |
| [Electric vehicle](https://www.typhoon-hil.com/documentation/typhoon-hil-application-notes/References/electric_vehicle.html) | 加速性能、转矩／功率曲线、充放电场景；汽车／电驱方向 | `examples/models/automotive/electric vehicle/electric vehicle.tse`；`examples/tests/110_electric_vehicle/test_electric_vehicle.py` | 安装 2026.3；官方列实时 HIL404、Pro 1，并说明实时运行需 Grid Resources；本地测试有 VHIL 分支 | 网页已核、安装含例并已读加载分支；未实测，官方案例本身也含预期不通过的工况 | 2026-10-15 |
| [PMSM torque control using TI F28379D](https://www.typhoon-hil.com/documentation/typhoon-hil-application-notes/References/ti_pmsm_torque_control.html) | 实体控制器的转矩、电流调节和损耗测试；明确开展 C-HIL 的人员 | `examples/models/hardware in the loop/ti pmsm torque control/ti pmsm torque control.tse`；`examples/tests/119_ti_pmsm_torque_control/test_ti_pmsm_torque_control.py` | 安装 2026.3；官方要求 HIL101 Pro 1、TI F28379D LaunchPad、HIL TI 接口及 UniFlash；包含控制器烧写 | 网页已核、安装含例；尚未做设备接入或烧写；不作为本项目现有 VHIL 任务 | 2026-10-15 |
| RLC circuit TyphoonSim | 认识两种仿真上下文的差别；进阶比较 | `examples/models/typhoonsim/rlc circuit typhoonsim/rlc circuit typhoonsim.tse` | 安装 2026.3；TyphoonSim 示例；不沿用当前 Virtual HIL 执行器 | 安装含例；尚未建立 TyphoonSim 运行与指标验证 | 2026-10-15 |

“公开测试案例”在这里指官方公开的应用说明与安装附带的教学测试；本表未将其称为完整标准符合性认证测试套件。接到标准相关任务时，需要取得适用版本、测试范围和验收依据，并逐条映射到具体断言。

## 供应商介绍的应用案例

[汉象技术方案](<../../docs/电机硬件在环（HIL）及自动化测试 - 技术方案.pdf>)第四章列出以下四个用户案例。来源版本为 V.20261021-1.0，核对日期为 2026-10-22；页码按 PDF 文件页序计数，包含封面和目录。下表“应用内容”来自方案概述，“可借鉴的方向”是本项目的选型分析。

| 用户案例与页码 | 方案介绍的应用内容与设备 | 可借鉴的方向 | 接入前需取得的材料 |
|---|---|---|---|
| 同济大学——电机模拟器实时仿真，第 21 页 | 基于 HIL404 的超低速 PMSM 模拟器，面向控制力矩陀螺仪（CMG）万向节电动驱动系统 | 电机模型、低速工况、控制响应及模拟器精度评价 | 对应论文或技术说明、模型与参数、控制器接口、低速测试工况及参考判据 |
| 同济大学——燃料电池快速控制原型系统，第 22 页 | 使用 HIL404 和两相交错升压变换器构建 PEMFC 在线电化学阻抗谱（EIS）测试平台 | 激励设计、同步采集、特征计算与状态分析；结合具体实现区分 RCP 与被控对象仿真职责 | 对应论文、燃料电池及变换器模型、激励与采样设置、阻抗计算方法及参考数据 |
| 企业案例——电机控制实时仿真，第 23 页 | 某国际头部电机驱动企业使用 HIL402 验证电机驱动控制算法 | 外部控制器接入、控制算法测试和自动化结果判定 | 可共享的模型或替代教学模型、控制器接口说明、测试工况、脚本与验收依据 |
| 浣江实验室——微电网/智能电网实时仿真 HIL 平台，第 24 页 | 方案介绍 HIL606、EMS、两台 DSP28377D 控制器及光伏、储能、风机子系统，描述了闭环运行 | 多子系统建模、多控制器协同、系统级工况与实验编排 | 系统拓扑、各子模型、控制器及通信映射、协调策略、调度工况和参考结果 |

四项目前均为“方案介绍已核”：本项目已核对 PDF 概述及图示说明，尚未取得对应的完整模型、脚本与判据，也未开展对应实例的运行验证。文中描述的设备与运行结果属于来源材料中的陈述。向汉象或案例提供方索取可共享材料后，再登记依赖、使用范围和实施路径。

相关学习资源可先从上表官方应用说明与安装示例中筛选：感应电机案例用于熟悉电机测试流程，Boost 用于学习变换器动态分析，Generic PV plant 用于学习并网频率—有功测试与接口接入。这些资源只提供学习与方法参考，与四个用户案例的具体模型、算法和结论分别核对。

水泵控制器在方案前半部分作为具体需求对象描述，单独维护于[水泵控制器 HIL 需求与接入准备](pump-hil-intake.md)。四个用户案例用于拓展应用视野和接入候选；具体实施顺序按[案例层次与选择依据](#案例层次与选择依据)确定。

## 工作区中文补充材料

工作区上级 docs 保存以下中文材料，独立交付 lab-workflow 时按使用范围附带。前两份于 2026-10-15 核对封面、章节入口及相关目录文字；技术方案于 2026-10-22 核对需求与四个用户案例。具体函数、硬件操作和实验结果按实际任务验证。

| 本机文件 | 已核对来源与适用范围 | 使用与验证边界 |
|---|---|---|
| `D:\Typhoon\docs\汉象-实时仿真用户使用指南.pdf` | 74 页；封面署名上海汉象智能科技有限公司。含软件安装、基础使用、连接硬件、示例、I/O、硬件在环演示；基础使用从 PDF 第 8 页开始 | 可作中文界面操作与教学图示补充；公开原始下载来源及与本机 2026.3 的完整对应关系未确认。硬件章节依赖具体设备；当前 API 名称与运行行为按同版本官方资料核对 |
| `D:\Typhoon\docs\电机自动化测试能力归纳.pdf` | 6 页；README 说明为按需求和自动化测试软件整理的能力归纳。包含电机参数、工况、故障和报告线索 | 用于整理候选测试需求；公开原始来源与正式出版身份未确认，PDF 元数据署名不能证明其为官方出版物。表中函数、运行改参与重编译边界须逐项核实，不计入现有项目实测能力 |
| [电机硬件在环（HIL）及自动化测试 - 技术方案](<../../docs/电机硬件在环（HIL）及自动化测试 - 技术方案.pdf>) | 24 页；V.20261021-1.0，编写于 2026-10-21；含水泵控制器需求、系统架构、故障与自动化路线及四个用户案例 | 需求接收与应用选型来源；模型、脚本、设备接口和判据按具体实例补齐；水泵见[专题记录](pump-hil-intake.md)，四个用户案例见上节 |

同版本本地官方资料从 `environment.local.json` 或 `TYPHOON_HOME` 定位本机安装根目录后访问上表所列的 `Documentation/` 路径；也可通过 Control Center 的 Help 入口打开。这样换电脑后不依赖项目与安装目录相邻。

## 选中案例后的操作顺序

1. 明确测试问题，例如“参考值改变后能否在限定时间内回到允许区间”，写明输入、单位、采样和预先固定的判据。
2. 查看应用说明中的模型、测试脚本和设备要求，确认是否需要实体控制器、通信、专用功能库或烧写工具。
3. 从安装目录复制所需文件，保存来源路径、软件版本与哈希；安装目录继续作为原始资料来源。
4. 先检查模型组件、初始条件、输入与测量信号，再编译加载到所选模式；记录真实错误或成功证据。
5. 将手动可解释的最小工况接入统一入口，再扩展参数和工况。原始 CSV、配置、模型副本、事件、日志、指标和代码快照一并留存。
6. 用 verify 复算记录，再请另一位组员按教程复现。更新本页的“项目实测”时，链接实际证据和 validation。

完成课程、跨机器使用或实体设备测试后，只更新对应的真实状态，不以网页介绍或别人演示代替自己的验收记录。

