# Typhoon 教学项目指令

## 任务与读者
为有专业基础但不熟悉 Typhoon/Python 的组员执行可复现教学实验。先理解实验问题、参数与单位，再执行并解释实际结果。

## 入口和范围
- 在本目录工作；使用 .\lab.ps1 doctor / smoke / inspect / run / sweep / report / verify。
- 初次运行读 README.md 和 docs/environment.md；实验定义看 docs/experiments.md，操作问题看 docs/troubleshooting.md。
- 使用安装包自带 Python，由 lab.ps1 定位；本地 API 文档位于软件目录 Documentation/ 和 typhoon/help/。API 名称与行为以安装版本为准。
- 当前执行入口支持 rlc_filter + virtual_hil。将任务写成 configs/ 中的新 JSON 配置，沿用已验证执行入口。
- 输入未说明且存在多个合理选择时，先澄清所缺的参数或比较条件；可从明确标注的基准配置开始。
- 结构参数修改由 Schematic API 写入每次运行的模型副本，再编译。运行参数和采集由 HIL API 设置，源与结构参数均回读确认。
- API 组件名是顶层 Rin/R/L/C；get_item 不接收点分隔的层次路径。信号 I/Va1 与源 Vs1 在加载后发现确认。
- 仿真稳态用 get_sim_time() 判断；墙钟 sleep 仅降低轮询频率。所有采集有独立墙钟超时和异常停止。
- 运行互斥锁限制一个执行器；已有仿真运行时应报告并保留现场。

## 证据
- 保留配置、模型、代码快照、原始CSV、采集时间元数据、日志、指标、图与报告。
- passed/failed/error/skipped 如实区分；doctor 模块导入通过不能代替 smoke 或实验通过。
- 结果图和结论来自实际原始数据；报告的解析参考值与模拟测量值分别列出。
- Virtual HIL 的 UTC 触发时间可能是 null，保留原值；记录运行时间带 +08:00 时区。
- 每次运行给出实际目录、判定依据和 verify 结果。无法验证的项目明确列为待验证。
- verify 核验已有记录的文件哈希并复算指标；report 用已有数据重建报告。

## 文件与设备
- 安装目录作为依赖和参考来源。实验改动发生在本项目内的模型副本与新结果目录。
- 许可文件不写入报告、不复制进教学项目。
- 当前工作流只使用 Virtual HIL。涉及真实设备、固件、控制器烧写的任务先确定设备、操作范围与实验负责人。
- 不结束用户正在使用的 Office/WPS 或 Typhoon GUI 进程。

## 编码与验证
- PowerShell 文本 cmdlet 显式 -Encoding UTF8；Python/Node 使用自身的编码参数。
- 模型副本按字节复制，使用 Schematic API 修改。
- 配置/分析/记录逻辑改动后运行 tests；运行链或模型改动后做相应实际 Virtual HIL 检查。
- Python 测试可用软件自带解释器和 unittest discover；不需要联网安装依赖。
- 教学文档写明目的、读者、操作结果和排错依据。
