# 环境配置与检查

本文帮助首次接手项目的组员确认：当前电脑可以通过项目入口调用 Typhoon 的 Python API，并能够运行 Virtual HIL 教学实验。软件已正常启动且具备许可，是开始检查的前提；具体 API 和仿真能力以本机检查记录为准。

## 准备项目

1. 将完整的 `lab-workflow` 项目放到可写目录，并在 PowerShell 中进入项目根目录。下文所有命令均从包含 `lab.ps1` 的目录执行。
2. 使用与项目匹配的 Typhoon HIL Control Center 安装。当前工作区参考版本为 2026.3。
3. 查看项目根目录的 `environment.local.json`，将 `typhoon_home` 设置为本机 Typhoon 安装目录。`lab.ps1` 根据该目录定位软件配套的 Python，无需另行安装 Python。
4. 在 Codex 中选择 `lab-workflow` 为工作目录，使项目的 [AGENTS.md](../AGENTS.md) 与 [README](../README.md) 可被读取。

`environment.local.json` 的示例内容如下，复制项目到另一台电脑后按实际安装位置修改：

```json
{
  "typhoon_home": "D:\\Typhoon\\Typhoon HIL Control Center 2026.3"
}
```

入口按以下顺序定位安装：`TYPHOON_HOME` 环境变量、JSON 中的 `typhoon_home`、项目父目录下带有 `python3_portable/python.exe` 的 Control Center 安装。团队日常使用建议统一维护本机 JSON 配置；检查输出中的最终路径，尤其注意环境变量是否覆盖了配置。入口不自动安装软件。

搬移项目时应保留模型、脚本、配置和文档的相对目录结构，并更新本机路径配置。实验配置使用项目内相对路径，运行结果保存在 [results](../results/) 下。

## 分两步确认能力

先运行：

```powershell
.\lab.ps1 doctor
```

`doctor` 检查解释器、软件版本及必要模块导入。阅读输出中的路径和失败项，确认调用了预期的软件安装。模块导入通过只说明脚本具备加载 API 的基础。

随后运行：

```powershell
.\lab.ps1 smoke
```

`smoke` 执行一次最小仿真链：编译模型、加载 Virtual HIL、启动、读取实际仿真数据并停止。将实际输出目录记入实验记录；通过的依据是完整执行日志和真实采集数据。

2026-10-14 本机搭建已通过 `doctor`、`inspect` 与 `smoke`。配套版本为 Python 3.11.4、Typhoon-HIL-API 1.32.1、TyphoonTest 1.35.6；最小回环实验将输入设为 -10、0、10，实际读到 `Probe1` 的对应值，并成功停止仿真。记录位于 [本次 smoke 目录](../results/20261014-212943-smoke-a2a022/)。RLC 基准与 Rin=1/5/10 Ω 扫描也已通过数值判据及报告重建后的复算，图表 QA 和 24 项单元测试通过；完整记录见 [实测验收](validation.md)。换电脑后重新执行环境与仿真检查。

## 理解本版运行模式

本版选用 Virtual HIL：在电脑上模拟 HIL 设备，按仿真时间推进，运行速度取决于模型和电脑。它采用非实时运行方式，且没有外部 I/O。因此，本教程可以验证模型操作、自动采集和报告流程；真实控制器闭环接入须在课题组设备信息明确后建立单独的验证记录。以上特性见官方 [Control Center Quick Start](<../../Typhoon HIL Control Center 2026.3/typhoon/help/t-ug002/concepts/realtime_quick_start_guide.html>) 中 “Run a model using Virtual HIL”。

`inspect` 输出中的 `HIL101`、`Pro 1` 表示模型的编译目标与配置。该信息描述软件模拟的目标，不代表本机已经连接了实体 HIL101。TyphoonSim 是另一种仿真路径；本项目运行入口固定为 Virtual HIL，配置和记录均应注明这一模式。

## 查阅匹配版本的资料

- [Control Center 入门与 Virtual HIL](<../../Typhoon HIL Control Center 2026.3/typhoon/help/t-ug002/concepts/realtime_quick_start_guide.html>)：许可、示例打开、加载和运行。
- [Schematic API](<../../Typhoon HIL Control Center 2026.3/Documentation/html/schematic_api.html>)：模型操作、属性修改、保存和编译。
- [HIL API](<../../Typhoon HIL Control Center 2026.3/Documentation/html/hil_api.html>)：加载模型、设置源、启动与停止仿真。
- [TyphoonTest Library](<../../Typhoon HIL Control Center 2026.3/Documentation/typhoontest_html/index.html>)：采集和测试工具。

这些本地链接对应当前安装目录；换电脑后可从 Control Center 的帮助入口找到随软件安装的同版本资料。线上 [Typhoon 软件指南](https://www.typhoon-hil.com/documentation/typhoon-hil-software-manual/) 与 [API 文档](https://www.typhoon-hil.com/documentation/typhoon-hil-api-documentation/) 可用于检索，并应核对版本差异。

下一步：[完成首次实验](first-experiment.md)。遇到错误：[故障排查](troubleshooting.md)。
