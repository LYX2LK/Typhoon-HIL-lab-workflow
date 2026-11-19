"""Same-permission evidence selection and scoring for the PMSM comparison."""

import itertools

import numpy as np

from .kaist_pmsm import LABELS, OBSERVATIONS


UNDETERMINED = "undetermined"
QUERY_BUDGET = 2
QUERY_IDS = ("Q1", "Q2", "Q3")
RULES = ("fixed", "adaptive")
DISTANCE_LIMITS = (0.75, 1.5, 3.0, 6.0, None)
MARGIN_LIMITS = (0.05, 0.15, 0.3, 0.6, 1.0)
QUERY_DESCRIPTIONS = {
    "Q1": "Phase RMS imbalance and minor-to-major fundamental sequence amplitude ratio.",
    "Q2": "Phase-current spectral amplitude ratios at 3x, 5x and 7x the electrical fundamental.",
    "Q3": "Vibration energy near 1x through 4x mechanical rotation divided by energy at 10–1000 Hz.",
}
SYSTEM = """Diagnose one anonymized PMSM recording. The fault candidates are healthy,
interturn (inter-turn short), and intercoil (inter-coil short). Use undetermined if evidence is absent
or cannot distinguish the candidates. The current and vibration are steady-state summaries computed
on their own time axes. Empirical development medians and interquartile ranges are not physical
limits. Candidate observations come from previously collected signals. Choose an unused offered
query if it can distinguish the current candidates, or finish. Check consistency of the structured
decision and action with your reason before returning. Never treat a requested or failed query as
evidence. If no initial evidence or query is available, finish with undetermined.
Both winding fault types can change current amplitude and phase balance. When initial values fit
multiple classes, use a query to compare the leading hypotheses before committing. Prefer features
that separate their development medians relative to the pooled scale and within-class ranges.
Evaluate each returned measurement in that context. When the final observations remain overlapping
or are far outside the development ranges, retain undetermined.
Return exactly one JSON object with these fields:
decision (healthy, interturn, intercoil or undetermined), action (finish or one offered query ID),
evidence_ids (only observed IDs that support your current decision), reason (brief explanation),
prediction (null for finish, otherwise an object with feature, higher and lower, where feature
belongs to the requested query, and higher and lower are distinct fault candidate labels).
At a query step, decision is provisional and uses only evidence already observed."""


def make_calibration(recordings):
    calibration = {}
    for bundle, names in OBSERVATIONS.items():
        calibration[bundle] = {}
        for feature in names:
            values = [row["observations"][bundle][feature] for row in recordings]
            center = float(np.median(values))
            quartiles = np.quantile(values, [0.25, 0.75])
            scale = max(float(quartiles[1] - quartiles[0]), abs(center) * 1e-6, 1e-9)
            by_class = {}
            for label in LABELS:
                subset = [row["observations"][bundle][feature] for row in recordings if row["label"] == label]
                if not subset:
                    raise ValueError(f"no development recordings for {label}")
                points = np.quantile(subset, [0.25, 0.5, 0.75])
                by_class[label] = {"count": len(subset), "q25": float(points[0]),
                                   "median": float(points[1]), "q75": float(points[2])}
            calibration[bundle][feature] = {"scale": scale, "classes": by_class}
    return calibration


def rank_labels(calibration, evidence):
    if not evidence:
        return []
    ranked = []
    for label in LABELS:
        distances = []
        for bundle, observed in evidence.items():
            features = calibration[bundle]
            values = [
                abs(value - features[key]["classes"][label]["median"]) / features[key]["scale"]
                for key, value in observed.items()
            ]
            distances.append(sum(values) / len(values))
        ranked.append((sum(distances) / len(distances), label))
    return sorted(ranked)


def accepted_label(ranked, stop):
    if not ranked:
        return UNDETERMINED
    best_distance, best_label = ranked[0]
    gap = ranked[1][0] - best_distance
    if stop["max_distance"] is not None and best_distance > stop["max_distance"]:
        return UNDETERMINED
    return best_label if gap > stop["min_margin"] else UNDETERMINED


def separation(feature, labels):
    a, b = (feature["classes"][label]["median"] for label in labels)
    return abs(a - b) / feature["scale"]


def _expected_separation(features, pairs):
    separations = [separation(feature, pair) for pair in pairs for feature in features.values()]
    return sum(separations) / len(separations)


def _prediction(features, labels):
    feature = max(sorted(features), key=lambda name: separation(features[name], labels))
    centers = features[feature]["classes"]
    lower, higher = sorted(labels, key=lambda label: (centers[label]["median"], label))
    return {"feature": feature, "higher": higher, "lower": lower}


def rule_answer(strategy, request, stop):
    calibration = request["calibration"]
    evidence = observed_so_far(request)
    ranked = rank_labels(calibration, evidence)
    decision = accepted_label(ranked, stop)
    available = [key for key in request["available_queries"] if key not in evidence]
    if decision != UNDETERMINED or not available or request["remaining_queries"] == 0:
        return {
            "decision": decision, "action": "finish", "evidence_ids": list(evidence),
            "reason": "Development centroid distance and stop margin.", "prediction": None,
        }

    pair = tuple(label for _, label in ranked[:2]) if ranked else LABELS[:2]
    pairs = (pair,) if strategy == "adaptive" else tuple(itertools.combinations(LABELS, 2))
    query = max(sorted(available), key=lambda key: _expected_separation(calibration[key], pairs))
    return {
        "decision": decision, "action": query, "evidence_ids": list(evidence),
        "reason": f"Development contrast for {', '.join(pair)}.",
        "prediction": _prediction(calibration[query], pair),
    }


def _public_observation(key, measurements):
    return {"id": key, "measurements": measurements}


def request_for(case, calibration, history, remaining):
    bundles = case["observations"]
    return {
        "case_id": case["task_id"],
        "initial": _public_observation("I0", bundles["I0"]) if "I0" in bundles else None,
        "available_queries": {
            key: {"description": QUERY_DESCRIPTIONS[key], "features": OBSERVATIONS[key]}
            for key in QUERY_IDS if key in bundles
        },
        "calibration": calibration,
        "remaining_queries": remaining,
        "history": history,
    }


def observed_so_far(request):
    observed = {}
    if request["initial"] is not None:
        observed["I0"] = request["initial"]["measurements"]
    for event in request["history"]:
        query = event["result"]
        if query["status"] == "ok":
            observed[query["observation"]["id"]] = query["observation"]["measurements"]
    return observed


def classify_answer(answer, request):
    """Return the action status without rewriting the structured answer."""
    if not isinstance(answer, dict) or set(answer) != {"decision", "action", "evidence_ids", "prediction", "reason"}:
        return "invalid_answer"
    if answer["decision"] not in (*LABELS, UNDETERMINED) or not isinstance(answer["reason"], str):
        return "invalid_answer"
    evidence = observed_so_far(request)
    citations = answer["evidence_ids"]
    if (not isinstance(citations, list) or any(not isinstance(key, str) or key not in evidence for key in citations)
            or len(set(citations)) != len(citations)):
        return "invalid_evidence"

    action = answer["action"]
    prediction = answer["prediction"]
    if action == "finish":
        if prediction is not None:
            return "invalid_answer"
        return "finish" if citations or answer["decision"] == UNDETERMINED else "invalid_evidence"
    if request["remaining_queries"] == 0:
        return "budget_exhausted"
    if not isinstance(action, str) or action not in request["available_queries"]:
        return "unavailable_query"
    if action in evidence:
        return "repeated_query"
    if (not isinstance(prediction, dict) or set(prediction) != {"feature", "higher", "lower"}
            or prediction["feature"] not in OBSERVATIONS[action]
            or prediction["higher"] not in LABELS or prediction["lower"] not in LABELS
            or prediction["higher"] == prediction["lower"]):
        return "invalid_prediction"
    return "query"


def execute_query(case, calibration, answer, classification):
    if classification != "query":
        return {"status": classification}
    bundle = answer["action"]
    measurements = case["observations"][bundle]
    prediction = answer["prediction"]
    feature = prediction["feature"]
    classes = calibration[bundle][feature]["classes"]
    high = classes[prediction["higher"]]["median"]
    low = classes[prediction["lower"]]["median"]
    observed = measurements[feature]
    return {
        "status": "ok", "observation": _public_observation(bundle, measurements),
        "prediction_check": {
            "feature": feature, "observed": observed, "higher_dev_median": high, "lower_dev_median": low,
            "closer_to": ("tie" if abs(observed - high) == abs(observed - low)
                          else prediction["higher"] if abs(observed - high) < abs(observed - low)
                          else prediction["lower"]),
        },
    }


def session(case, calibration, next_answer):
    """Run or replay one session. Each attempted query consumes one slot."""
    history = []
    trace = []
    remaining = QUERY_BUDGET
    decision = None
    status = "incomplete"
    for turn in range(1, QUERY_BUDGET + 2):
        request = request_for(case, calibration, history.copy(), remaining)
        answer, transport = next_answer(turn, request)
        if transport:
            status = transport
            trace.append({"turn": turn, "answer": answer, "status": status})
            break
        status = classify_answer(answer, request)
        entry = {"turn": turn, "answer": answer, "status": status}
        trace.append(entry)
        if status == "finish":
            decision = answer["decision"]
            break
        if status in ("invalid_answer", "invalid_evidence", "budget_exhausted"):
            break
        response = execute_query(case, calibration, answer, status)
        entry["result"] = response
        history.append({"answer": answer, "result": response})
        remaining -= 1
    return {
        "status": "completed" if status == "finish" else status,
        "decision": decision,
        "queries": QUERY_BUDGET - remaining,
        "valid_queries": sum(event["result"]["status"] == "ok" for event in history),
        "invalid_actions": sum(row["status"] not in ("finish", "query", "transport_error", "interrupted")
                               for row in trace),
        "trace": trace,
    }


def rule_session(case, calibration, stop, strategy):
    return session(case, calibration, lambda _, request: (rule_answer(strategy, request, stop), None))


def tune_stop(recordings, motor_order):
    folds = []
    for motor in motor_order:
        fit = [row for row in recordings if row["motor_w"] != motor]
        test = [row for row in recordings if row["motor_w"] == motor]
        folds.append((make_calibration(fit), test))
    scored = []
    for distance, margin in itertools.product(DISTANCE_LIMITS, MARGIN_LIMITS):
        stop = {"max_distance": distance, "min_margin": margin}
        by_label = {label: [] for label in LABELS}
        wrong = queries = 0
        for calibration, test in folds:
            for index, row in enumerate(test):
                case = {"task_id": f"development-{index}", "observations": row["observations"]}
                for strategy in RULES:
                    outcome = rule_session(case, calibration, stop, strategy)
                    answer = outcome["decision"]
                    loss = 0 if answer == row["label"] else 0.5 if answer == UNDETERMINED else 1
                    by_label[row["label"]].append(loss)
                    wrong += loss == 1
                    queries += outcome["queries"]
        macro_loss = sum(sum(losses) / len(losses) for losses in by_label.values()) / len(LABELS)
        scored.append({**stop, "macro_loss": macro_loss, "wrong": wrong, "queries": queries})
    best = min(scored, key=lambda row: (row["macro_loss"], row["wrong"], row["queries"]))
    return {key: best[key] for key in ("max_distance", "min_margin")}, scored
