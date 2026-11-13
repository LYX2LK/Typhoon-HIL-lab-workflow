# 讨论稿流程图：Word 插图

来源：2026-11-13 当前 discussion-brief.md 的三张流程图及相邻正文。

1. 01-overall-workflow：总体流程与任务衔接。
2. 02-test-search-feedback：任务一的测试生成与真实反馈循环。
3. 03-analysis-and-diagnosis：任务二的数据分析、故障识别及工具辅助诊断。

术语与正文一致：反馈包括性能指标、判定结果及响应特征；评分计算指标与限值的差值，恢复时间示例使用正文定义的余量。图中的“闭环”专指电机控制闭环。

PNG 为白底、600 dpi，适合直接插入 Word。建议插入后锁定纵横比，宽度设置为 15—16 cm；第三张建议独占一页。SVG 为可缩放矢量源图，使用 Microsoft YaHei 字体，需在有相应字体的系统中查看或插入。

文字按语义显式分行，并按实际字体测量宽度；框与连线均手动定位。实线表示当前主要数据/处理流程；图一虚线表示后续执行复验，图三虚线表示可选分类器辅助输入。图二将相邻正文的工程知识与反馈特征展开为输入说明。其余措辞为适应图示做了等义简化。

build_figures.py 可重新生成所有图片，manifest.json 记录来源文件摘要及图片尺寸。来源按脚本所在目录相对定位，输出保存在本 figures 目录，不生成压缩包。

在项目根目录运行：

```powershell
& 'D:\Typhoon\Typhoon HIL Control Center 2026.3\python3_portable\python.exe' -B -X utf8 'docs/research/2026-11-11-hil-ai-selection/figures/build_figures.py'
```

图片采用手动排版，脚本不会自动读取并转换 Mermaid。后续正文或流程变化时，需同步更新图中文字与布局，再重新生成图片。
