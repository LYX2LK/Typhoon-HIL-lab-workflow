"""Build the bounded search catalog; no external calls or model inference."""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'evidence'
data = json.loads((EVIDENCE / 'paper-search-results.json').read_text(encoding='utf-8'))
drop = {4: '摘要研究控制器优化，非测试生成、数据诊断或实验选择。',
        9: '摘要研究网络威胁情报去重，非物理系统测试诊断。',
        11: '摘要研究股票市场预测，未涉及本任务的方法选择。',
        16: '摘要中的 falsification 指偏好伪装，非规格证伪。'}
reviews = []
kept = []
for index, paper in enumerate(data['ranked'], 1):
    abstract = paper.get('abstract') or ''
    if index in drop:
        assert abstract.strip(), 'Never exclude a paper without an abstract'
    else:
        kept.append((index, paper))
    reviews.append({'rank': index, 'title': paper['title'],
                    'abstract_available': bool(abstract.strip()),
                    'decision': 'irrelevant' if index in drop else 'relevant',
                    'reason': drop.get(index, '主题相关或需补核；缺摘要者按保留原则列入待核验，未用作结论依据。')})
(EVIDENCE / 'semantic-review.json').write_text(json.dumps(reviews, ensure_ascii=False, indent=2), encoding='utf-8')

out = ['# 大模型核心方法调研：完整检索总表', '',
       '检索截止：2026-11-09。该文件按 paper-search 技能保留所有未排除的 API 检索记录；针对原始论文的深入判断见 [调研报告](research-report.md)。检索记录不等于已核实的研究证据。', '',
       'per-source hits: semantic_scholar=0, open_alex=0, arxiv=0, openreview=0, crossref=18, dblp=0 · 17 unique (1 duplicate merged) · 4 filtered as irrelevant · 13 retained', '',
       '除 Crossref 外，多个接口出现错误；0 不能理解为未发现相关研究。缺日期/摘要者依照技能保留为待核验，未据此认定其属于截止日期前的有效证据。词法分数不是论文质量评分。引文数为本次 Crossref 快照，来源覆盖有限。', '',
       '| 原排名 | Title | Date | Venue / 状态 | Citations | Score | Sources |',
       '|---|---|---|---|---:|---:|---|']
for i, p in kept:
    title = ('[survey] ' if p.get('is_survey') else '') + p['title']
    venue = p.get('venue') or '元数据待核验'
    out.append(f"| [{i}]({p['url']}) | {title} | {p.get('publication_date') or '未返回'} | {venue} | {p.get('citation_count', 0)} | {p.get('relevance_score')} | Crossref |")
out += ['', '未过滤记录完整保存在 [paper-search-results.json](evidence/paper-search-results.json)；筛选依据见 [semantic-review.json](evidence/semantic-review.json)。', '',
        '## Model Knowledge', '', '0 篇。未把仅凭模型记忆、未经当前来源核验的论文加入证据。补充论文均由实时原始来源检索取得，列于下方。', '',
        '## Overview', '',
        'API 查询：`large language model cyber physical falsification`、`large language model time series anomaly diagnosis`、`large language model active fault diagnosis`；时间窗口为 2023 至 2026-11-09。API 去重后 17 条、保留 13 条，随后通过精确题名、原论文参考文献及作者/会议渠道补充 19 项重点阅读来源（18 项原始研究、1 项综述）。两组有交集，不相加宣称论文总量。', '',
        '## Trends', '',
        '补充阅读显示方法已从单纯序列预测/分类扩展到语义反馈证伪、工具辅助诊断与动作/观测选择，并出现自动生成检测规则的路线。2024—2026 年材料覆盖 IJCAI、ICLR、KDD、NeurIPS、ISSTA 及工业领域会议/期刊；最新主动诊断证据中仍有较多预印本。该有目的的小样本不足以估计全领域的发表增长速度。', '',
        '## Key themes', '',
        '| 主题 | 方法与代表 |', '|---|---|',
        '| 语义驱动测试 | S1 AutoHIL、S2 LLM-Falsifier、S3 GLLMPro：从需求产生测试，或直接选择下一输入 |',
        '| 直接时序/视觉识别 | S4 LLMAD、S5 LLM-TSAD、S13 VLM4TS：输入表示与异常定位 |',
        '| 知识与信号联合诊断 | S10 S2S-FDD、S11 BatteryAgent、S7 ATTLLM：融合机理和观测；S12 为融合反证 |',
        '| 主动信息获取 | S17 CoffeeBench、S18 LeGIT、S19 ACTMED：选择动作、干预或检查；S8 TraceBench 是静态归属参照 |',
        '| 方法生成与表示迁移 | S14 Argos、S15 AnomalyLLM、S16 FD-LLM：分别生成规则、蒸馏和微调 |', '',
        '## Keywords frequency', '',
        '仅在 13 条保留 API 记录的标题中计数；忽略通用检索词 LLM，大小写与连字符归一，每篇每个词组最多计 1 次。同频按预设词表顺序，不能据此比较研究热度。', '',
        '| Keyword | Count |', '|---|---:|']
terms = {'fault diagnosis': r'fault (?:detection and )?diagnosis',
         'time series': r'time[ -]series', 'anomaly detection': r'anomaly detection',
         'cyber physical': r'cyber[ -]physical', 'distillation': r'distillation',
         'forecasting': r'forecasting', 'multimodal': r'multimodal'}
freq = [(k, sum(bool(re.search(v, p['title'], re.I)) for _, p in kept)) for k, v in terms.items()]
for term, count in sorted(freq, key=lambda x: -x[1])[:5]:
    out.append(f'| {term} | {count} |')
out += ['', '## Most cited by accepted paper', '',
        '只列 API 返回明确期刊/会议出版元数据者；不足 5 项时不补造。元数据完整不代表全文已审查，其中负荷预测与飞行仿真条目仍需核验任务相关性。补充精读文献未统一取得引文数，不参加此排序。', '',
        '| Rank | Title | Year | Citations |', '|---|---|---:|---:|']
accepted = [(i, p) for i, p in kept if i in {1, 3, 6, 7}]
for j, (i, p) in enumerate(sorted(accepted, key=lambda x: -x[1]['citation_count']), 1):
    out.append(f"| {j} | [{p['title']}]({p['url']}) | {p['year']} | {p['citation_count']} |")
out += ['', '## Most cited by first author', '',
        '限 13 条保留 API 记录；缺作者者不推断。包括预印本，引文口径继承 Crossref，不能用于判定作者权威性。', '',
        '| Rank | Author | Papers in set | Total citations |', '|---|---|---:|---:|']
authors = defaultdict(lambda: [0, 0])
for _, p in kept:
    if p.get('authors'):
        a = p['authors'][0]
        authors[a][0] += 1
        authors[a][1] += p.get('citation_count') or 0
for j, (name, (n, cites)) in enumerate(sorted(authors.items(), key=lambda x: -x[1][1])[:5], 1):
    out.append(f'| {j} | {name} | {n} | {cites} |')
out += ['', '## Recommendations for reading', '',
        '1. **S6 AnomLLM（ICLR 2025）**：先理解直接读时序时的动态与定位困难，建立评价标准。',
        '2. **S14 Argos（2025 公开版本）**：理解大模型生成分析方法这一独立路线。',
        '3. **S2 LLM-Falsifier（2026）**：进入与任务一最贴近的语义反馈搜索；与 S3 对读。',
        '4. **S10 S2S-FDD（2026）**：研究信号信息如何转为故障诊断输入，同时核对小样本/已知区间条件。',
        '5. **S17 CoffeeBench（2026）**：研究动作—观测闭环，识别真值反馈与实际工程之间的差异。', '',
        '## 精确检索与正文核验补充表', '',
        '该表不按引文数排名。正式状态与已读版本分别标明；作者报告尚未在本项目复现。', '',
        '| 编号 | 文献 | 状态/已读版本 | 阅读深度 |', '|---|---|---|---|']
sources = [
('S1','AutoHIL','https://conf.researchr.org/details/issta-2026/issta-2026-research-papers/64/AutoHIL-LLM-Based-ECU-Functional-Test-Generation-through-Domain-Knowledge-Augmentati','ISSTA 2026','官方摘要'),
('S2','Large Language Models as Falsifiers for Cyber-Physical Systems','https://arxiv.org/html/2609.20752v1','2026-09 预印本 v1','相关正文、代码 README'),
('S3','On the Role of Large Language Models in Robustness-Guided Requirement Falsification','https://doi.org/10.1145/3832139','ISSTA/PACMSE 2026','官方摘要、公开工件元数据'),
('S4','Large Language Models Can Deliver Accurate and Interpretable Time Series Anomaly Detection','https://doi.org/10.1145/3711896.3737239','KDD 2025；正文为 2024 arXiv v1','版本区分、相关正文、部分代码'),
('S5','Delving into Large Language Models for Effective Time-Series Anomaly Detection','https://papers.nips.cc/paper_files/paper/2025/file/950a34c7b107111570077078e1b5b8ef-Paper-Conference.pdf','NeurIPS 2025','摘要、作者代码入口；未完整取得 PDF'),
('S6','Can LLMs Understand Time Series Anomalies?','https://proceedings.iclr.cc/paper_files/paper/2025/file/05774fb74e863308c4b460c9f49f6918-Paper-Conference.pdf','ICLR 2025','公开正文相关部分'),
('S7','ATTLLM','https://ieeexplore.ieee.org/abstract/document/11701917/','ASCC 2026','官方摘要'),
('S8','TraceBench','https://arxiv.org/html/2608.27182v1','2026-08 预印本 v1','相关方法、实验与附录'),
('S9','[survey] Industrial Fault Diagnosis: A Survey on Evolution Towards LLMs and Agentic Systems','https://ieeexplore.ieee.org/abstract/document/11718786/','IEEE IoT Journal，2026-10-01 Early Access','官方摘要'),
('S10','S2S-FDD','https://arxiv.org/html/2603.08048v1','已核验 2026-03 arXiv v1；不据此推定会议状态','相关方法、实验'),
('S11','BatteryAgent','https://arxiv.org/html/2512.24686v1','已读 2025-12 arXiv v1','方法、消融与案例'),
('S12','When LLMs Sit Above Diagnostic Tools: Unrealized Complementarity in Industrial Fault Diagnosis','https://arxiv.org/html/2610.05031v1','2026-10 预印本 v1','相关方法、比较结果'),
('S13','Harnessing Vision-Language Models for Time Series Anomaly Detection','https://arxiv.org/html/2506.06836v1','已读 2025-06 arXiv v1','方法、评价及主表'),
('S14','Argos: Agentic Time-Series Anomaly Detection with Autonomous Rule Generation via Large Language Models','https://arxiv.org/html/2501.14170v1','已读 2025-01 arXiv v1','方法、实验设置、官方代码说明'),
('S15','Large Language Model Guided Knowledge Distillation for Time Series Anomaly Detection','https://www.ijcai.org/proceedings/2024/0239.pdf','IJCAI 2024','公开正文方法部分'),
('S16','FD-LLM','https://arxiv.org/html/2412.01218v1','已读 2024-12 arXiv v1','方法、数据划分及训练设置'),
('S17','Can LLM Agents Efficiently Identify Appliance Faults? Insights From Diagnosing a Simulated Appliance','https://arxiv.org/html/2610.19291v1','2026-10 预印本 v1','动作/观测接口、真值反馈、评价'),
('S18','Can Large Language Models Help Experimental Design for Causal Discovery?','https://arxiv.org/html/2503.01139v1','已读 2025-03 arXiv v1','方法；DAG 与硬干预边界'),
('S19','Timely Clinical Diagnosis through Active Test Selection','https://arxiv.org/html/2510.18988v1','已读 2025-10 arXiv v1','BED 方法与迁移边界；跨领域参考'),
]
for sid, title, url, status, depth in sources:
    out.append(f'| {sid} | [{title}]({url}) | {status} | {depth} |')
(EVIDENCE / 'curated-sources.json').write_text(json.dumps([dict(zip(['id','title','url','version_status','reading_depth'], s)) for s in sources], ensure_ascii=False, indent=2), encoding='utf-8')
out += ['', '## 检索失败与执行记录', '',
        '技能文档示例中的 `--json` 与本机 CLI 不兼容，原始错误如下。随后改用同一技能的程序接口完成六源搜索、去重与排名，并将完整结果写入 JSON；未修改技能脚本。', '', '```text',
        (EVIDENCE / 'paper-search.log').read_text(encoding='utf-8').strip(), '```', '',
        '下面保留 API 错误原文；完整进度与重试日志见 [paper-search-api.log](evidence/paper-search-api.log)。这些错误是采用精确题名和原始出版渠道补充检索的原因。', '', '```text']
log = (EVIDENCE / 'paper-search-api.log').read_text(encoding='utf-8')
out += [line for line in log.splitlines() if 'Error on query' in line]
out += ['```', '', '公开全文的额外获取限制：GLLMPro 作者归档/ACM 返回 403；LLM-TSAD 出现 TLS/超时与 OpenReview 浏览器校验，故只采用实际读到的摘要和代码说明。ICLR 论文通过官方网页的 PDF 文本读取，本地 TLS 下载失败不妨碍已读取内容，但本目录未保存该 PDF。', '',
        '运行环境：`D:/LYX/Documents/毕业论文/.venv/Scripts/python.exe`；UTF-8。未运行收费推理、未训练模型、未执行 Typhoon 或实体设备试验。本目录 `allinone.md` 是本次调研的独立输出，不覆盖既有选型文件。', '']
(ROOT / 'allinone.md').write_text('\n'.join(out), encoding='utf-8')
print(f'Wrote {len(kept)} API records, {len(sources)} curated sources and exact errors.')
