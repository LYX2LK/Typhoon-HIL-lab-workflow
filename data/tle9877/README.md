# 本次寄送板卡资料

本目录保存所交付 LIN.ldf 的字节副本。原始来源位于工作区 docs；SHA-256 与其他资料索引在 configs/tle9877_sample.json 的 sources 中维护。

接口和参数事实集中在该配置中：18 条引线按 Excel 原单元格转录，物理参数带单位、来源与确认状态。未知接口规格保持 null 或 false。后续确认值应注明答复或实测依据。

LIN 工具使用 THCC 配套 Python 已包含的 ldfparser 读取此文件，只实现本次三个业务帧所需的离线操作。原文件的诊断定义保留，但本轮没有实现诊断服务或设备通信。

PMSM 预演使用 configs/pmsm_software_preview.json 的独立假设，不将其回填为样机已确认参数。
