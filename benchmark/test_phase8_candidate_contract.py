import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from visual_agent.vlm import validate_candidate_verification


CANDIDATES = [{"id": "A"}, {"id": "B"}]
CONSTRAINTS = ["正在钓鱼"]


def item(candidate_id: str, status: str = "satisfied", evidence: str = "可见证据") -> dict:
    return {
        "id": candidate_id,
        "checks": [
            {
                "constraint": "正在钓鱼",
                "status": status,
                "evidence": evidence,
            }
        ],
    }


def must_fail(result: dict) -> None:
    try:
        validate_candidate_verification(result, CANDIDATES, CONSTRAINTS)
    except RuntimeError:
        return
    raise AssertionError("预期 candidate contract 校验失败")


def main() -> None:
    valid = {"candidates": [item("A"), item("B", "not_satisfied")]}
    assert len(validate_candidate_verification(valid, CANDIDATES, CONSTRAINTS)) == 2
    must_fail({"candidates": {"A": {"checks": item("A")["checks"]}, "B": {"checks": item("B")["checks"]}}})
    must_fail({"candidates": [item("A")]})
    must_fail({"candidates": [item("A"), item("C")]})
    must_fail({"candidates": [item("A"), item("A")]})
    must_fail({"candidates": [{"id": "A", "checks": []}, item("B")]})
    wrong_constraint = item("A")
    wrong_constraint["checks"][0]["constraint"] = "别的约束"
    must_fail({"candidates": [wrong_constraint, item("B")]})
    must_fail({"candidates": [item("A", "yes"), item("B")]})
    must_fail({"candidates": [item("A", evidence=""), item("B")]})
    assert validate_candidate_verification(
        {"candidates": [item("A", "uncertain"), item("B")]}, CANDIDATES, CONSTRAINTS
    )[0]["checks"][0]["status"] == "uncertain"
    assert validate_candidate_verification(
        {"candidates": [item("A", "not_satisfied"), item("B")]}, CANDIDATES, CONSTRAINTS
    )[0]["checks"][0]["status"] == "not_satisfied"
    print("Phase 8 candidate contract: PASS")


if __name__ == "__main__":
    main()
