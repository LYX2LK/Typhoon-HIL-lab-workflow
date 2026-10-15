# 第一版实现约定

目的：让有电机或电力电子基础、但不熟悉 Typhoon/Python 的组员，通过自然语言完成选定教学模型的参数扫描、波形采集、比较和报告。
执行目录：D:\Typhoon\lab-workflow。软件目录：D:\Typhoon\Typhoon HIL Control Center 2026.3。
运行模式仅 Virtual HIL，非实时且不支持外部I/O。物理HIL、控制器烧写和固件更新不属于第一版。
父代理负责 lab.ps1、scripts、src、configs、models、results、tests、README.md、AGENTS.md。
文档worker负责 docs/ 下中文文档，不运行Typhoon，不修改父代理文件。
已实现入口：.\lab.ps1 doctor；.\lab.ps1 smoke；.\lab.ps1 inspect；.\lab.ps1 run --config configs/rlc_baseline.json；.\lab.ps1 sweep --config configs/rlc_sweep.json；.\lab.ps1 report --run-dir results/<实际目录>；.\lab.ps1 verify --run-dir results/<实际目录>。
doctor 只检查解释器/软件版本/模块导入；smoke 才实测compile/load/run/read/stop。
主实验复制官方 basic electrical circuits/rlc circuit/rlc circuit.tse。
真实拓扑：Vs1→Rin→节点；节点到地有两支路：L以及R串C。测量节点电压Va1和源电流I。默认Rin=5Ω，R=.1Ω，L=1e-5H，C=.0005F。
教学配置使用源10Vrms、1000Hz正弦；扫描Rin=1/5/10Ω。此配置的基准与三组扫描已完成；实测状态见docs/validation.md。
结构参数修改→另存模型副本→重新编译→加载Virtual HIL；源波形设定→运行→捕获实际数据→计算稳态RMS→按对应拓扑的稳态相量解析值校核。
每次运行保存config/model/原始CSV/metrics/manifest/log/图表/HTML与Markdown报告。结果状态明确passed/failed/error/skipped。保留本地时间带UTC偏移及代码版本摘要。
文档按真实已验证功能成稿，尚未实测内容标待验证；不得承诺硬件接入和任意模型自动建模。
