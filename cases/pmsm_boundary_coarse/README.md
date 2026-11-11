# PMSM 幅值扩展与事件间隔加密

在首轮事件交互实验基础上，扩大目标转速和负载，比较恢复时间及累计误差，并保留单事件对照。设计、固定判据与后续选点规则见[运行前方案](acceptance.md)。

本案例执行13次粗扫描：2400/2700/3000 rpm × 0.03/0.06/0.10 N·m的同时事件，以及新增幅值的四个单事件对照。

```powershell
.\lab.ps1 validate-case --case pmsm_boundary_coarse --json
.\lab.ps1 run-case --case pmsm_boundary_coarse --json
```

后续固定配置在`pmsm_boundary_dense`（8次时序加密）与`pmsm_boundary_confirm`（2次复跑）中，均通过相同的`run-case`入口运行。加密幅值由粗扫描结果按预先固定规则选出，选择文件保存在对应任务记录，实际结论见[验证索引](../../docs/validation-history.md)。

本轮连续批次中发生两次Virtual HIL进程崩溃。剩余加密与复跑工况改用逐配置的独立`lab.ps1 run --config <配置> --json`，每次随后执行`lab.ps1 verify --run-dir <实际目录> --json`。错误原记录保持，独立运行由任务目录的`*-runs.json`关联；这一恢复方式不代表已确定或修复崩溃根因。

离线汇总用安装配套Python调用：

```text
scripts/analyze_pmsm_boundary.py report --batch <粗扫描批次> --batch <加密批次> --batch <复跑批次> --task <本次任务目录>
```

分析只读原记录、复算指标并输出`analysis/`报告、CSV、图表和哈希。报告另引用首轮的四条对照记录，来源目录与哈希随分析保存。复制项目时须一并提供这些来源。

`--batch`可以重复指定原批次目录、续跑目录及已完成的独立运行清单JSON。只有缺少完整采样的已记录错误允许进入执行尝试清单；所有用于性能比较的子记录必须单独复核一致，其他文件或数值不一致会停止汇总。

执行器、PMSM模型实现和首轮判据均保持。恢复时间为末实际事件后持续回到±50 rpm带的时间，阈值100 ms；原始event_group判据状态单独保留。每配置一次主运行，复跑只作确定性检查。离散点全部通过不意味着已证明连续参数空间通过。
