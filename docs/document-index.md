# 文档导航

本页说明各文档解决什么问题。按任务选择入口先看 [README](../README.md)；具体参数、步骤和结论以所链接的页面及当前案例为准。

| 类别 | 文档 | 何时阅读 |
|---|---|---|
| 入门 | [样机测试零基础图文教程](beginner/index.html)、[Markdown 正文](beginner/README.md) | 从电压、电流和芯片开始，学习引线、电机控制、反馈、LIN/PWM 与软件预演，配原图、手册截图和练习答案 |
| 入门 | [首次实验](first-experiment.md) | 用 RLC 完成 GUI 操作、采集、报告与复核 |
| 入门 | [建模练习](modeling-practice.md) | 从空白图建立 RLC、增加测量点、脚本采集并独立重做 GUI 操作 |
| 实验 | [RLC 参数扫描](experiments.md) | 查看参数、信号与解析判据 |
| 实验 | [Boost 动态实验](boost-experiments.md) | 运行参考阶跃和输入扰动，理解分析窗口 |
| 实验 | [单相整流](rectifier-experiments.md) | 学习新案例的工况、判据和比较 |
| 方法 | [Boost 扰动分析](boost-disturbance-analysis.md) | 查原始数据复算、对照结果与解释边界 |
| 接收 | [外部波形](external-waveforms.md) | 按 CSV/PNG 清单做离线分析与复核 |
| 接收 | [现场数据](field-data.md)、[采集交接](tle9877-data-collection.md) | 整理多通道 CSV 与 LIN 日志，保留时钟依据并按已确认项目作离线判定 |
| 分析 | [波形异常识别](waveform-diagnosis.md) | 从数据包识别形态异常、定位事件并导入大模型解释 |
| 分析 | [Boost + AI 在线演示](boost-ai-demo.md) | 从Virtual HIL记录调用真实模型，展示差异并确认对照实验 |
| 分析 | [对话式实验Agent](agent.md) | 模型调用证据工具、编排回答与选项，确认后多轮实验并更新解释 |
| 接入 | [模型接入](model-integration.md) | 登记新模型来源，建立适配器、判据和验证 |
| 接入 | [案例与 CLI 接口](case-interface.md) | 查询案例发现、字段和 JSON 协议 |
| 任务 | [Agent 工作流](agent-workflow.md) | 用自然语言提出实验任务并核对结果 |
| 需求 | [水泵控制器需求](pump-hil-intake.md) | 查该专题的材料、缺口和接入准备 |
| 接入 | [寄送控制板接口与 LIN](tle9877-hil-intake.md) | 查本次控制板引线、PMSM 参数、LIN/PWM 协议及剩余联调条件 |
| 实验 | [样机软件准备](tle9877-software-preparation.md) | 执行参数/接口检查、LIN 离线编解码和 PMSM 软件预演 |
| 接入 | [样机现场联调](tle9877-field-commissioning.md)、[LIN 设备接口与 Mock](tle9877-lin-adapter.md) | 填写 I/O 合同、电机参数及现场记录，预演设备调用与错误日志 |
| 查找 | [学习资源与案例](resources.md) | 选择案例及查找官方资料 |
| 环境 | [环境配置](environment.md) | 指定安装目录、准备模型和做最小检查 |
| 排错 | [故障排查](troubleshooting.md) | 按失败阶段定位问题 |
| 交接 | [独立复现与交接](handoff.md) | 搬迁、复现和验收教学副本 |
| 验证 | [验证状态](validation.md) | 查当前能力、实测结论与待验范围 |
| 验证 | [验证记录索引](validation-history.md) | 按日期查实际证据 |
| 规划 | [路线图](roadmap.md) | 查建设方向、优先级和扩展条件 |

项目长期约束见 [AGENTS](../AGENTS.md)；执行器、记录和文档维护约定见 [PROJECT_SPEC](../PROJECT_SPEC.md)。
