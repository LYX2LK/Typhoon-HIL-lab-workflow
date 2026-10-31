"""Local, self-contained waveform demonstration report; no remote assets."""
import base64
from html import escape
import json
from pathlib import Path
from .waveform_diagnosis import CLASS_LABELS


def event_text(rec):
    if not rec["events"]:
        return "未检出满足幅度和持续时间阈值的事件"
    return "；".join(f"{e['first_sample_s'] * 1e6:.6f} 至 {e['last_sample_s'] * 1e6:.6f} μs，"
                    f"采样支撑时长 {e['sample_support_duration_s'] * 1e6:.3f} μs"
                    for e in rec["events"])


def metric_text(rec):
    e = rec["evidence"]
    if not e:
        return rec["reason"]
    unit = e["value_unit"]
    text = f"最大{'下降' if rec['family'] == 'dip' else '回落'} {e['max_deviation']:.6f} {unit}"
    text += f"（参考幅值的 {e['max_deviation_fraction'] * 100:.3f}%）；幅度阈值 {e['deviation_threshold']:.6f} {unit}"
    if rec["family"] == "rise":
        text += f"；首次 10%–90% 穿越间隔 {e['first_crossing_interval_s'] * 1e6:.3f} μs"
    return text


def write_diagnosis_report(out, diagnosis, rules, response=None):
    out = Path(out)
    explanations = {r["id"]: r for r in response["records"]} if response else {}
    records = diagnosis["records"]
    expected = rules["label_context"].get("expected_labels", {})
    scope = ("结果用于计划第15条的正常/异常波形识别演示。分类来自预设数值规则；大模型负责解释证据。"
             "正常表示指定方法及窗口内未检出规则事件。逐文件参考标签为形态推断，四组样本已参与方法制定；"
             "目前未评价独立识别准确率或控制器性能，具体故障原因未确定。")
    md = ["# 四组波形识别演示", "", scope, "",
          f"数据集：{diagnosis['dataset_id']}。识别状态：{diagnosis['status']}。", "",
          "| 波形 | 规则判断 | 数值依据 | 异常位置 |", "|---|---|---|---|"]
    rows, cards = [], []
    for r in records:
        rid, label = r["id"], CLASS_LABELS[r["classification"]]
        metrics, event = metric_text(r), event_text(r)
        md.append(f"| {rid} | {label} | {metrics} | {event} |")
        rows.append(f"<tr><td><a href='#{escape(rid)}'>{escape(rid)}</a></td><td class='{r['classification']}'>{label}</td>"
                    f"<td>{escape(metrics)}</td><td>{escape(event)}</td></tr>")
        explanation = explanations.get(rid)
        paragraph = escape(explanation["summary"]) if explanation else "大模型解释待生成；当前显示确定性计算结果。"
        references = ", ".join(explanation["evidence_keys"]) if explanation else ""
        chart = out / "source" / f"{rid}.png"
        img = (f"<img loading='lazy' alt='{escape(rid)} 原始采样全程和局部图，单位与各自坐标见图内标注' "
               f"src='data:image/png;base64,{base64.b64encode(chart.read_bytes()).decode('ascii')}'>") if chart.is_file() else ""
        ref = CLASS_LABELS[expected[rid]] if rid in expected else "无"
        md.extend(["", f"## {rid} {label}", "", metrics, "", event, "", paragraph,
                   "", f"解释引用字段：{references or '待生成'}。参考标签：{ref}，状态 {diagnosis['reference_status']}。",
                   "", f"![{rid}](source/{rid}.png)"])
        evidence = json.dumps(r, ensure_ascii=False, indent=2)
        cards.append(f"<section id='{escape(rid)}'><div class='cardhead'><h2>{escape(rid)}</h2>"
                     f"<span class='{r['classification']}'>{label}</span></div><p>{escape(metrics)}</p>"
                     f"<p><b>事件位置：</b>{escape(event)}</p><div class='explanation'><b>大模型解释</b><p>{paragraph}</p>"
                     f"<small>引用字段：{escape(references or '待生成')}</small></div>{img}"
                     f"<details><summary>查看数值证据</summary><pre>{escape(evidence)}</pre></details></section>")
    thresholds = (f"电平跌落超过起始基准的 {rules['dip_fraction'] * 100:g}%；"
                  f"上升过程相对历史峰值的回落超过起止参考差的 {rules['rise_drawdown_fraction'] * 100:g}%；"
                  f"连续越限至少 {rules['minimum_duration_s'] * 1e6:g} μs。严格大于幅度阈值，持续时间含等号。"
                  "事件时间以各 CSV 自身坐标表示，采样支撑时长为点数乘采样间隔。上升回落仅检查首次 10%–90% 穿越窗口。")
    provenance = (f"提供方：{response['provider']}；模型：{response['model']}；传递方式：{response['transport']}；"
                  f"上下文：{response['context']}。") if response else "尚未导入大模型回答。"
    caveat = "模型回答已做请求哈希、分类与引用字段校验，并需人工复阅自然语言；校验不等于验证所有语义。"
    md.extend(["", "## 规则和解释来源", "", thresholds, "", rules["threshold_source"], "", provenance,
               "", caveat, "", "## 来源和复核", "",
               "原始 CSV/PNG、清单、截图参数来源及数据复算记录保存在 source/；该目录是独立副本。",
               "", "识别结果：diagnosis.json；模型输入：llm_request.json；模型回答（完成时）：llm_response.json。",
               "", "使用 verify-diagnosis 做哈希检查并从原始 CSV 复算识别结果。"])
    (out / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    completed = sum(r["classification"] != "inconclusive" for r in records)
    abnormal = sum(r["classification"] == "abnormal" for r in records)
    document = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>四组波形识别演示</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f3f5f8;color:#182635;font:16px/1.7 'Microsoft YaHei',sans-serif}}
main{{max-width:1260px;margin:auto;padding:36px 28px 80px}}h1{{font-size:32px;margin:0 0 12px}}h2{{margin:0;font-size:25px}}
.intro{{max-width:980px;color:#46596c}}.stats{{display:flex;flex-wrap:wrap;gap:14px;margin:26px 0}}
.stats div{{background:white;border:1px solid #dce3ea;border-radius:10px;padding:16px 24px;flex:1;min-width:170px}}
.stats strong{{display:block;font-size:27px;color:#163c65}}table{{border-collapse:collapse;width:100%;background:white;font-size:14px}}
th,td{{padding:14px;text-align:left;border-bottom:1px solid #dce3ea;vertical-align:top}}th{{background:#e7edf4}}
.tablewrap{{overflow-x:auto}}a{{color:#185b98}}section{{background:white;border:1px solid #dce3ea;border-radius:12px;padding:24px;margin-top:24px;scroll-margin-top:16px}}
.cardhead{{display:flex;justify-content:space-between;gap:16px;align-items:center}}.normal{{color:#166444;font-weight:700}}
.abnormal{{color:#a13523;font-weight:700}}.inconclusive{{color:#775313;font-weight:700}}.explanation{{background:#edf3fa;border-left:4px solid #3d6c9c;padding:14px 18px;margin:18px 0}}
.explanation p{{margin:6px 0}}small{{color:#4e6278}}img{{display:block;width:100%;height:auto;margin:12px auto}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f7f9;padding:16px;font-size:13px}}details{{margin-top:16px}}summary{{cursor:pointer}}
footer{{margin-top:28px;color:#526274}}@media(max-width:650px){{main{{padding:22px 14px}}section{{padding:16px}}h1{{font-size:27px}}}}
</style><main><h1>四组波形识别演示</h1><p class="intro">{escape(scope)}</p>
<div class="stats"><div><strong>{completed} / {len(records)}</strong>完成规则判断</div><div><strong>{abnormal}</strong>检出形态异常</div>
<div><strong>{'已生成' if response else '待生成'}</strong>大模型解释</div><div><strong>未确定</strong>具体故障原因</div></div>
<div class="tablewrap"><table><thead><tr><th>波形</th><th>规则判断</th><th>数值依据</th><th>异常位置</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>{''.join(cards)}
<section><h2>规则和来源</h2><p>{escape(thresholds)}</p><p>{escape(rules['threshold_source'])}</p>
<p>{escape(provenance)}</p><p>{escape(caveat)}</p><details><summary>批次说明和参考标签</summary>
<pre>{escape(json.dumps(rules['label_context'], ensure_ascii=False, indent=2))}</pre></details></section>
<footer>本页面包含全部图像，可离线打开。全量采样与单位保留在 source/；四幅图各自取轴范围，不假定跨文件同步。可用 verify-diagnosis 从 CSV 复算识别结果。性能状态：not_evaluated。</footer></main></html>"""
    (out / "report.html").write_text(document, encoding="utf-8")
