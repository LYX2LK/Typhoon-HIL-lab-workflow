# LIN 设备接口与 Mock 预演

本文供接入实际 LIN 主节点设备的维护者使用。已有 LIN 编解码负责字段与校验；新增接口负责组织帧操作、调度、超时和原始日志。当前唯一实现为脚本化 Mock，未连接物理总线。

## 运行与查看

```powershell
.\lab.ps1 lin-mock --json
.\lab.ps1 lin-mock --scenario configs/tle9877_lin_mock.json --output-dir results/lin-mock-my-run --json
```

不指定目录时新建唯一结果目录；指定目录时要求该目录尚不存在。结果包含 session.json、bus.jsonl、原始场景副本、样机配置副本和 LDF 副本。总线报错会保留日志，CLI 返回 1；输入错误返回 2。`record_status`、`experiment_status` 仍为 null，这些文件不是 Virtual HIL 实验记录，也不交给通用 verify 命令。

默认场景使用独立已知向量：2240rpm 对应 `64 00`、PID `A6`、checksum `F4`；先请求一次版本，再执行两个 EWPTEST 周期。两个 10ms 时隙使控制帧和状态帧分别每 20ms 重复。Mock 只推进模拟时钟，不做墙钟等待，不复现设备电气行为或板卡状态机。

## 设备接口的职责

接口定义在 [lin_transport.py](../src/typhoon_lab/lin_transport.py)，编排与日志在 [lin_session.py](../src/typhoon_lab/lin_session.py)。这是项目约定，实际 SDK 的方法名待设备选定后映射。

| 操作 | 责任 |
|---|---|
| open(bitrate) | 使用实际设备配置主节点与速率；连接失败保留错误 |
| wake_up() | 执行已确认的唤醒操作；实际固件的等待和状态机另行落实 |
| publish(ID, data, checksum, timeout_s) | 发送完整主节点发布帧，返回本机 TX 完成及实际字节；这不证明板卡收到 |
| request(ID, length, timeout_s) | 主节点发送帧头并等待从节点响应，返回原始 PID/数据/checksum/接收状态；超时抛出 LINTimeout |
| close() | 释放通信资源；停止板卡另走已确认流程 |

接口接受 6 位 ID，返回帧携带实际 PID。驱动保留帧错误、错误校验与原始时间戳，不自动修复或重试；原生 SDK 调用自身也要遵守超时。需要 SDK 枚举设备、总线电气配置、时间戳换算或停止调度时，在厂家适配器中实现并说明支持范围。

当前编排按 LDF 时隙产生绝对截止时刻，检查超时和跨时隙占用，异常后停止后续帧并尝试释放设备。Python 循环目前仅通过 Mock 验证；真实总线的 break/sync、帧间时序、唤醒等待和周期稳定性应由选定硬件/SDK 实现并实测。不能将本轮 Mock 的准确时间当成主机实时能力。

## 场景与故障复现

[场景配置](../configs/tle9877_lin_mock.json)的 steps 按调用顺序列出 `operation`、`frame` 和 `outcome`。publish 用 expected_data / expected_checksum 核对实际发送请求；request 的 data / pid / checksum 是输入原始响应，故意不自动重算。delay_s 为模拟响应耗时。

复制场景到新文件后，可以这样复现：

| 修改 | 预期行为 |
|---|---|
| 将某个响应的 outcome 改为 timeout | 记录超时、停止后续调度、关闭适配器 |
| 将 checksum 改为 0 | 保存错误原始帧、报告校验不符 |
| 将状态响应 pid 改为 165 | 保存 PID 并报告与所选帧不符 |
| 将 outcome 改为 transport_error | 记录设备异常并释放资源 |

测试还覆盖短帧、发送向量不符、打开失败、关闭失败、驱动超时返回、接收错误和晚唤醒行为。不会为“恢复”自动发送零速或重发命令，因为其实际固件含义尚待确认。

## 日志字段

bus.jsonl 每行保存一个事件。exchange 包含 operation、6 位 id、frame、计划/开始/完成时间、timeout_s、本机 TX 请求、实际 raw 帧和可用时的 decoded 字段。raw 内保留 pid、data、checksum、device_time_s、clock_domain 和 driver_status；校验失败的帧同样保留，超时没有伪造的响应。

logged_at 是带时区主机写日志时间，session_time_s 来自编排时钟；设备时戳的时钟域另列。Mock 的设备和编排时刻都为模拟值，clock_synchronization 保持 not_established。请求、编码速度分别保存，model_speed_rpm 保持 null；真实板卡回报速度和模型速度将来按独立采集来源记录。

session.json 保存输入/日志摘要、相关代码摘要、调用顺序和完成状态。SDK 未选定前不添加假设备驱动，也不开放一个把配置切换成物理发送的选项。
