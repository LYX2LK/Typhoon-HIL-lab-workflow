# 大模型核心方法调研：完整检索总表

检索截止：2026-11-09。该文件按 paper-search 技能保留所有未排除的 API 检索记录；针对原始论文的深入判断见 [调研报告](research-report.md)。检索记录不等于已核实的研究证据。

per-source hits: semantic_scholar=0, open_alex=0, arxiv=0, openreview=0, crossref=18, dblp=0 · 17 unique (1 duplicate merged) · 4 filtered as irrelevant · 13 retained

除 Crossref 外，多个接口出现错误；0 不能理解为未发现相关研究。缺日期/摘要者依照技能保留为待核验，未据此认定其属于截止日期前的有效证据。词法分数不是论文质量评分。引文数为本次 Crossref 快照，来源覆盖有限。

| 原排名 | Title | Date | Venue / 状态 | Citations | Score | Sources |
|---|---|---|---|---:|---:|---|
| [1](https://doi.org/10.24963/ijcai.2024/239) | Large Language Model Guided Knowledge Distillation for Time Series Anomaly Detection | 2024-08 | Proceedings of the Thirty-ThirdInternational Joint Conference on Artificial Intelligence | 23 | 6 | Crossref |
| [2](https://doi.org/10.20944/preprints202411.1036.v1) | Multimodal Large Language Model-Based Fault Detection and Diagnosis in Context of Industry 4.0 | 未返回 | 元数据待核验 | 22 | 6 | Crossref |
| [3](https://doi.org/10.1109/access.2025.3613663) | TriP-LLM: A Tri-Branch Patch-Wise Large Language Model Framework for Time-Series Anomaly Detection | 2025 | IEEE Access | 3 | 6 | Crossref |
| [5](https://doi.org/10.2139/ssrn.5886005) | LLM-YOLOMS: Large Language Model-based Semantic Interpretation and Fault Diagnosis for Wind Turbine Components | 未返回 | 元数据待核验 | 3 | 5 | Crossref |
| [6](https://doi.org/10.17775/cseejpes.2025.02460) | Enhancing Information Sensing of Load Forecasting in Cyber-Physical-Social Systems: An Approach with Large Language Model | 2026 | CSEE Journal of Power and Energy Systems | 1 | 5 | Crossref |
| [7](https://doi.org/10.3384/ecp215.1196) | The Large Language Model Pilot: Generative Artificial Intelligence for Cyber-Physical Flight Simulations | 2025-10-28 | Linköping Electronic Conference Proceedings FT2025: Proceedings of the 12th Swedish Aerospace Technology Congress | 1 | 5 | Crossref |
| [8](https://doi.org/10.2139/ssrn.5243041) | Large-Model-Based Smart Agent for Time Series Anomaly Detection in Power Systems | 未返回 | 元数据待核验 | 1 | 5 | Crossref |
| [10](https://doi.org/10.21203/rs.3.rs-9291769/v1) | CP-LLM: Conformal Calibration for Time Series Interval Forecasting with Frozen Large Language Model | 未返回 | 元数据待核验 | 0 | 5 | Crossref |
| [12](https://doi.org/10.46855/energy-proceedings-11484) | Intelligent Fault Diagnosis for Overhead Lines with Covered Conductors: Using Large Language Model | 未返回 | 元数据待核验 | 0 | 5 | Crossref |
| [13](https://doi.org/10.2139/ssrn.5352663) | Large Language Model-Augmented Machine Learning For Intelligent Fault Diagnosis in Process Systems | 未返回 | 元数据待核验 | 0 | 5 | Crossref |
| [14](https://doi.org/10.2139/ssrn.6293248) | A large language model-guided machinery fault diagnosis model based on multi-task prompt tuning and adaptive adversarial distillation | 未返回 | 元数据待核验 | 0 | 5 | Crossref |
| [15](https://doi.org/10.2139/ssrn.7283958) | Large language model-driven automated modelling paradigm for marine diesel engine fault diagnosis | 未返回 | 元数据待核验 | 0 | 5 | Crossref |
| [17](https://doi.org/10.2139/ssrn.6033215) | [survey] A Survey of Large Language Models for Time Series Anomaly Detection: Methods, Challenges, and Future Directions | 未返回 | 元数据待核验 | 0 | 6 | Crossref |

未过滤记录完整保存在 [paper-search-results.json](evidence/paper-search-results.json)；筛选依据见 [semantic-review.json](evidence/semantic-review.json)。

## Model Knowledge

0 篇。未把仅凭模型记忆、未经当前来源核验的论文加入证据。补充论文均由实时原始来源检索取得，列于下方。

## Overview

API 查询：`large language model cyber physical falsification`、`large language model time series anomaly diagnosis`、`large language model active fault diagnosis`；时间窗口为 2023 至 2026-11-09。API 去重后 17 条、保留 13 条，随后通过精确题名、原论文参考文献及作者/会议渠道补充 19 项重点阅读来源（18 项原始研究、1 项综述）。两组有交集，不相加宣称论文总量。

## Trends

补充阅读显示方法已从单纯序列预测/分类扩展到语义反馈证伪、工具辅助诊断与动作/观测选择，并出现自动生成检测规则的路线。2024—2026 年材料覆盖 IJCAI、ICLR、KDD、NeurIPS、ISSTA 及工业领域会议/期刊；最新主动诊断证据中仍有较多预印本。该有目的的小样本不足以估计全领域的发表增长速度。

## Key themes

| 主题 | 方法与代表 |
|---|---|
| 语义驱动测试 | S1 AutoHIL、S2 LLM-Falsifier、S3 GLLMPro：从需求产生测试，或直接选择下一输入 |
| 直接时序/视觉识别 | S4 LLMAD、S5 LLM-TSAD、S13 VLM4TS：输入表示与异常定位 |
| 知识与信号联合诊断 | S10 S2S-FDD、S11 BatteryAgent、S7 ATTLLM：融合机理和观测；S12 为融合反证 |
| 主动信息获取 | S17 CoffeeBench、S18 LeGIT、S19 ACTMED：选择动作、干预或检查；S8 TraceBench 是静态归属参照 |
| 方法生成与表示迁移 | S14 Argos、S15 AnomalyLLM、S16 FD-LLM：分别生成规则、蒸馏和微调 |

## Keywords frequency

仅在 13 条保留 API 记录的标题中计数；忽略通用检索词 LLM，大小写与连字符归一，每篇每个词组最多计 1 次。同频按预设词表顺序，不能据此比较研究热度。

| Keyword | Count |
|---|---:|
| fault diagnosis | 6 |
| time series | 5 |
| anomaly detection | 4 |
| cyber physical | 2 |
| distillation | 2 |

## Most cited by accepted paper

只列 API 返回明确期刊/会议出版元数据者；不足 5 项时不补造。元数据完整不代表全文已审查，其中负荷预测与飞行仿真条目仍需核验任务相关性。补充精读文献未统一取得引文数，不参加此排序。

| Rank | Title | Year | Citations |
|---|---|---:|---:|
| 1 | [Large Language Model Guided Knowledge Distillation for Time Series Anomaly Detection](https://doi.org/10.24963/ijcai.2024/239) | 2024 | 23 |
| 2 | [TriP-LLM: A Tri-Branch Patch-Wise Large Language Model Framework for Time-Series Anomaly Detection](https://doi.org/10.1109/access.2025.3613663) | 2025 | 3 |
| 3 | [Enhancing Information Sensing of Load Forecasting in Cyber-Physical-Social Systems: An Approach with Large Language Model](https://doi.org/10.17775/cseejpes.2025.02460) | 2026 | 1 |
| 4 | [The Large Language Model Pilot: Generative Artificial Intelligence for Cyber-Physical Flight Simulations](https://doi.org/10.3384/ecp215.1196) | 2025 | 1 |

## Most cited by first author

限 13 条保留 API 记录；缺作者者不推断。包括预印本，引文口径继承 Crossref，不能用于判定作者权威性。

| Rank | Author | Papers in set | Total citations |
|---|---|---:|---:|
| 1 | Chen Liu | 1 | 23 |
| 2 | Khalid Alsaif | 1 | 22 |
| 3 | Yuan-Cheng Yu | 1 | 3 |
| 4 | Yaru Li | 1 | 3 |
| 5 | Jorge Lovaco | 1 | 1 |

## Recommendations for reading

1. **S6 AnomLLM（ICLR 2025）**：先理解直接读时序时的动态与定位困难，建立评价标准。
2. **S14 Argos（2025 公开版本）**：理解大模型生成分析方法这一独立路线。
3. **S2 LLM-Falsifier（2026）**：进入与任务一最贴近的语义反馈搜索；与 S3 对读。
4. **S10 S2S-FDD（2026）**：研究信号信息如何转为故障诊断输入，同时核对小样本/已知区间条件。
5. **S17 CoffeeBench（2026）**：研究动作—观测闭环，识别真值反馈与实际工程之间的差异。

## 精确检索与正文核验补充表

该表不按引文数排名。正式状态与已读版本分别标明；作者报告尚未在本项目复现。

| 编号 | 文献 | 状态/已读版本 | 阅读深度 |
|---|---|---|---|
| S1 | [AutoHIL](https://conf.researchr.org/details/issta-2026/issta-2026-research-papers/64/AutoHIL-LLM-Based-ECU-Functional-Test-Generation-through-Domain-Knowledge-Augmentati) | ISSTA 2026 | 官方摘要 |
| S2 | [Large Language Models as Falsifiers for Cyber-Physical Systems](https://arxiv.org/html/2609.20752v1) | 2026-09 预印本 v1 | 相关正文、代码 README |
| S3 | [On the Role of Large Language Models in Robustness-Guided Requirement Falsification](https://doi.org/10.1145/3832139) | ISSTA/PACMSE 2026 | 官方摘要、公开工件元数据 |
| S4 | [Large Language Models Can Deliver Accurate and Interpretable Time Series Anomaly Detection](https://doi.org/10.1145/3711896.3737239) | KDD 2025；正文为 2024 arXiv v1 | 版本区分、相关正文、部分代码 |
| S5 | [Delving into Large Language Models for Effective Time-Series Anomaly Detection](https://papers.nips.cc/paper_files/paper/2025/file/950a34c7b107111570077078e1b5b8ef-Paper-Conference.pdf) | NeurIPS 2025 | 摘要、作者代码入口；未完整取得 PDF |
| S6 | [Can LLMs Understand Time Series Anomalies?](https://proceedings.iclr.cc/paper_files/paper/2025/file/05774fb74e863308c4b460c9f49f6918-Paper-Conference.pdf) | ICLR 2025 | 公开正文相关部分 |
| S7 | [ATTLLM](https://ieeexplore.ieee.org/abstract/document/11701917/) | ASCC 2026 | 官方摘要 |
| S8 | [TraceBench](https://arxiv.org/html/2608.27182v1) | 2026-08 预印本 v1 | 相关方法、实验与附录 |
| S9 | [[survey] Industrial Fault Diagnosis: A Survey on Evolution Towards LLMs and Agentic Systems](https://ieeexplore.ieee.org/abstract/document/11718786/) | IEEE IoT Journal，2026-10-01 Early Access | 官方摘要 |
| S10 | [S2S-FDD](https://arxiv.org/html/2603.08048v1) | 已核验 2026-03 arXiv v1；不据此推定会议状态 | 相关方法、实验 |
| S11 | [BatteryAgent](https://arxiv.org/html/2512.24686v1) | 已读 2025-12 arXiv v1 | 方法、消融与案例 |
| S12 | [When LLMs Sit Above Diagnostic Tools: Unrealized Complementarity in Industrial Fault Diagnosis](https://arxiv.org/html/2610.05031v1) | 2026-10 预印本 v1 | 相关方法、比较结果 |
| S13 | [Harnessing Vision-Language Models for Time Series Anomaly Detection](https://arxiv.org/html/2506.06836v1) | 已读 2025-06 arXiv v1 | 方法、评价及主表 |
| S14 | [Argos: Agentic Time-Series Anomaly Detection with Autonomous Rule Generation via Large Language Models](https://arxiv.org/html/2501.14170v1) | 已读 2025-01 arXiv v1 | 方法、实验设置、官方代码说明 |
| S15 | [Large Language Model Guided Knowledge Distillation for Time Series Anomaly Detection](https://www.ijcai.org/proceedings/2024/0239.pdf) | IJCAI 2024 | 公开正文方法部分 |
| S16 | [FD-LLM](https://arxiv.org/html/2412.01218v1) | 已读 2024-12 arXiv v1 | 方法、数据划分及训练设置 |
| S17 | [Can LLM Agents Efficiently Identify Appliance Faults? Insights From Diagnosing a Simulated Appliance](https://arxiv.org/html/2610.19291v1) | 2026-10 预印本 v1 | 动作/观测接口、真值反馈、评价 |
| S18 | [Can Large Language Models Help Experimental Design for Causal Discovery?](https://arxiv.org/html/2503.01139v1) | 已读 2025-03 arXiv v1 | 方法；DAG 与硬干预边界 |
| S19 | [Timely Clinical Diagnosis through Active Test Selection](https://arxiv.org/html/2510.18988v1) | 已读 2025-10 arXiv v1 | BED 方法与迁移边界；跨领域参考 |

## 检索失败与执行记录

技能文档示例中的 `--json` 与本机 CLI 不兼容，原始错误如下。随后改用同一技能的程序接口完成六源搜索、去重与排名，并将完整结果写入 JSON；未修改技能脚本。

```text
usage: search_papers.py [-h] [--query QUERY] [--queries QUERIES]
                        --start-year START_YEAR --end-year END_YEAR
                        [--max-papers MAX_PAPERS]
                        [--sources {arxiv,dblp,open_alex,openreview,semantic_scholar,crossref} [{arxiv,dblp,open_alex,openreview,semantic_scholar,crossref} ...]]
                        [--no-parallel] [--start-date START_DATE]
                        [--end-date END_DATE] [--raw] [--min-score MIN_SCORE]
search_papers.py: error: unrecognized arguments: --json D:/Typhoon/lab-workflow/docs/research/2026-11-09-llm-core-methods/evidence/paper-search-results.json
```

下面保留 API 错误原文；完整进度与重试日志见 [paper-search-api.log](evidence/paper-search-api.log)。这些错误是采用精确题名和原始出版渠道补充检索的原因。

```text
[arxiv] Error on query 'large language model cyber physical falsification': HTTPSConnectionPool(host='export.arxiv.org', port=443): Read timed out. (read timeout=35.0)
[arxiv] Error on query 'large language model time series anomaly diagnosis': HTTPSConnectionPool(host='export.arxiv.org', port=443): Read timed out. (read timeout=35.0)
[arxiv] Error on query 'large language model active fault diagnosis': 429 Client Error: Too Many Requests for url: https://export.arxiv.org/api/query?search_query=%28all%3Alarge+language+model+active+fault+diagnosis%29+AND+submittedDate%3A%5B202301010000+TO+202612312359%5D&sortBy=relevance&sortOrder=descending&max_results=6
[dblp] Error on query 'large language model cyber physical falsification': Expecting value: line 1 column 1 (char 0)
[dblp] Error on query 'large language model time series anomaly diagnosis': Expecting value: line 1 column 1 (char 0)
[dblp] Error on query 'large language model active fault diagnosis': Expecting value: line 1 column 1 (char 0)
[open_alex] Error on query 'large language model cyber physical falsification': 429 Client Error: Too Many Requests for url: https://api.openalex.org/works?search.semantic=large+language+model+cyber+physical+falsification&filter=publication_year%3A2023-2026&sort=relevance_score%3Adesc&page=1&per-page=6
[open_alex] Error on query 'large language model time series anomaly diagnosis': 429 Client Error: Too Many Requests for url: https://api.openalex.org/works?search.semantic=large+language+model+time+series+anomaly+diagnosis&filter=publication_year%3A2023-2026&sort=relevance_score%3Adesc&page=1&per-page=6
[open_alex] Error on query 'large language model active fault diagnosis': 429 Client Error: Too Many Requests for url: https://api.openalex.org/works?search.semantic=large+language+model+active+fault+diagnosis&filter=publication_year%3A2023-2026&sort=relevance_score%3Adesc&page=1&per-page=6
[openreview] Error on query 'large language model time series anomaly diagnosis': {'name': 'RateLimitError', 'message': 'Too many requests: You have made 5 requests, surpassing the limit of 3 requests. Please try again in 8 seconds (2026-11-09-2610569)', 'status': 429, 'details': {'limit': 3, 'remaining': 0, 'resetTime': '2026-11-09T03:36:16.064Z', 'used': 5, 'current': 5, 'reqId': '2026-11-09-2610569'}}
[openreview] Error on query 'large language model active fault diagnosis': {'name': 'RateLimitError', 'message': 'Too many requests: You have made 7 requests, surpassing the limit of 3 requests. Please try again in 7 seconds (2026-11-09-2610725)', 'status': 429, 'details': {'limit': 3, 'remaining': 0, 'resetTime': '2026-11-09T03:36:16.063Z', 'used': 7, 'current': 7, 'reqId': '2026-11-09-2610725'}}
[semantic_scholar] Error on query 'large language model cyber physical falsification': 429 Client Error:  for url: https://api.semanticscholar.org/graph/v1/paper/search?query=large+language+model+cyber+physical+falsification&offset=0&limit=6&fields=title%2Cauthors%2Cyear%2Cabstract%2CcitationCount%2Curl%2Cvenue%2CpublicationDate%2CexternalIds&year=2023-2026
[semantic_scholar] Error on query 'large language model time series anomaly diagnosis': 429 Client Error:  for url: https://api.semanticscholar.org/graph/v1/paper/search?query=large+language+model+time+series+anomaly+diagnosis&offset=0&limit=6&fields=title%2Cauthors%2Cyear%2Cabstract%2CcitationCount%2Curl%2Cvenue%2CpublicationDate%2CexternalIds&year=2023-2026
[semantic_scholar] Error on query 'large language model active fault diagnosis': 429 Client Error:  for url: https://api.semanticscholar.org/graph/v1/paper/search?query=large+language+model+active+fault+diagnosis&offset=0&limit=6&fields=title%2Cauthors%2Cyear%2Cabstract%2CcitationCount%2Curl%2Cvenue%2CpublicationDate%2CexternalIds&year=2023-2026
```

公开全文的额外获取限制：GLLMPro 作者归档/ACM 返回 403；LLM-TSAD 出现 TLS/超时与 OpenReview 浏览器校验，故只采用实际读到的摘要和代码说明。ICLR 论文通过官方网页的 PDF 文本读取，本地 TLS 下载失败不妨碍已读取内容，但本目录未保存该 PDF。

运行环境：`D:/LYX/Documents/毕业论文/.venv/Scripts/python.exe`；UTF-8。未运行收费推理、未训练模型、未执行 Typhoon 或实体设备试验。本目录 `allinone.md` 是本次调研的独立输出，不覆盖既有选型文件。
