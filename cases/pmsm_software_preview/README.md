# 低压 PMSM 软件预演

预演启动、转速变化、负载变化和零速命令，验证模型及采集流程。使用模型内部角度、等效星形假设和独立参数配置；样机实物与无感算法待接入。

- 操作与参数依据：[软件准备](../../docs/tle9877-software-preparation.md)。
- 固定工况和判据：[acceptance.md](acceptance.md)。
- 配置：[pmsm_software_preview.json](../../configs/pmsm_software_preview.json)。

```powershell
.\lab.ps1 prepare-models --json
.\lab.ps1 run-case --case pmsm_software_preview --json
```

查看实际返回的 run_dir 内报告、原始波形、事件和最终复核。软件检查结果与样机性能分别解释。
