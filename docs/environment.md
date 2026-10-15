# 环境配置与检查

本页帮助首次接手的组员确认：项目能调用预期的 Typhoon Python API，并完成最小 Virtual HIL 仿真。准备好已安装、可正常启动且具备许可的 Typhoon HIL Control Center；参考安装为 2026.3。

## 指定本机安装目录

将完整项目放到可写目录，保留脚本、配置、模型和文档的相对结构。在项目根目录的 `environment.local.json` 中填写：

```json
{
  "typhoon_home": "D:\\Typhoon\\Typhoon HIL Control Center 2026.3"
}
```

lab.ps1 按顺序使用 TYPHOON_HOME 环境变量、本机 JSON 中的 typhoon_home、项目父目录中唯一可用的 Control Center 安装。有效安装应包含 `python3_portable/python.exe`。查看检查输出中的最终路径，确认环境变量没有覆盖预期配置。

项目使用软件配套 Python。搬到其他电脑后修改本机路径，并重新检查环境及实际运行能力。软件与许可由设备管理者配置。

## 检查解释器与最小仿真

在包含 lab.ps1 的项目目录执行：

```powershell
.\lab.ps1 doctor
.\lab.ps1 smoke
```

| 命令 | 查看什么 | 通过依据 |
|---|---|---|
| doctor | 解释器路径、软件与依赖版本、模块导入 | 输出使用预期安装且检查通过 |
| smoke | 编译、加载、运行、实际读数与停止 | 最小回环读到输入对应值，并完整停止 |

doctor 的模块导入结果与 smoke 的仿真结果分别记录。记下 smoke 输出的实际 run_dir，遇到问题按 [故障排查](troubleshooting.md) 查看首次错误。

如果本机执行策略阻止脚本，可在单次进程运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\lab.ps1 doctor
```

这不会修改系统执行策略。

## 理解运行模式

Virtual HIL 在电脑上模拟 HIL 设备，以非实时方式推进仿真时间，没有外部 I/O。电脑执行一秒与模型推进一秒可能不同；实验事件和采集窗口按仿真时间定义，墙钟时间用于等待超时。

模型检查中的 HIL101、Pro 1 是编译目标和配置。实际使用模式以加载记录中的 Virtual HIL 为准。实体控制器闭环接入需要设备和接口条件明确后，另建对应的实验与验证记录。

同一自动实验期间使用一个执行入口。手动操作 HIL SCADA 时，先完成并停止手动实验、释放占用，再执行自动流程。

## 选择实验与资料

环境检查后，按 [首次实验](first-experiment.md) 运行 RLC，或按 [Boost 教程](boost-experiments.md) 运行闭环动态实验。已完成的软件验证和待验事项见 [验证状态](validation.md)。

API 名称和行为以所用安装的本地资料为准：

- [Control Center 入门与 Virtual HIL](<../../Typhoon HIL Control Center 2026.3/typhoon/help/t-ug002/concepts/realtime_quick_start_guide.html>)
- [Schematic API](<../../Typhoon HIL Control Center 2026.3/Documentation/html/schematic_api.html>)
- [HIL API](<../../Typhoon HIL Control Center 2026.3/Documentation/html/hil_api.html>)
- [TyphoonTest Library](<../../Typhoon HIL Control Center 2026.3/Documentation/typhoontest_html/index.html>)

本地链接按工作区安装路径编写；换电脑后也可从 Control Center 帮助入口找到同版本资料。
