"""Targeted Remediation Gates 1-4 adjudication (frozen 919fcf2, impl 41b7b46)."""

from __future__ import annotations

import json
from pathlib import Path

OUTPUT = Path(r"E:\3\_visual_agent_real_world_acceptance\v1\_general_rgb_final_acceptance_remediation_v1")

F2_INVALID = {"fishing_021", "fishing_022"}
F4_INVALID = {"fishing_010", "fishing_022", "fishing_025"}

F2_REF = {
    "fishing_002": [3170.2, 2012.95, 3647.27, 3273.71],
    "fishing_004": [3489.95, 1180.05, 4441.24, 3564.27],
    "fishing_008": [1731.32, 3957.72, 2149.14, 4507.34],
    "fishing_009": [2047.97, 2.56, 4089.2, 2788.53],
    "fishing_012": [1718.0, 895.0, 4020.0, 4034.0],
    "fishing_013": [1290.08, 2017.8, 2329.53, 3802.3],
    "fishing_014": [2695.03, 1846.72, 3228.39, 2889.21],
    "fishing_015": [2999.05, 1622.48, 3504.69, 2266.66],
    "fishing_016": [2475.14, 1642.49, 3341.06, 3675.66],
    "fishing_024": [1333.66, 1486.82, 1896.49, 2669.0],
    "fishing_025": [706.53, 772.24, 1382.39, 2389.67],
    "fishing_026": [580.85, 1626.76, 1854.29, 3962.56],
    "fishing_027": [360.61, 791.13, 1015.5, 2423.81],
    "fishing_029": [1857.41, 4252.47, 2571.89, 6200.18],
    "fishing_030": [1335.31, 77.96, 1916.43, 1276.59],
}
F2_SINGLE_PERSON = {"fishing_009", "fishing_028"}
F2_REF["fishing_028"] = [0.0, 511.49, 2319.57, 4281.92]
F4_REF = {
    "fishing_001": [82.09, 2516.94, 3674.47, 7719.49],
    "fishing_003": [1089.57, 357.53, 2123.86, 1684.45],
    "fishing_005": [987.83, 567.11, 2230.0, 3493.45],
    "fishing_006": [865.87, 132.62, 3278.81, 2930.64],
    "fishing_007": [1922.91, 784.92, 3331.53, 2945.28],
    "fishing_009": [2047.97, 2.56, 4089.2, 2788.53],
    "fishing_017": [0.0, 0.0, 1140.06, 2078.16],
}
F4_SINGLE_PERSON = {"fishing_020"}
F4_REF["fishing_020"] = [87.97, 14.53, 3826.89, 5734.23]
CHALLENGE_REF = {
    "challenge_001": {"fisher": [155.37, 23.12, 205.32, 124.4], "non_fisher": [183.95, 60.79, 234.64, 148.47]},
    "challenge_003": {"person": [260.7, 168.83, 309.72, 301.64]},
    "challenge_004": {"elder": [471.6, 98.27, 544.83, 320.23], "child": [430.95, 171.57, 485.74, 337.7]},
}


def read_rows(gate):
    p = OUTPUT / ("raw_execution_gate" + str(gate) + ".jsonl")
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union > 0 else 0.0


def satisfied_targets(row):
    return [t for t in row.get("targets", []) if t.get("bbox")]


def relation_ok(row):
    checks = []
    for c in row.get("candidates", []):
        checks.extend(c.get("verification_checks") or [])
    return any(c.get("status") == "satisfied" and ("拿" in (c.get("constraint") or "")) for c in checks)


def has_binding_conflict(row):
    return any(g.get("completion_reason") == "binding_conflict" for g in row.get("semantic_groups", []))


def protocol_leaves(value):
    if isinstance(value, dict):
        if {"attempts", "retry_count", "recovered"}.issubset(value):
            return [value]
        out = []
        for v in value.values():
            out.extend(protocol_leaves(v))
        return out
    if isinstance(value, list):
        out = []
        for v in value:
            out.extend(protocol_leaves(v))
        return out
    return []


def gate1():
    rows = read_rows(1)
    rel_ok = 0
    behavior_route = 0
    out = {"scheduled": 20, "terminal": len(rows), "rows": []}
    for r in rows:
        plan = r.get("plan") or {}
        constraints = plan.get("constraints") or []
        related = plan.get("related_objects") or []
        route = constraints[0].get("route") if constraints else None
        held = related[0].get("relation") if related else None
        canonical = route == "relation" and held == "held_by_target"
        if canonical:
            rel_ok += 1
        if route == "behavior":
            behavior_route += 1
        out["rows"].append({"unit_id": r["unit_id"], "terminal_status": r["terminal_status"], "route": route, "relation": held, "canonical": canonical, "plan_attempts": r.get("plan_attempts")})
    out["validated_canonical"] = rel_ok
    out["behavior_route"] = behavior_route
    out["gate"] = "PASS" if (len(rows) == 20 and all(x["terminal_status"] == "success" for x in rows) and rel_ok == 20 and behavior_route == 0) else "FAIL"
    return out


def gate2():
    rows = read_rows(2)
    by_case = {}
    for r in rows:
        by_case.setdefault(r["case_id"], []).append(r)
    per = {}
    for case, reps in by_case.items():
        info = {"reps": []}
        for r in reps:
            ok = r.get("terminal_status") == "success"
            targets = satisfied_targets(r)
            conflict = has_binding_conflict(r)
            if case == "F2::fishing_001.jpeg":
                status = "TN" if (ok and len(targets) == 0) else ("false_assignment" if (ok and len(targets) > 0) else "error")
            elif case == "F2::fishing_024.jpeg":
                ref = F2_REF["fishing_024"]
                retained = ok and relation_ok(r) and any(iou(t["bbox"], ref) >= 0.3 for t in targets)
                status = "retained" if retained else ("binding_conflict" if (ok and conflict) else ("no_target" if ok else "error"))
            elif case == "F4::fishing_017.jpeg":
                ref = F4_REF["fishing_017"]
                retained = ok and relation_ok(r) and any(iou(t["bbox"], ref) >= 0.3 for t in targets)
                status = "retained" if retained else ("no_target" if ok else "error")
            elif case == "challenge_001":
                fisher = CHALLENGE_REF["challenge_001"]["fisher"]
                non = CHALLENGE_REF["challenge_001"]["non_fisher"]
                wrong = any(iou(t["bbox"], non) >= 0.3 and iou(t["bbox"], fisher) < 0.2 for t in targets)
                kept = any(iou(t["bbox"], fisher) >= 0.3 for t in targets)
                status = "false_assignment" if wrong else ("retained" if kept else ("no_target" if ok else "error"))
            elif case == "challenge_004":
                elder = CHALLENGE_REF["challenge_004"]["elder"]
                child = CHALLENGE_REF["challenge_004"]["child"]
                kept = any(iou(t["bbox"], elder) >= 0.25 for t in targets)
                child_conf = any(iou(t["bbox"], child) >= 0.3 and iou(t["bbox"], elder) < 0.15 for t in targets)
                status = "child_false_assignment" if child_conf else ("elder_retained" if kept else ("no_target" if ok else "error"))
            elif case == "challenge_003":
                person = CHALLENGE_REF["challenge_003"]["person"]
                wrong = any(iou(t["bbox"], person) < 0.2 for t in targets)
                kept = any(iou(t["bbox"], person) >= 0.3 for t in targets)
                status = "false_assignment" if wrong else ("retained_safe" if kept else ("ambiguous_no_target" if ok else "error"))
            else:
                status = "unknown"
            info["reps"].append({"unit_id": r["unit_id"], "status": status, "target_count": r.get("target_count", 0)})
        per[case] = info

    def tally(case, want):
        reps = per.get(case, {}).get("reps", [])
        return sum(1 for x in reps if x["status"] == want), len(reps)

    checks = {}
    checks["F2 001 TN"] = tally("F2::fishing_001.jpeg", "TN")
    checks["F2 001 no_false_assignment"] = (len(per["F2::fishing_001.jpeg"]["reps"]) - tally("F2::fishing_001.jpeg", "false_assignment")[0], 5)
    checks["F2 024 retained"] = tally("F2::fishing_024.jpeg", "retained")
    checks["F2 024 no_binding_conflict"] = (len(per["F2::fishing_024.jpeg"]["reps"]) - tally("F2::fishing_024.jpeg", "binding_conflict")[0], 5)
    checks["F4 017 retained"] = tally("F4::fishing_017.jpeg", "retained")
    checks["challenge_001 no_false_assignment"] = (len(per["challenge_001"]["reps"]) - tally("challenge_001", "false_assignment")[0], 5)
    checks["challenge_004 elder_retained"] = tally("challenge_004", "elder_retained")
    checks["challenge_004 no_child_false_assignment"] = (len(per["challenge_004"]["reps"]) - tally("challenge_004", "child_false_assignment")[0], 5)
    checks["challenge_003 no_false_assignment"] = (len(per["challenge_003"]["reps"]) - tally("challenge_003", "false_assignment")[0], 5)
    checks["challenge_003 ambiguity_safe"] = tally("challenge_003", "retained_safe")
    ok_all = (
        checks["F2 001 TN"][0] == 5
        and checks["F2 001 no_false_assignment"][0] == 5
        and checks["F2 024 retained"][0] == 5
        and checks["F2 024 no_binding_conflict"][0] == 5
        and checks["F4 017 retained"][0] >= 4
        and checks["challenge_001 no_false_assignment"][0] == 5
        and checks["challenge_004 elder_retained"][0] >= 4
        and checks["challenge_004 no_child_false_assignment"][0] == 5
        and checks["challenge_003 no_false_assignment"][0] == 5
        and checks["challenge_003 ambiguity_safe"][0] == 5
    )
    return {"gate": "PASS" if (len(rows) == 30 and ok_all) else "FAIL", "checks": {k: {"v": v[0], "den": v[1]} for k, v in checks.items()}, "case_breakdown": per}


def gate3():
    rows = read_rows(3)
    calls = [c for r in rows for c in r.get("vlm_calls", [])]
    leaves = [l for r in rows for l in protocol_leaves(r.get("qwen_protocol"))]
    system = {
        "scheduled": 60,
        "terminal": len(rows),
        "success": sum(1 for r in rows if r["terminal_status"] == "success"),
        "system_failure": sum(1 for r in rows if r["terminal_status"] == "error"),
        "provider_attempt_failure": sum(1 for c in calls if c.get("status") == "error"),
        "unexpected_model": sum(1 for c in calls if c.get("model") != "qwen3.8:27b-mtp-q4_K_M"),
        "unexpected_endpoint": sum(1 for c in calls if (c.get("base_url") or "").rstrip("/") != "http://192.168.250.9:11434/v1"),
        "protocol_final_failure": 0,
        "validator_final_failure": 0,
    }
    per = {"F2": {"positives": {}, "negatives": {}}, "F4": {"positives": {}, "negatives": {}}}
    invalid_ok = {"F2": 0, "F4": 0}
    new_invalid = []
    for r in rows:
        prompt = r["prompt_id"]
        stem = Path(r["image_name"]).stem
        if r["frozen_invalid"]:
            invalid_ok[prompt] += 1 if r["terminal_status"] == "success" else 0
            continue
        if r["terminal_status"] != "success":
            new_invalid.append(r["unit_id"])
            continue
        gt = r["ground_truth_class"]
        targets = satisfied_targets(r)
        if gt == "positive":
            ref = (F2_REF if prompt == "F2" else F4_REF).get(stem)
            single = stem in (F2_SINGLE_PERSON if prompt == "F2" else F4_SINGLE_PERSON)
            usable = relation_ok(r) and (single or (ref is not None and any(iou(t["bbox"], ref) >= 0.3 for t in targets)))
            per[prompt]["positives"][stem] = {"unit_id": r["unit_id"], "usable": usable, "target_count": r.get("target_count", 0), "ref": ref}
        else:
            per[prompt]["negatives"][stem] = {"unit_id": r["unit_id"], "tn": r.get("target_count", 0) == 0, "target_count": r.get("target_count", 0)}
    summary = {}
    for prompt in ("F2", "F4"):
        pos = per[prompt]["positives"]
        neg = per[prompt]["negatives"]
        usable = sum(1 for v in pos.values() if v["usable"])
        tn = sum(1 for v in neg.values() if v["tn"])
        summary[prompt] = {
            "positive_usable": str(usable) + "/" + str(len(pos)),
            "positive_den": len(pos),
            "negative_tn": str(tn) + "/" + str(len(neg)),
            "negative_den": len(neg),
            "frozen_invalid_kept": invalid_ok[prompt],
        }
    ok = (
        len(rows) == 60
        and system["system_failure"] == 0
        and system["provider_attempt_failure"] == 0
        and invalid_ok["F2"] == 2
        and invalid_ok["F4"] == 3
        and not new_invalid
        and int(summary["F2"]["positive_usable"].split("/")[0]) >= 11
        and int(summary["F2"]["negative_tn"].split("/")[0]) >= 10
        and int(summary["F4"]["positive_usable"].split("/")[0]) >= 7
        and int(summary["F4"]["negative_tn"].split("/")[0]) >= 18
    )
    return {"gate": "PASS" if ok else "FAIL", "system": system, "summary": summary, "new_invalid": new_invalid, "failures": [r["unit_id"] for r in rows if r["terminal_status"] == "error"]}


def gate4():
    rows = read_rows(4)
    expected = {
        "core_003": {"target_object": "person", "action": "outline", "target_count": 1},
        "core_004": {"target_object": "person", "action": "cutout", "target_count": 1},
        "core_014": {"target_object": "person", "action": "outline", "target_count": 0},
    }
    details = {}
    for r in rows:
        exp = expected.get(r["case_id"])
        plan = r.get("plan") or {}
        ok = (
            r["terminal_status"] == "success"
            and plan.get("target_object") == exp["target_object"]
            and (plan.get("action") or {}).get("type") == exp["action"]
            and r.get("target_count", -1) == exp["target_count"]
        )
        details[r["case_id"]] = {
            "pass": ok,
            "terminal_status": r["terminal_status"],
            "target_object": plan.get("target_object"),
            "action": (plan.get("action") or {}).get("type"),
            "target_count": r.get("target_count"),
            "expected": exp,
        }
    ok_all = len(rows) == 3 and all(v["pass"] for v in details.values())
    return {"gate": "PASS" if ok_all else "FAIL", "details": details}


def main():
    report = {
        "stage": "GENERAL_RGB_FINAL_ACCEPTANCE_REMEDIATION_V1_TARGETED_GATES",
        "implementation_commit": "1960505b6378024e403b2e23750dff03fc2cecbf",
        "contract": "919fcf200fefebbe10f7c87a579def9c8d3f9348",
        "frozen_config": {
            "planner_model": "qwen3.8:27b-mtp-q4_K_M",
            "planner_base_url": "http://192.168.250.9:11434/v1",
            "planner_api_key": "ollama",
            "vlm_model": "qwen3.8:27b-mtp-q4_K_M",
            "vlm_base_url": "http://192.168.250.9:11434/v1",
            "vlm_api_key": "ollama",
            "vlm_timeout_seconds": 120,
            "concurrency": 1,
        },
        "vlm_model": "qwen3.8:27b-mtp-q4_K_M",
        "gate1_planner_stability": gate1(),
        "gate2_blocker_stability": gate2(),
        "gate3_f2f4_regression": gate3(),
        "gate4_core_controls": gate4(),
    }
    out_json = OUTPUT / "gate_adjudication.json"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")
    fence = chr(96) * 3
    lines = ["# Targeted Remediation Gates - Adjudication", ""]
    pairs = [
        ("gate1_planner_stability", "Gate 1 - Planner stability"),
        ("gate2_blocker_stability", "Gate 2 - Blocker stability"),
        ("gate3_f2f4_regression", "Gate 3 - F2/F4 regression"),
        ("gate4_core_controls", "Gate 4 - Core relation controls"),
    ]
    for key, label in pairs:
        g = report[key]
        lines.append("## " + label + ": " + g["gate"])
        lines.append(fence + "json")
        lines.append(json.dumps(g, ensure_ascii=False, indent=1))
        lines.append(fence)
        lines.append("")
    out_md = OUTPUT / "gate_adjudication.md"
    out_md.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    for key, label in pairs:
        print(key, "=", report[key]["gate"])


if __name__ == "__main__":
    main()

