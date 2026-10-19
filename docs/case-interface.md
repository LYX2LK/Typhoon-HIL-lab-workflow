# 案例发现、静态校验与 CLI 协议

本页面向项目维护者及需要稳定工具返回的 Agent。案例描述测试问题；模型标识选择代码中显式注册的适配器。完整接入方法见 [模型接入](model-integration.md)，日常任务见 [Agent 工作流](agent-workflow.md)。

## 查找和校验

```powershell
.\lab.ps1 list-cases --json
.\lab.ps1 validate-case --case im_speed_tracking --json
.\lab.ps1 --json run --config configs/im_speed_1430.json
```

list-cases 与 validate-case 只读取文件，不调用 Typhoon API、不启动仿真、不写结果。存在本机案例证据索引时，会离线复算相关记录。输出将以下范围分开：

| 字段 | 含义 |
|---|---|
| integrity | 案例结构、引用、模型/面板哈希及配置身份 |
| software_support | Adapter 是否注册、对应配置与执行能力是否支持 |
| runtime_validation | 实际记录能否证明链路完成；缺失或模型、配置、代码摘要变化时为 not_verified |

静态总 status=passed 表示前两类检查通过。runtime_validation.completed 可包含性能 failed 的有效记录；每个工况的 experiment_status 单列。不能从静态结果推断本机可编译或可加载。

software_support.capabilities 列出适配器声明的配置版本、运行接口、事件能力和采集信号；configuration_checks 逐项呈现 passed、failed 或 not_checked。未注册、依赖不可用和校验器尚未实现分别保留缺口信息，未检查的配置不会算作通过。

## 案例说明

每个案例使用 cases/<case_id>/case.json，版本为整数 1，字段为 schema_version、case_id、model_id、title、backend、model_origin_ref、configs、acceptance_ref。一个模型可以有多个案例；configs 是非空且不重复的配置引用列表。case_id 与所在目录同名。

案例说明只维护元信息与引用。实验参数保留在配置，公式与适用条件保留在判据文档，模型哈希保留在 models/origin.json。新增来源仍按 models/<model_id>.tse 约定落地；这轮不支持由 JSON 指定任意模型加载路径或 Python 类。

configs 和 model_origin_ref 相对于项目根目录，分别限制在 configs/ 与 models/；来源索引固定为 models/origin.json。acceptance_ref 相对于当前案例目录，并限制在该目录内。所有引用禁止绝对路径、盘符、父目录段和替代数据流，解析后检查符号链接/目录联接边界。命令的 --case 接受标识或项目 cases/ 内的 case.json 路径。

本机可在 results/case-validation/<case_id>/latest.json 留存可选证据索引：runs 数组中的每项为 config（项目相对配置路径）和 run_dir（项目相对结果目录）。每份引用配置均须对应完整记录。工具检查模型、配置与当前代码摘要，并以 write=False 复算记录；索引不构成运行授权，不随案例元信息伪造实测状态。

## JSON 返回

--json 支持放在子命令前或后。标准输出只返回一个 JSON 对象；进度、Typhoon API/native 输出和堆栈送往标准错误。--json 与 --help 同用时帮助写标准错误，result.help_on_stderr=true。

| 字段 | 规则 |
|---|---|
| schema_version / command | 协议整数 1；可识别命令名，未知命令为 null |
| status | 当前命令结果 passed/failed/error/skipped；报告生成成功对应 passed |
| run_dir / artifacts | 实际目录；产物名称到实际路径的映射；无产物时为空 |
| record_status | 仅 verify 实际复核后填写；run/report 不自动声明记录通过 |
| experiment_status | 已有实验执行/性能状态；静态任务为 null |
| result | 原命令返回内容及检查详情 |
| error | 执行错误对象 code/stage/message；正常性能未达标可为 null |

命令生成报告成功而原实验 failed 时，status=passed、experiment_status=failed、record_status=null。verify 可返回 record_status=passed、experiment_status=failed，总 status=failed。

保留默认模式的结果与退出码：0 为成功；1 为已形成但未通过的命令结果（包含执行器留存的 error）；2 为参数、启动、入口导入或外层执行异常。JSON 不重新解释为另一套退出码。PowerShell 启动错误采用同一信封；Python 返回非零实验结果时不再追加第二个响应。

原有 inspect/doctor 会写本机检查记录，verify 会写 verification.json，report 会更新报告与清单；它们的副作用与这两个只读案例命令不同。历史记录需复核或重建时按 [记录约定](../PROJECT_SPEC.md#历史记录处理) 在副本操作。
