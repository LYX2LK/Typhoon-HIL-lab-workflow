# 官方学习资源与案例导航

本页供有电机或电力电子基础、尚不熟悉 Typhoon/Python 的组员选学习材料和测试案例。目标是先完成一个可解释、可复核的实验，再选择与手头任务相近的案例。核对日期：**2026-10-15（北京时间）**；本机参考安装：**Typhoon HIL Control Center 2026.3**。

## 先按任务选择

| 现在要做什么 | 优先入口 | 做到什么程度 |
|---|---|---|
| 第一次使用软件 | 本项目[环境配置](environment.md) → [首次实验](first-experiment.md) | 完成 doctor、smoke、RLC 实验和 verify |
| 学模型、面板和采集的 GUI 操作 | 官方 Quick Start、Example Explorer、HIL Specialist 课程 | 能说明打开、编译、加载、启动、改参、采集和停止的对应操作 |
| 让 Agent 执行实验 | 本项目[Agent 工作流](agent-workflow.md) | 能从任务描述追到配置、原始数据、报告及复核结果 |
| 学自动化接口或修改运行器 | Schematic API → HIL API → TyphoonTest | 先区分模型结构操作、运行操作、数据分析和测试断言 |
| 接收一个新测试实例 | 本项目[模型接入方法](model-integration.md) → 下方案例表 | 先核对版本、运行模式、输入、信号、判据和设备条件，再建副本运行 |

## 如何理解核对状态

- **网页已核**：本次打开了对应官方页面并核对正文或资源入口，证明资料存在及其说明内容。
- **安装含例**：本机 2026.3 安装中找到了指定模型、面板或测试脚本，并核对了文件位置；不代表已经编译或运行。
- **项目实测**：项目保存了实际运行及数据证据；具体判据结果见[验证状态](validation.md)。实验执行成功、性能通过和文件复核通过分别判断。

Virtual HIL 在 PC 上以非实时方式模拟 HIL 设备，没有外部 I/O；TyphoonSim 使用另一种仿真上下文。官方资料会将 HIL/VHIL 归入 real-time context，但这不表示 PC 上的 Virtual HIL 按墙钟实时运行。选择案例时检查组件、属性和接口的支持状态；模型能在界面中显示也不代表本机具备完整运行条件。依据：[官方 Quick Start](https://www.typhoon-hil.com/documentation/typhoon-hil-software-manual/concepts/realtime_quick_start_guide.html)、[Simulation context definitions](https://www.typhoon-hil.com/documentation/typhoon-hil-software-manual/topics/general_simulation_context_definitions.html)。

## 学习与接口资源

| 资源与入口 | 用途、适合读者 | 版本与模式／条件 | 本项目核对或实测状态 | 核对日期 |
|---|---|---|---|---|
| [官方文档总入口](https://www.typhoon-hil.com/resources/documentation/) | 找软件手册、硬件手册、Application Notes 与 API；所有组员 | 在线资料会更新；操作细节优先对照安装内同版本资料 | 网页已核；不是实验结果 | 2026-10-15 |
| [Quick Start: THCC](https://www.typhoon-hil.com/documentation/typhoon-hil-software-manual/concepts/realtime_quick_start_guide.html) | 安装、工具入口、示例首次运行和 Virtual HIL 概念；新手 | 同页含实体 HIL、Virtual HIL 和 TyphoonSim 路径；按自己的模式阅读 | 网页已核；项目自己的最小运行证据见 validation | 2026-10-15 |
| [Example Explorer](https://www.typhoon-hil.com/documentation/typhoon-hil-software-manual/concepts/example_explorer.html) | 从标题搜索模型，打开模型及配套应用说明；选案例的组员 | THCC 内置入口；每个模型的设备、组件及许可条件分别核对 | 网页已核，安装目录含示例；未逐个运行全库 | 2026-10-15 |
| [Application Notes](https://www.typhoon-hil.com/documentation/typhoon-hil-application-notes/concepts/application_notes_introduction.html) | 看模型原理、工况、测试方法及最低实时硬件；已有领域基础者 | 按应用分类；说明中的实时硬件要求不能直接替代 VHIL 兼容性检查 | 网页已核；下方案例另列本地文件与运行状态 | 2026-10-15 |
| [Schematic Editor API](https://www.typhoon-hil.com/documentation/typhoon-hil-api-documentation/schematic_api.html)；`Documentation/html/schematic_api.html`（安装根目录下） | 创建、读取、改参、保存和编译 tse；运行器维护者 | 在线标题为 Typhoon API 2026.3；使用安装配套 Python | 网页及本地入口已核；项目已使用对应模型操作，未执行页面所有示例 | 2026-10-15 |
| [HIL API](https://www.typhoon-hil.com/documentation/typhoon-hil-api-documentation/hil_api.html)；`Documentation/html/hil_api.html`（安装根目录下） | 加载、初始化、启停、运行改参、信号读取与采集；运行器维护者 | 在线标题为 Typhoon API 2026.3；load_model 的 vhil_device 参数选择 Virtual HIL；各函数有可用场景 | 网页及本地入口已核；项目 RLC/Boost 的实际使用见 validation | 2026-10-15 |
| [TyphoonTest Library](https://www.typhoon-hil.com/documentation/typhoon-hil-typhoontest-library/)；`Documentation/typhoontest_html/index.html`（安装根目录下） | 数据采集、信号判定、RMS、谐波和报告接口；自动测试开发者 | 在线标题为 1.35.6；先确认本机版本，逐函数核对输入、单位与分析窗口 | 网页及本地入口已核；库存在不等于每个分析函数均实测 | 2026-10-15 |
| [TyphoonTest IDE](https://www.typhoon-hil.com/documentation/typhoon-hil-software-manual/concepts/typhoontest_ide.html) | 用 GUI 写、运行 pytest 测试并看日志和报告；希望学习官方测试工具者 | 文档标明 real-time/VHIL；HIL SCADA 与 TyphoonTest IDE 不能同时工作 | 网页已核；本项目统一入口与官方 IDE 的验收分别进行 | 2026-10-15 |
| [HIL Academy 官方介绍](https://www.typhoon-hil.com/solutions/academic-research/hil-academy/)、[课程目录](https://hil.academy/courses/)、[HIL Specialist 2.0](https://hil.academy/hil-specialist-certification-2-0/) | 系统学习工具链、HIL 概念和案例；新手至进阶组员 | 官网介绍含五门 HIL Specialist 2.0 课程；课程所用版本、账号与设备要求到具体课程核对 | 介绍与课程入口已核；未代替组员登录上课，也未宣称完成认证 | 2026-10-15 |
| [Knowledge Center](https://www.typhoon-hil.com/resources/knowledge-center/) | 按应用补充视频、网络研讨会及论文线索；任务明确后拓展 | 内容覆盖多个年代、产品与设备；演示视频需对照当前安装 | 网页入口已核；视频与论文中的结果不计为本项目实测 | 2026-10-15 |

Schematic API 负责模型结构与编译，HIL API 负责运行控制与采集；TyphoonTest 提供可进一步采用的官方分析与断言库。**当前 lab.ps1 封装的是 Schematic/HIL API、本项目自己的 Python 分析器和记录复核**，指标由项目代码计算，脚本逻辑测试使用 unittest。TyphoonTest 当前作为已安装库和官方学习资料列出，不表示现有指标调用了它的信号断言。直接复用官方测试前仍需阅读其初始化、运行模式、等待和清理逻辑。

## 模型与公开测试案例

下表的安装路径均相对于本机 **THCC 2026.3 安装根目录**，不是 lab-workflow 根目录。先在 Example Explorer 按模型名搜索；需要修改时按[模型接入方法](model-integration.md)复制到教学项目并保存来源。网页中的设备型号表示其列出的最低**实时**硬件配置。

| 案例／官方说明 | 学习问题与适合读者 | 本地模型或测试入口（安装根目录下） | 版本、模式与设备条件 | 核对／实测状态 | 核对日期 |
|---|---|---|---|---|---|
| RLC circuit | 从改参、采集到解析值比较；首次实验 | `examples/models/basic electrical circuits/rlc circuit/rlc circuit.tse`；项目入口见[首次实验](first-experiment.md) | 安装 2026.3；本项目使用 Virtual HIL | 安装含例；项目基准与 Rin 扫描已有实际数据及复核记录 | 2026-10-15 |
| Boost closed loop | 闭环稳态、参考阶跃和输入扰动；完成 RLC 后学习 | `examples/models/general power electronics/boost closed loop/boost closed loop.tse`；[项目教程](boost-experiments.md) | 安装 2026.3；本项目使用 Virtual HIL | 安装含例；四工况均有实测，具体性能状态见 validation | 2026-10-15 |
| 1ph rectifier | 单相二极管整流桥；学习新模型的信号和判据接入 | `examples/models/general power electronics/1ph rectifier/1ph rectifier.tse`，同目录有 cus | 安装 2026.3；项目实测 Virtual HIL；见[项目教程](rectifier-experiments.md) | 基准、低输入、重载三工况及跨工况比较通过；[验收记录](../results/20261015-rectifier-acceptance/actual_runs.json) | 2026-10-15 |
| Basic loopback tests | pytest 测试函数与参数化；有少量 Python 基础者 | `examples/tests/10_basic_model/test_model_basic.py`、`test_model_parametrized.py`、`model.tse` | 安装 2026.3；所核对的参数化脚本明确设置 `vhil_device=True` | 安装含例且已读脚本；项目 smoke 使用同源模型，原官方 pytest 套件未在本轮执行 | 2026-10-15 |
| Induction machine with open loop control；[Quick Start](https://www.typhoon-hil.com/documentation/typhoon-hil-software-manual/concepts/realtime_quick_start_guide.html) | 电机开环控制和 SCADA；有电机基础者 | `examples/models/electrical drives/indm open loop control/indm open loop control.tse`，同目录有 cus | 安装 2026.3；官方 Quick Start 提供 HIL 与可用时 Virtual HIL 加载路径，仍需核对模型编译目标 | 网页已核、安装含例；未纳入本项目自动实验或实测 | 2026-10-15 |
| [Generic PV plant](https://www.typhoon-hil.com/documentation/typhoon-hil-application-notes/References/generic_pv_plant.html) | HzWatt 曲线、设定值与测量值断言；微电网／并网方向 | `examples/models/microgrid/pv plant/pv plant (generic)/pv plant gen.tse`；`examples/tests/109_pv_plant_generic/test_pv_plant_generic.py` | 安装 2026.3；官方列实时 HIL101、Base 1；本地测试有 VHIL 分支，但本机可用性需实际编译加载确认 | 网页已核、安装含例并已读加载分支；未实测 | 2026-10-15 |
| [Electric vehicle](https://www.typhoon-hil.com/documentation/typhoon-hil-application-notes/References/electric_vehicle.html) | 加速性能、转矩／功率曲线、充放电场景；汽车／电驱方向 | `examples/models/automotive/electric vehicle/electric vehicle.tse`；`examples/tests/110_electric_vehicle/test_electric_vehicle.py` | 安装 2026.3；官方列实时 HIL404、Pro 1，并说明实时运行需 Grid Resources；本地测试有 VHIL 分支 | 网页已核、安装含例并已读加载分支；未实测，官方案例本身也含预期不通过的工况 | 2026-10-15 |
| [PMSM torque control using TI F28379D](https://www.typhoon-hil.com/documentation/typhoon-hil-application-notes/References/ti_pmsm_torque_control.html) | 实体控制器的转矩、电流调节和损耗测试；明确开展 C-HIL 的人员 | `examples/models/hardware in the loop/ti pmsm torque control/ti pmsm torque control.tse`；`examples/tests/119_ti_pmsm_torque_control/test_ti_pmsm_torque_control.py` | 安装 2026.3；官方要求 HIL101 Pro 1、TI F28379D LaunchPad、HIL TI 接口及 UniFlash；包含控制器烧写 | 网页已核、安装含例；尚未做设备接入或烧写；不作为本项目现有 VHIL 任务 | 2026-10-15 |
| RLC circuit TyphoonSim | 认识两种仿真上下文的差别；进阶比较 | `examples/models/typhoonsim/rlc circuit typhoonsim/rlc circuit typhoonsim.tse` | 安装 2026.3；TyphoonSim 示例；不沿用当前 Virtual HIL 执行器 | 安装含例；尚未建立 TyphoonSim 运行与指标验证 | 2026-10-15 |

“公开测试案例”在这里指官方公开的应用说明与安装附带的教学测试；本表未将其称为完整标准符合性认证测试套件。接到标准相关任务时，需要取得适用版本、测试范围和验收依据，并逐条映射到具体断言。

## 工作区中文补充材料

本机另有两份中文 PDF，位置由工作区 `D:\Typhoon\docs\README.txt` 说明。它们用于辅助阅读，不随 lab-workflow 的独立搬迁自动附带。核对日期均为 2026-10-15；已检查封面、章节入口及相关目录文字，未逐条验证其中的全部函数和硬件步骤。

| 本机文件 | 已核对来源与适用范围 | 使用与验证边界 |
|---|---|---|
| `D:\Typhoon\docs\汉象-实时仿真用户使用指南.pdf` | 74 页；封面署名上海汉象智能科技有限公司。含软件安装、基础使用、连接硬件、示例、I/O、硬件在环演示；基础使用从 PDF 第 8 页开始 | 可作中文界面操作与教学图示补充；公开原始下载来源及与本机 2026.3 的完整对应关系未确认。硬件章节依赖具体设备；当前 API 名称与运行行为按同版本官方资料核对 |
| `D:\Typhoon\docs\电机自动化测试能力归纳.pdf` | 6 页；README 说明为按需求和自动化测试软件整理的能力归纳。包含电机参数、工况、故障和报告线索 | 用于整理候选测试需求；公开原始来源与正式出版身份未确认，PDF 元数据署名不能证明其为官方出版物。表中函数、运行改参与重编译边界须逐项核实，不计入现有项目实测能力 |

同版本本地官方资料从 `environment.local.json` 或 `TYPHOON_HOME` 定位本机安装根目录后访问上表所列的 `Documentation/` 路径；也可通过 Control Center 的 Help 入口打开。这样换电脑后不依赖项目与安装目录相邻。

## 选中案例后的操作顺序

1. 明确测试问题，例如“参考值改变后能否在限定时间内回到允许区间”，写明输入、单位、采样和预先固定的判据。
2. 查看应用说明中的模型、测试脚本和设备要求，确认是否需要实体控制器、通信、专用功能库或烧写工具。
3. 从安装目录复制所需文件，保存来源路径、软件版本与哈希；安装目录继续作为原始资料来源。
4. 先检查模型组件、初始条件、输入与测量信号，再编译加载到所选模式；记录真实错误或成功证据。
5. 将手动可解释的最小工况接入统一入口，再扩展参数和工况。原始 CSV、配置、模型副本、事件、日志、指标和代码快照一并留存。
6. 用 verify 复算记录，再请另一位组员按教程复现。更新本页的“项目实测”时，链接实际证据和 validation。

组员完成课程、跨机器使用或实体设备测试后，只更新对应的真实状态，不以网页介绍或别人演示代替自己的验收记录。

