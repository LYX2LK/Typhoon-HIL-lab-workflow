"""Separate free Markdown from reference-only report controls. No JSON repair."""
from copy import deepcopy
import re

from .boost_agent_schema import obj, enum, array
from .boost_agent_investigation import context_refs
from .boost_agent_wire import project_answer


NARRATIVE_REQUEST = """现在只输出给工程组员阅读的普通Markdown分析，不输出JSON或工具调用。
先用一句话说明最重要的发现，再用2至4个要点说明关键证据、当前解释和下一步验证的目的；通常250至450字，复杂追问按需展开。每点只讲一件事，用空行分开。可用“波形说明了什么”“可能的原因”“下一步怎么验证”等自然表达，按本轮内容取舍，不必逐个设置标题。
正文是唯一的分析主文，不为结构字段重复写摘要、表述、范围、依据、判据和流程清单；状态码、字段名、选项菜单均不写入正文。范围和不确定性就近用一句话说明。只讨论与当前问题有关的1至2个解释，首轮没有对照时不能说启动残余解释已经被削弱。确认或排除原因时仍须有明确判据和实际判别证据。
首轮围绕已发现的问题提出有信息增量的对照；只有完成相关对照并回答当前问题后，才建议总结或继续定位。用户明确要求收尾时，简短总结当前证据及尚未回答的问题。后续轮次重点写新增证据改变了什么，避免复述前文和首页项目背景。
正文中正常使用引号，无需为传输转义。下一阶段另填简短问题、选项名称和一句话目的，分析依据仍引用正文段落。"""


def index_narrative(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 9000:
        raise ValueError("正文为空或超过9000字符")
    paragraphs = re.split(r"\n\s*\n", text.strip())
    # References are display excerpts; the full original Markdown remains intact.
    chunks = [p[i:i + 900] for p in paragraphs for i in range(0, len(p), 900)]
    return {f"P{i:03d}": value for i, value in enumerate(chunks, 1)}


OPTION_LABEL_PATTERN = r'^[^"\\\r\n]{1,80}$'
GOAL_MESSAGES = {
    "conclude": "请根据已有证据形成有适用范围的阶段结论，分别说明已确认的观察、假说状态和后续需求，结束本轮提问。",
    "deepen": "请将当前目标转为定位具体机理，先利用已有证据，明确需要区分的机制和新增观测或干预的用途，并提出实施方案。",
}


def has_timing_contrast(context):
    """A retry or an identical repeat is not a timing comparison."""
    return len({r["event_at_s"] for r in context["run_history"]["disturbance_runs"]}) >= 2


def concise_schema(request_hash, evidence, remaining, context, text_index):
    # Keep historical schemas unchanged for saved-record verification.
    schema = compact_schema(request_hash, evidence, remaining, context, text_index, 2)
    props = schema["properties"]
    props.pop("question_ref")
    props["question"] = enum([""]) if context["intent"] == "conclude" else {"type": "string", "pattern": r"^[\s\S]{0,60}$"}
    variants = props["options"]["items"]["anyOf"]
    if context["goal"] == "characterize_response" and not has_timing_contrast(context) and context["intent"] != "conclude":
        props["decision"] = enum(["continue", "needs_capability"])
        variants[:] = [v for v in variants if "conclude" not in v["properties"]["tool"]["enum"]]
    for variant in variants:
        fields = variant["properties"]
        fields.pop("description_ref")
        fields["description"] = {"type": "string", "pattern": r"^[\s\S]{1,120}$",
                                 "description": "一句话说明此选项的目的，不复制分析段落。"}
        variant["required"] = list(fields)
    schema["required"] = list(props)
    return schema


def compact_schema(request_hash, evidence, remaining, context, text_index, control_version=1):
    if control_version == 3: return concise_schema(request_hash, evidence, remaining, context, text_index)
    if control_version not in (1, 2): raise ValueError("未知报告控制版本")
    ref = enum(text_index)
    optional = enum(["", *text_index])
    refs = array(enum([f"{rid}.{field}" for rid in evidence for field in
                       ("config", "metrics", "pre_event_trend", "aligned_response")] + context_refs(context)))
    hypothesis = obj({"id": {"type": "string", "pattern": "^[A-Za-z0-9_-]{1,48}$"},
        "status": enum(["supported", "weakened", "unresolved", "established", "refuted"]),
        "claim_ref": ref, "scope_ref": ref, "reason_ref": ref, "evidence": refs,
        "criterion_ref": optional, "test_basis_ref": optional})
    block = obj({"type": enum(["analysis", "metrics", "waveform", "callout"]),
        "title_ref": optional, "text_ref": optional, "evidence": refs,
        "run_ids": array(enum(evidence)), "view": enum(["full", "aligned", "pre_event"]),
        "tone": enum(["info", "warning"])})
    actions = ["discuss", "conclude"] + ([] if context["goal"] == "identify_mechanism" else ["deepen"])
    if remaining > 0: actions.append("run_experiment")
    option = obj({"id": {"type": "string", "pattern": "^[A-Za-z0-9_-]{1,48}$"},
        "label_ref": ref, "description_ref": ref, "recommended": {"type": "boolean"},
        "tool": enum(actions), "experiment_key": enum(context["action_catalog"]),
        "event_at_s": {"type": "number", "minimum": 0, "maximum": 2.5}, "message_ref": optional})
    if control_version == 2:
        common = {k: deepcopy(v) for k, v in option["properties"].items()
                  if k not in {"label_ref", "tool", "experiment_key", "event_at_s", "message_ref"}}
        common["label"] = {"type": "string", "pattern": OPTION_LABEL_PATTERN,
                           "description": "独立生成1至80字的简短单行标题，各选项含义清楚；不用英文双引号或反斜杠。"}
        zero = {"type": "number", "enum": [0]}
        variants = [obj({**common, "tool": enum(["discuss"]), "experiment_key": enum(["none"]),
                         "event_at_s": zero, "message_ref": ref}),
                    obj({**common, "tool": enum([t for t in ("conclude", "deepen") if t in actions]),
                         "experiment_key": enum(["none"]), "event_at_s": zero, "message_ref": enum([""])})]
        if remaining > 0:
            variants.append(obj({**common, "tool": enum(["run_experiment"]),
                "experiment_key": enum(k for k in context["action_catalog"] if k != "none"),
                "event_at_s": {"type": "number", "minimum": 0, "maximum": 2.5}, "message_ref": enum([""])}))
        option = {"anyOf": variants}
    closing = context["intent"] == "conclude"
    return obj({"request_sha256": enum([request_hash]),
        "decision": enum(["complete"] if closing else ["continue", "ready_to_conclude", "needs_capability", "complete"]),
        "summary_ref": ref, "next_requirement_ref": optional,
        "observations": array(enum(f["id"] for f in context["verified_observations"])),
        "hypotheses": array(hypothesis),
        "blocks": array(block, "恰好一个analysis显示完整正文；模型决定它与指标、波形、提示的次序。"),
        "question_ref": enum([""]) if closing else optional,
        "options": {"type": "array", "items": option, "enum": [[]]} if closing else array(option)})


def project_compact(wire, context, text_index, narrative, control_version=1):
    if control_version == 3:
        # Validate the new business fields without tightening optional visual hints.
        if not isinstance(wire, dict): raise ValueError("报告控制字段不符合契约")
        question = wire.get("question")
        if not isinstance(question, str) or len(question) > 60: raise ValueError("问题需为60字以内短句")
        early = context["goal"] == "characterize_response" and not has_timing_contrast(context) and context["intent"] != "conclude"
        if early and wire.get("decision") in {"ready_to_conclude", "complete"}: raise ValueError("尚无实际时刻对照，应先继续验证")
        for option in wire.get("options", []):
            description = option.get("description")
            if not isinstance(description, str) or not description.strip() or len(description) > 120:
                raise ValueError("选项说明需为120字以内的一句话")
            if early and option.get("tool") in {"conclude", "deepen"}: raise ValueError("尚无实际时刻对照，应先继续验证")
        legacy = deepcopy(wire); index = dict(text_index)
        def add(value):
            key = "UI" + str(len(index)); index[key] = value; return key
        legacy.pop("question");legacy["question_ref"] = add(question) if question else ""
        for option in legacy["options"]: option["description_ref"] = add(option.pop("description"))
        answer = project_compact(legacy, context, index, narrative, 2)
        answer["presentation"] = "concise_v1"
        return answer
    if control_version not in (1, 2): raise ValueError("未知报告控制版本")
    expected = {"request_sha256", "decision", "summary_ref", "next_requirement_ref", "observations",
                "hypotheses", "blocks", "question_ref", "options"}
    if not isinstance(wire, dict) or set(wire) != expected:
        raise ValueError("报告控制字段不符合契约")

    def text(ref, optional=False):
        if optional and ref == "": return ""
        if not isinstance(ref, str) or ref not in text_index:
            raise ValueError("引用了不存在的正文段落编号")
        return text_index[ref]

    def title(ref, fallback=""):
        if not ref: return fallback
        value = re.sub(r"^\s*(?:#{1,6}\s+|[-*]\s+)", "", text(ref).splitlines()[0]).strip()
        return value[:99] + "…" if len(value) > 100 else value

    flat = {"request_sha256": wire["request_sha256"], "goal": context["goal"], "decision": wire["decision"],
        "summary": text(wire["summary_ref"]), "next_requirement": text(wire["next_requirement_ref"], True),
        "observations": deepcopy(wire["observations"]), "hypotheses": [], "blocks": [],
        "question": title(wire["question_ref"]), "options": []}
    for h in wire["hypotheses"]:
        if set(h) != {"id", "status", "claim_ref", "scope_ref", "reason_ref", "evidence", "criterion_ref", "test_basis_ref"}:
            raise ValueError("假说控制字段不符合契约")
        flat["hypotheses"].append({"id": h["id"], "status": h["status"], "evidence": h["evidence"],
            **{k: text(h[k + "_ref"], k in ("criterion", "test_basis")) for k in
               ("claim", "scope", "reason", "criterion", "test_basis")}})
    count = 0
    for b in wire["blocks"]:
        if set(b) - {"type", "title_ref", "text_ref", "evidence", "run_ids", "view", "tone"}:
            raise ValueError("页面控制字段不符合契约")
        kind = b["type"]
        if kind not in {"analysis", "metrics", "waveform", "callout"}: raise ValueError("未知页面区块")
        if kind == "analysis": count += 1
        flat["blocks"].append({"type": "markdown" if kind == "analysis" else kind,
            "title": title(b["title_ref"], {"analysis": "分析与验证建议", "metrics": "指标", "waveform": "波形", "callout": "说明"}[kind]),
            "text": narrative if kind == "analysis" else text(b["text_ref"], True),
            "evidence": b["evidence"], "run_ids": b["run_ids"], "view": b["view"], "tone": b.get("tone", "info")})
    if count != 1: raise ValueError("页面需恰好一次展示完整分析正文")
    for o in wire["options"]:
        label_key = "label" if control_version == 2 else "label_ref"
        if set(o) != {"id", label_key, "description_ref", "recommended", "tool", "experiment_key", "event_at_s", "message_ref"}:
            raise ValueError("候选控制字段不符合契约")
        label = o["label"] if control_version == 2 else title(o["label_ref"])
        message = text(o["message_ref"], True)
        if control_version == 2:
            if not isinstance(label, str) or not re.fullmatch(OPTION_LABEL_PATTERN, label) or not label.strip():
                raise ValueError("选项标题需为1至80字单行短标题，不含英文双引号或反斜杠")
            if o["tool"] in GOAL_MESSAGES:
                if o["message_ref"]: raise ValueError("目标选择不接受追问段落，使用已声明的目标操作")
                message = GOAL_MESSAGES[o["tool"]]
            elif o["tool"] == "discuss" and not message.strip():
                raise ValueError("讨论选项需引用非空追问段落")
        flat["options"].append({k: o[k] for k in ("id", "recommended", "tool", "experiment_key", "event_at_s")} |
            {"label": label, "description": text(o["description_ref"]), "message": message})
    return project_answer(flat, context)
