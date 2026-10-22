# Typhoon HIL 与 AI Agent 教学工作流

本项目提供修改参数、采集波形、比较结果和编写报告的实验流程，面向有电机或电力电子基础、尚不熟悉 Typhoon 与 Python 的读者。常规案例采用官方示例模型；另有从空白原理图建立的 RLC 教学练习。运行使用软件自带 Python，通过统一入口执行。

运行模式为 **Virtual HIL**：模型在电脑上按仿真时间推进，以非实时方式运行，没有外部 I/O。每次实验保存配置、模型副本、代码快照、实际数据和判定依据。

## 选择实验

| 想完成的任务 | 使用模型 | 阅读材料 |
|---|---|---|
| 学会模型操作、采集和报告核对 | RLC | [首次实验](docs/first-experiment.md) |
| 从空白原理图建模、增加测量点并接入脚本 | 自建 RLC 练习 | [建模练习](docs/modeling-practice.md) |
| 改变 Rin，比较稳态 RMS 与解析值 | RLC | [参数与指标](docs/experiments.md) |
| 观察闭环参考阶跃和输入电压扰动 | Boost | [动态实验](docs/boost-experiments.md) |
| 比较电机独立启动后的转速跟踪 | 感应电机闭环 | [电机案例](cases/im_speed_tracking/README.md) |
| 观察运行中转速参考阶跃与闭环响应 | 感应电机闭环 | [转速阶跃动态实验](cases/im_speed_step/README.md) |
| 练习接收简短的新电机测试要求 | 感应电机闭环 | [1000 rpm 接入演练](cases/im_mid_speed_intake/README.md) |
| 查找案例并检查材料与代码支持 | 案例目录 | [案例与 CLI 接口](docs/case-interface.md) |
| 通过自然语言执行或分析实验 | 已支持模型 | [Agent 工作流](docs/agent-workflow.md) |
| 学习如何接收并接入新测试案例 | 单相整流 | [整流实验](docs/rectifier-experiments.md) / [接入方法](docs/model-integration.md) |
| 查找官方教程、示例和公开测试 | 资源导航 | [学习与案例资源](docs/resources.md) |

首次使用建议先做 RLC，再做 Boost；随后用单相整流学习新案例接入。已熟悉统一入口时，可直接选择相应模型的实验配置。

案例标识描述测试问题，模型标识选择适配器；一个模型可对应多个案例。`list-cases --json` 与 `validate-case --case <标识> --json` 为只读检查，分别显示材料完整性、代码支持及实际证据。列表发现成功与单案例校验分开返回；缺失本机模型的案例标为 `missing_local_dependency`。静态通过后仍需实际编译和采集验证。所有官方示例模型与面板统一为本机依赖，使用准备命令从匹配安装补齐；来源规则见 [模型说明](models/README.md)。

## 准备环境并运行

按 [环境配置](docs/environment.md) 指定 Typhoon 安装目录，在包含 `lab.ps1` 的目录执行：

```powershell
Set-Location 'D:\Typhoon\lab-workflow'
.\lab.ps1 doctor
.\lab.ps1 prepare-models
.\lab.ps1 smoke
.\lab.ps1 inspect --model rlc_filter
.\lab.ps1 run --config configs/rlc_baseline.json
```

`doctor` 检查解释器、版本和模块；`prepare-models` 补齐并核对官方模型与面板；`smoke` 实际完成最小编译、加载、运行、读取和停止。`run` 输出本次 `run_dir`，后续核对均使用这个目录。

| 操作 | 命令 |
|---|---|
| 按案例串行运行全部工况并复核 | `.\lab.ps1 run-case --case im_speed_tracking --json` |
| 运行电机转速阶跃并复核 | `.\lab.ps1 run-case --case im_speed_step --json` |
| 运行自建 RLC 模型练习 | 按[建模练习](docs/modeling-practice.md)创建模型，再执行 `practice-model` |
| 检查 Boost 模型 | `.\lab.ps1 inspect --model boost_closed_loop` |
| 扫描 RLC 输入电阻 | `.\lab.ps1 sweep --config configs/rlc_sweep.json` |
| 运行 Boost 基准 | `.\lab.ps1 run --config configs/boost_baseline.json` |
| 运行参考阶跃 | `.\lab.ps1 run --config configs/boost_reference_step.json` |
| 运行输入跌落 | `.\lab.ps1 run --config configs/boost_vin_drop.json` |
| 运行输入升高 | `.\lab.ps1 run --config configs/boost_vin_rise.json` |
| 检查单相整流模型 | `.\lab.ps1 inspect --model single_phase_rectifier` |
| 运行单相整流基准 | `.\lab.ps1 run --config configs/rectifier_baseline.json` |
| 低输入、重载与趋势比较 | 按 [整流教程](docs/rectifier-experiments.md) 执行另两份配置与比较命令 |

`run-case` 按案例配置顺序执行，自动复核各结果并更新本机证据索引；返回的 `run_dir` 为包含各工况的批次目录。性能失败保留原结论并继续，执行或记录异常时停止并登记未运行项。

实验配置的相对路径由入口相对于项目根目录解析。更改工况时另存配置，运行前确定参数、单位、采集窗口和判据。

## 核对结果

将占位路径换成本次实际目录：

```powershell
.\lab.ps1 verify --run-dir 'results/本次实际目录'
.\lab.ps1 report --run-dir 'results/本次实际目录'
.\lab.ps1 verify --run-dir 'results/本次实际目录'
```

`report` 根据已有数据重建报告；`verify` 核对文件哈希并复算指标。两条命令均不启动新仿真。

| 要核对的内容 | 对应文件 |
|---|---|
| 实际参数、模型与执行环境 | `config.json`、`model.tse`、`manifest.json` |
| 原始数据、信号单位和采集时间 | `waveforms.csv`、`capture.json` |
| 指标、分析窗口与判据 | `metrics.json` |
| 动态事件的实际生效证据 | Boost 或电机阶跃运行目录的 `events.json` |
| 图表、解释与执行问题 | `report.html` / `report.md`、`run.log` |
| 源码与结果复核 | `code_snapshot/`、`verification.json` |

RLC 扫描另有 `cases/`、`comparison.csv` 和 `comparison.png`。Boost 与电机阶跃动态工况同时提供完整启动波形和事件区间细节图。结果始终写入新目录。

实验状态分为 `passed`、`failed`、`error`、`skipped`。复核输出中的 `record_status` 表示记录与复算是否一致，`experiment_status` 表示实验是否满足判据；总状态要求两者均通过。具体已验证能力、未达标项目和证据集中在 [验证状态](docs/validation.md)。

## 继续使用和维护

- 执行异常：按 [故障排查](docs/troubleshooting.md) 根据阶段定位。
- 其他人接手：按 [交接验收](docs/handoff.md) 独立复现。
- 查看输入扰动的现象与候选机制：阅读 [Boost 扰动分析](docs/boost-disturbance-analysis.md)。
- 接入其他模型：按 [模型接入方法](docs/model-integration.md) 建立参数、信号、判据和实际证据。
- 自行建模：按 [建模练习](docs/modeling-practice.md)复现电路、测量点、编译、采集与结果复核。
- 维护入口、记录或文档：阅读 [实现约定](PROJECT_SPEC.md) 与 [Agent 项目指令](AGENTS.md)。
- 安排后续建设：参照 [能力准备与长期规划](docs/roadmap.md)，按近期优先级和长期扩展条件确定范围。
- 准备水泵控制器测试：阅读 [HIL 需求与接入准备](docs/pump-hil-intake.md)，核对需求、已有基础、缺失材料和下一步完成依据。

搬到另一台电脑时保留目录结构，更新本机安装路径，再执行环境检查、最小仿真及所选实验。软件和许可由设备管理者配置。官方模型与面板通过 `prepare-models` 从目标机器的匹配安装补齐；实体 HIL 与外部控制器按具体设备和任务另行验证。
