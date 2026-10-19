# 感应电机闭环转速跟踪

本案例供有电机基础的组员学习已有模型接入和转速跟踪测试。研究问题是：在相同电源与常值负载下，从零启动的闭环能否在指定窗口跟踪 1430 rpm 或 850 rpm。运行模式为 Virtual HIL。

## 已核对接口

| 对象 | 实际路径与含义 | 设置时机或证据 |
|---|---|---|
| 速度参考 | SCADA Input `Speed RPM`，rpm；连接 rpm_to_w_elec 至控制器误差通路 | 加载后、启动前显式设置；API 回读和 LabSpeedReference 全程波形 |
| 反馈速度 | `Speed`；机械角速度经 `60/(2*np.pi)` 换算为 rpm | 直接采集；原始列 Speed_rpm |
| 转矩 | `Torque`；machine 3 的 el_trq_out 对应测量输出 T，电磁转矩 N·m | 与施加的负载指令分别记录 |
| 电源 | `Vgrid` 为三相电压源；rms=230 对应相电压 RMS | 短采集相电压约 229.9994 V、线电压约 398.3705 V；加载后设置并回读 |
| 使能 | `Enable=1`，启用逆变器控制 | 加载后设置；API 回读和预验探针 |
| 负载模式 | `Load_sel=1` 选择 IM_Load 常值输入；0 时实际负载指令为零 | 两次短采集对照确认，不沿用未经核实的默认选择 |
| 负载大小 | IM_Load=0.5 经 Gain6=4 输出 2 N·m | 此处 4 是模型信号缩放基值，不推定为电机铭牌额定转矩 |
| 控制周期 | 模型初始化中的 Ts=100 µs | 静态读取字面量并通过实际编译验证 |

官方电机及控制器结构属性保留。适配器在编译前向每次运行副本增加参考与负载监测探针；源模型和面板按字节保存。预验编译目标为 HIL101、配置 Pro 1，实际运行始终显式选择 Virtual HIL；实测步长 0.5 µs。

接口与短采集证据：[常值负载预验](../../results/20261019-120728-im-preflight-5b262b/preflight.json)、[原始波形](../../results/20261019-120728-im-preflight-5b262b/waveforms.csv)；[选择 0 对照](../../results/20261019-120536-im-preflight-912b67/preflight.json)。本机结果不一定随仓库附带，缺失时需重新实测。

## 本机模型依赖

官方模型和面板统一作为本机依赖并排除 Git，公开再分发权限尚未确认。安装根目录从 TYPHOON_HOME 或 environment.local.json 定位；来源、安装相对路径及 SHA-256 见 [来源索引](../../models/origin.json) 的 induction_motor_closed_loop 条目。

使用者先执行 `prepare-models`，从匹配安装准备 models/induction_motor_closed_loop.tse 和 models/induction_motor_closed_loop.cus，再执行 validate-case 核对哈希。缺少本机依赖时，静态工具会明确报告，不以已登记或代码支持代替运行验证。

## 执行与解释

```powershell
.\lab.ps1 validate-case --case im_speed_tracking --json
.\lab.ps1 run --config configs/im_speed_1430.json --json
.\lab.ps1 run --config configs/im_speed_850.json --json
.\lab.ps1 verify --run-dir 'results/本次实际目录' --json
.\lab.ps1 report --run-dir 'results/本次实际目录' --json
.\lab.ps1 verify --run-dir 'results/本次实际目录' --json
```

两工况独立运行，以命令返回的目录关联。请求 4 s、20 kHz，实际抽取、样本数及时间戳以 capture.json 为准。[判据与官方测试差异](acceptance.md) 说明 [2,4) s 全窗口 1% 判定及采样有效性检查。

API 回读在 manifest.json；SpeedReference_rpm 与 LoadCommand_Nm 直接记录参考和负载通路。metrics.json 保存全部超限时刻；报告保留完整启动波形。数据不足或控制输入未生效时为 error，完整有效数据越限为 failed。记录一致性由最终 verify 单独判定。
