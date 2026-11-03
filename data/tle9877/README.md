# 本次寄送板卡资料

本目录保存所交付 [LIN.ldf](LIN.ldf) 的字节副本。来源位置与 SHA-256 在 [tle9877_sample.json](../../configs/tle9877_sample.json) 的 sources 中维护。文档从本索引引用档案，不依赖某位组员电脑的盘符。

## 原始资料及获取

| 来源 ID | 档案名称 | SHA-256 | 获取方式 |
|---|---|---|---|
| ldf | LIN.ldf | `d0effaec3cd0513490de7e380051fa7aa75b0c77711370a5fe9f3a160ae1a95e` | 使用本目录字节副本 |
| wiring | 电机控制板引线连接位置信号及方案说明.xlsx | `9564b2632b5a60fc00716d4fb1622171298e356e494d2f7544696d133256a9ec` | 向课题组本次样机资料接收人员获取 |
| datasheet | Infineon-TLE9877QXA40-DataSheet（试样的样机控制芯片）.pdf | `ab08b216f97a101cf7545ec9aae8f52d9eeca296fef59a1689c427c33a95b6d1` | 同上，按本次归档版本核对 |
| meeting | 联合实验室建设方案研讨会议纪要.md | `d5bbc6b6eb7bf3928e609f7350a1cffb4bab393c3b89578e61ac602c7c49277c` | 同上 |
| parameters | motor-parameters.png（用户提供的电机参数截图） | `3bad8737cf0140de875d3d82d900bab1c21fff13a0a3ba1591c48e18963f3077` | 同上；原工作区归档在 docs/assets/tle9877 |
| control_boundary | control-boundary.png（用户提供的控制边界标注截图） | `8ab3cdd22ab21a0793dd4116b2505cb11715c848fa7b917900cd8b68ddfcf800` | 同上 |

除 LIN 字节副本外，本目录不复制上述原件。获取后按完整摘要核对；workspace_path 仅是配置所记的可选工作区位置。单独克隆仓库可运行离线 LIN 工具，外层原件缺失继续由 `check-tle9877` 标为 missing，保持原有通过条件。

## 配置与接入工作表

接口和参数事实集中在样机配置中：18 条引线按 Excel 原单元格转录，物理参数带单位、来源与确认状态。实际 [I/O 合同](../../configs/tle9877_hil_contract.json)与[电机参数接收表](../../configs/tle9877_motor_pending.json)另存。未知接口规格保持 null 或 false。后续确认值注明答复或实测依据。

LIN 工具使用 THCC 配套 Python 已包含的 ldfparser 读取此文件。三个业务帧已有离线编解码和 [Mock 调度/日志](../../docs/tle9877-lin-adapter.md)；原文件的诊断定义保留。实际设备驱动和诊断服务待设备条件明确后实现。

PMSM 预演使用 configs/pmsm_software_preview.json 的独立假设，不将其回填为样机已确认参数。
