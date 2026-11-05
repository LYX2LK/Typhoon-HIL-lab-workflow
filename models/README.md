# 模型来源与本机准备

本页供准备环境和接入模型的组员使用。当前官方安装示例的模型和面板统一作为本机依赖；Git 保存来源、版本、SHA-256、代码和配置。公开再分发权限状态记录在 [origin.json](origin.json) 的 `redistribution`，当前为 `unconfirmed`。

在项目根目录配置 THCC 安装后执行：

```powershell
.\lab.ps1 prepare-models
.\lab.ps1 list-cases --json
```

`prepare-models` 读取来源清单中的官方示例条目，包括最小回环 Loopback，按安装相对路径找到源文件。安装版本必须匹配登记版本。已有且哈希匹配的文件直接跳过；缺失文件从安装按字节复制并验证；本机文件、安装源哈希或版本不符时报告问题，预检失败不复制任何文件。命令不会更新登记哈希；实际编译和运行由后续 `smoke` 与实验命令验证。已有匹配文件跳过时无需再次读取安装源文件。

| 位置 | 用途 |
|---|---|
| `origin.json` | 当前模型、面板及相关资料的来源索引 |
| 根目录的 `<model_id>.tse` / `<model_id>.cus` | 当前执行器使用的官方示例本机副本，由准备命令生成并被 Git 忽略 |
| `vendor/` | 为后续第三方模型分目录管理预留，当前保持为空 |
| `custom/` | 为后续自主模型分目录管理预留，当前保持为空 |

Git 不保存空目录，准备命令会自动补建这两个预留目录。现有模型仍使用根目录约定；首次启用子目录中的模型时，需同步调整执行器、案例校验与来源引用，再验证新路径。

新增模型先核对来源和再分发权限。自主创建且有权公开的模型可纳入 Git；第三方模型按其明确许可管理并保留出处。当前根目录忽略规则只覆盖本层 `.tse` 和 `.cus`，不覆盖预留子目录。其他官方原始材料（如 SVG）按各自来源和许可单独核对。

根目录已有 `three_phase_rectifier_fault.tse` 的项目自建例外，现另预留 `tle9877_hil_plant.tse` 和同名 `.cus` 的明确例外。TLE9877 实体模型尚未创建；落地时将实际源文件、必要面板和 SHA-256/来源说明一起提交到 origin.json。命名例外本身不登记可执行能力，也不改变官方示例的来源和权限状态。提交前可用 `git check-ignore -v --no-index models/tle9877_hil_plant.tse` 核对；无忽略匹配时通常返回 1，有 `!` 例外时看规则内容。

来源清单中的模型及面板使用 `installation_relative_path`、`sha256` 和所属模型的 `thcc_version`。官方条目使用 `kind=official_teaching_example_local_dependency`，由准备命令处理；有权提交的自主模型应使用独立来源类别。Generic PV plant 条目还登记官方 HzWatt 测试脚本的路径与哈希；光伏自动实验只需要模型，未依赖 SCADA 面板。运行中的 HzWatt/额定功率改动保存在结果模型副本中。

安装根目录由统一入口定位，详见 [环境配置](../docs/environment.md)。

`pmsm_software_preview` 从安装的 PMSM closed loop SVPWM control 示例按字节准备；9V 等效星形假设、初始化与事件改动仅保存在每次运行副本。参数来源与使用范围见[样机软件准备](../docs/tle9877-software-preparation.md)，不与样机已确认参数混用。

`tle9877_gui_practice.tse` 和 `tle9877_gui_practice.cus` 是同版本安装源派生的本机教学文件。模型沿用 9 V 预演参数，运行给定由 HIL SCADA 面板施加。文件准备和手操步骤见[样机图形界面预演](../docs/tle9877-gui-practice.md)。
