"""Portable external-data records and read-only recomputation."""
from copy import deepcopy
import json
import math
from pathlib import Path
import shutil
from .external_waveforms import analyze_dataset, load_intake, relative_file, validate_intake
from .utils import PROJECT, finalize, now, sha256, write_json
from .versions import record_version_problems, require_analysis_method_version

KIND = "external_waveforms"
SNAPSHOTS = ("external_waveforms.py", "external_reporting.py", "external_records.py", "utils.py", "versions.py")


def analyze_external(intake_path, input_dir, output_dir):
    intake_path = Path(intake_path).resolve()
    source, out = Path(input_dir).resolve(), Path(output_dir).resolve()
    intake = load_intake(intake_path)
    if out == source or out.is_relative_to(source) or source.is_relative_to(out):
        raise ValueError("input and output directories must be separate, non-nested locations")
    if intake_path == out or intake_path.is_relative_to(out):
        raise ValueError("output directory must not contain the input intake file")
    if out.exists():
        raise ValueError("output directory must be new")
    inputs = []
    for rec in intake["records"]:
        for key in ("csv", "image"):
            if rec.get(key):
                path = relative_file(source, rec[key])
                if not path.is_file():
                    raise ValueError(f"missing input: {rec[key]}")
                inputs.append((rec["id"], key, rec[key], path, sha256(path)))
    out.mkdir(parents=True)
    saved = deepcopy(intake)
    records_by_id = {r["id"]: r for r in saved["records"]}
    sources = []
    for rid, key, original, path, digest in inputs:
        suffix = ".csv" if key == "csv" else ".png"
        relative = f"inputs/{rid}/{key}{suffix}"
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        if sha256(target) != digest or sha256(path) != digest:
            raise ValueError(f"input changed during snapshot: {original}")
        records_by_id[rid][key] = relative
        sources.append({"record_id": rid, "role": key, "original_relative_path": original,
                        "snapshot": relative, "sha256": digest})
    write_json(out / "intake.json", saved)
    write_json(out / "provenance.json", {"source_dir": str(source), "intake_source": str(intake_path),
                                        "sources": sources, "original_intake": intake})
    profile, arrays = analyze_dataset(out, saved)
    write_json(out / "profile.json", profile)
    for name in SNAPSHOTS:
        target = out / "code_snapshot" / name
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(PROJECT / "src/typhoon_lab" / name, target)
    from .external_reporting import write_external_report
    write_external_report(out, saved, profile, arrays)
    manifest = {"kind": KIND, "started_at": now(), "configuration_schema_version": 1,
                "analysis_method_version": require_analysis_method_version(KIND),
                "status": "passed" if profile["analysis_status"] == "completed" else "failed",
                "data_quality_status": profile["data_quality_status"], "analysis_status": profile["analysis_status"],
                "performance_status": "not_evaluated",
                "sources": sources, "code_sha256": {name: sha256(out / "code_snapshot" / name) for name in SNAPSHOTS}}
    finalize(out, manifest)
    return {"status": manifest["status"], "run_dir": str(out),
            "data_quality_status": profile["data_quality_status"], "analysis_status": profile["analysis_status"],
            "performance_status": "not_evaluated", "record_status": None}


def _compare(expected, actual, where="profile"):
    """Compare structure exactly, finite floats at declared numerical tolerance."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        if expected.keys() != actual.keys():
            return [f"{where}: fields differ"]
        return [p for key in expected for p in _compare(expected[key], actual[key], f"{where}.{key}")]
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return [f"{where}: length differs"]
        return [p for i, (a, b) in enumerate(zip(expected, actual)) for p in _compare(a, b, f"{where}[{i}]")]
    if type(expected) in (float, int) and type(actual) in (float, int):
        if math.isfinite(expected) and math.isfinite(actual) and math.isclose(expected, actual, rel_tol=1e-10, abs_tol=1e-12):
            return []
    elif type(expected) == type(actual) and expected == actual:
        return []
    return [f"{where}: recomputation differs"]


def verify_external(run_dir, write=False):
    out = Path(run_dir).resolve()
    problems = []
    profile = {}
    try:
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("kind") != KIND:
            raise ValueError("expected external_waveforms record; legacy batch reports are not this format")
        version_problems = record_version_problems(manifest)
        for key in ("record_format_version", "analysis_method_version", "configuration_schema_version"):
            if type(manifest.get(key)) is not int or (key == "configuration_schema_version" and manifest[key] != 1):
                version_problems.append(f"missing or unsupported {key}")
        problems.extend(version_problems)
        hashes = manifest.get("artifacts", {})
        if not isinstance(hashes, dict):
            raise ValueError("invalid artifact hashes")
        required = {"intake.json", "provenance.json", "profile.json", "report.md"} | {
            f"code_snapshot/{name}" for name in SNAPSHOTS}
        for rel, expected in hashes.items():
            artifact = relative_file(out, rel)
            if not artifact.is_file() or sha256(artifact) != expected:
                problems.append(f"artifact missing or changed: {rel}")
        for name in SNAPSHOTS:
            if manifest.get("code_sha256", {}).get(name) != hashes.get(f"code_snapshot/{name}"):
                problems.append(f"code provenance mismatch: {name}")
        if version_problems:
            problems.append("recomputation skipped: unsupported version; old snapshots are never executed")
        else:
            intake = load_intake(out / "intake.json")
            provenance = json.loads((out / "provenance.json").read_text(encoding="utf-8"))
            original = validate_intake(provenance["original_intake"])
            expected_intake = deepcopy(original)
            expected_sources = []
            for rec in expected_intake["records"]:
                for role in ("csv", "image"):
                    if rec.get(role):
                        original_path = rec[role]
                        rel = f"inputs/{rec['id']}/{role}{'.csv' if role == 'csv' else '.png'}"
                        rec[role] = rel
                        required.add(rel)
                        expected_sources.append({"record_id": rec["id"], "role": role,
                                                 "original_relative_path": original_path,
                                                 "snapshot": rel, "sha256": hashes.get(rel)})
            if intake != expected_intake:
                problems.append("intake differs from original declared mapping")
            if provenance.get("sources") != expected_sources or manifest.get("sources") != expected_sources:
                problems.append("source provenance differs from snapshot hashes or intake")
            profile = json.loads((out / "profile.json").read_text(encoding="utf-8"))
            recomputed, arrays = analyze_dataset(out, intake)
            problems.extend(_compare(recomputed, profile))
            required.update(f"{rid}.png" for rid in arrays)
            for key in ("data_quality_status", "analysis_status", "performance_status"):
                if manifest.get(key) != recomputed[key]:
                    problems.append(f"manifest {key} differs from recomputation")
            expected_status = "passed" if recomputed["analysis_status"] == "completed" else "failed"
            if manifest.get("status") != expected_status:
                problems.append("manifest status differs from analysis")
        for rel in sorted(required - hashes.keys()):
            problems.append(f"required artifact not hashed: {rel}")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        problems.append(f"verification error: {exc}")
    result = {"status": "failed" if problems else "passed", "record_status": "failed" if problems else "passed",
              "run_dir": str(out), "verified_at": now(), "problems": problems,
              "data_quality_status": profile.get("data_quality_status"),
              "analysis_status": profile.get("analysis_status"), "performance_status": "not_evaluated",
              "comparison_tolerance": {"relative": 1e-10, "absolute": 1e-12}}
    if write:
        write_json(out / "verification.json", result)
    return result
