# Boost + AI 在线分析与确认复验

面向会议演示人员和维护者。用现有 Boost 输入跌落案例展示：Typhoon Virtual HIL 实验、原始采集、确定性判定、真实模型服务分析、人员确认、对照实验与解释更新。该连接对应 roadmap 中已有案例自动化执行和结果分析的近期目标。

## 开始演示

1. 将 `demo.env.example` 复制为根目录的 `demo.env.local`，填写 `DEEPSEEK_API_KEY`。环境变量同名值优先；文件支持 UTF-8/BOM、空行和注释。密钥文件已被 Git 忽略，不进入源码快照或报告。
2. 在项目根目录执行 `./lab.ps1 demo-boost --port 8765`，打开 <http://127.0.0.1:8765>。服务仅监听本机。
3. 点击“开始新实验与在线分析”。程序经原有互斥执行器编译、运行、采集和停止自身启动的仿真，复核原始记录后自动调用模型。初次 Typhoon 后台启动可能明显慢于后续运行。
4. 查看波形、固定判据、模型观察及证据引用。选择“延后至1.0 s施扰”，点击“展示验证方案”。先显示差异，再填写操作者、勾选确认并执行。
5. 查看对照波形、指标和模型更新解释。完整报告可单独离线打开；API失败时显示错误，保留证据，使用已有报告备用。

网页与命令行均调用固定白名单执行器。模型只能建议 `repeat`、`baseline`、`late`，不能提供脚本、路径或任意参数作为执行指令。模型未建议所选动作时，计划记录 `experimenter_selection`。

## 命令行分步接口

```powershell
.\lab.ps1 run --config configs/boost_vin_drop.json --json
.\lab.ps1 verify --run-dir '本次实际运行目录' --json
.\lab.ps1 analyze-boost --source-run '本次实际运行目录' --service configs/ai_service_deepseek.json --output-dir '新的分析目录' --json
.\lab.ps1 verify-boost-ai --run-dir '新的分析目录' --write --json
.\lab.ps1 plan-boost --analysis-run '新的分析目录' --action late --output-dir '新的计划目录' --json
# 展示 plan.json 中的目的和 differences；确认后使用该计划返回的 token：
.\lab.ps1 execute-boost-plan --plan-dir '新的计划目录' --confirm '该计划token' --confirmed-by '实际确认人员' --json
.\lab.ps1 analyze-boost --source-run '首次目录' --source-run '对照目录' --previous '首次分析目录' --plan-dir '计划目录' --service configs/ai_service_deepseek.json --output-dir '新的比较目录' --json
.\lab.ps1 verify-boost-ai --run-dir '新的比较目录' --write --json
```

路径相对项目根解析。省略 `--service` 只组织证据和待分析请求，`explanation_status=pending`，不称在线分析成功。API/响应校验失败保留 `model_call.json`、已发送请求及已有原始响应，状态为 error，分析记录整体为 incomplete；返回1。参数或外层执行异常返回2。模型调用完成的分析返回0。

## 输入、指标与状态

仅接受复核一致且采集/事件有效的 `boost_closed_loop` 仿真运行。源包完整复制到 `sources/R1`、`R2`；重用 `boost_analysis.analyze` 从 CSV 复算原判据，补充事件前0.1 s描述性线性趋势及事件后[0,0.9) s比较。每个动态工况比较窗为9,000点，按实际事件首次变化采样对齐，不滤波、不插值。无扰动基准使用0.5 s作为明确的比较参考时刻，不把它称为实际事件。

延后方案仅把事件0.5 s改成1.0 s，采集1.5 s改成2.0 s，最少样本15000改成20000。其他参数、PI、采样率和性能阈值保留。对照配置与来源分析均绑定哈希，配置变更、无确认、重复确认时拒绝执行。重复实验用于运行一致性检查；确定性模型的重复相同波形不能给出统计诊断准确率。

原实验的 `record_status` 与 `experiment_status` 独立：原始记录一致而峰偏差越限时分别为passed、failed。派生分析 `boost_ai` 的 `experiment_status=null`，其manifest的passed只表示模型回答通过结构/引用校验；不表示设备、控制性能或因果解释被验证。

## 模型服务与复核

服务事实位于 `configs/ai_service_deepseek.json`；默认 DeepSeek 官方 `deepseek-flash`，非思考模式、JSON Output、非流式、120 s超时。`http_request.json`不含认证头；`http_response.json`保存真实API字节，`model_call.json`保存提供方、请求/返回模型、请求哈希、usage、耗时及错误类型。拒绝自动重定向，以免把认证头传到其他地址。失败不生成手写替代回答，也不自动重复计费调用。

回答必须保留 `cause_status=undetermined`，引用现有 evidence 键，验证动作属于白名单。校验包括请求哈希、非空JSON、完成标记、必需字段和引用。**这些检查不能证明自然语言物理推理正确**；报告要求复阅。数值和性能状态以确定性表格为准。当前案例是既有软件实验复现，既不是盲测，也没有确诊芯片故障。

`verify-boost-ai`从包内CSV独立重算证据和请求，核对真实响应与answer、前次分析与确认链。默认只读，`--write`写verification.json；通用verify也可处理该类型。它不重新调用模型。历史包按PROJECT_SPEC复制后复核；重新解释创建新目录。

当前接入仅覆盖Boost；外部波形的`diagnose-waveforms`仍采用其独立数据结构和解释导入流程。两种输入能力的验证范围分别报告。

官方接口依据：[DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/)、[Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)。
