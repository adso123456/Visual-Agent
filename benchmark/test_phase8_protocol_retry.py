import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from visual_agent.qwen_protocol import request_validated_json
from visual_agent.relations import validate_relation_bindings
from visual_agent.vlm import validate_candidate_verification


CANDIDATES = [{"id": "A"}]
CONSTRAINTS = ["正在钓鱼"]
VALID_CANDIDATE = {
    "candidates": [
        {
            "id": "A",
            "checks": [
                {"constraint": "正在钓鱼", "status": "uncertain", "evidence": "证据不足"}
            ],
        }
    ]
}
SUBJECTS = [{"id": "A"}]
RELATED = [{"id": "R1"}]
VALID_RELATION = {
    "bindings": [
        {
            "subject_id": "A",
            "related_id": "R1",
            "relation": "held_by_target",
            "status": "satisfied",
            "evidence": "直接持握",
        }
    ]
}


class Stub:
    def __init__(self, responses: list[str | None | Exception]) -> None:
        self.responses = responses
        self.corrections = []

    def __call__(self, correction: str | None) -> str | None:
        self.corrections.append(correction)
        response = self.responses[len(self.corrections) - 1]
        if isinstance(response, Exception):
            raise response
        return response


def candidate_protocol(responses):
    stub = Stub(responses)
    value, metadata = request_validated_json(
        stub,
        lambda result: validate_candidate_verification(result, CANDIDATES, CONSTRAINTS),
        "candidate verification",
        "candidate schema",
    )
    return stub, value, metadata


def relation_protocol(responses):
    stub = Stub(responses)
    value, metadata = request_validated_json(
        stub,
        lambda result: validate_relation_bindings(
            result, SUBJECTS, RELATED, "held_by_target"
        ),
        "relation verification",
        "relation schema",
    )
    return stub, value, metadata


def assert_contract_retry(protocol, malformed: dict, valid: dict) -> None:
    stub, _, metadata = protocol(
        [json.dumps(malformed, ensure_ascii=False), json.dumps(valid, ensure_ascii=False)]
    )
    assert metadata == {
        "attempts": 2,
        "retry_count": 1,
        "recovered": True,
        "first_error_code": "contract_validation_error",
    }
    assert "FORMAT CORRECTION ONLY" in stub.corrections[1]


def main() -> None:
    wrong_shape = json.dumps({"candidates": {"A": {"checks": []}}}, ensure_ascii=False)
    valid = json.dumps(VALID_CANDIDATE, ensure_ascii=False)

    stub, _, metadata = candidate_protocol([wrong_shape, valid])
    assert metadata == {"attempts": 2, "retry_count": 1, "recovered": True, "first_error_code": "contract_validation_error"}
    assert "FORMAT CORRECTION ONLY" in stub.corrections[1]
    assert "satisfied" not in stub.corrections[1]

    _, _, metadata = candidate_protocol(["{bad", valid])
    assert metadata["first_error_code"] == "json_decode_error" and metadata["recovered"]
    _, _, metadata = candidate_protocol([None, valid])
    assert metadata["first_error_code"] == "empty_response" and metadata["recovered"]
    _, value, metadata = candidate_protocol([valid])
    assert metadata["attempts"] == 1 and metadata["retry_count"] == 0
    assert value[0]["checks"][0]["status"] == "uncertain"

    try:
        candidate_protocol([wrong_shape, wrong_shape])
    except RuntimeError as error:
        assert "after 2 attempts" in str(error) and "contract_validation_error" in str(error)
    else:
        raise AssertionError("两次结构失败必须 RuntimeError")

    network_error = ConnectionError("network down")
    try:
        candidate_protocol([network_error])
    except ConnectionError as error:
        assert error is network_error
    else:
        raise AssertionError("网络异常必须保持原始异常")

    relation_stub = Stub([json.dumps({"bindings": {}}, ensure_ascii=False), json.dumps(VALID_RELATION, ensure_ascii=False)])
    _, relation_metadata = request_validated_json(
        relation_stub,
        lambda result: validate_relation_bindings(result, SUBJECTS, RELATED, "held_by_target"),
        "relation verification",
        "relation schema",
    )
    assert relation_metadata["attempts"] == 2
    assert relation_metadata["recovered"] is True
    assert relation_metadata["first_error_code"] == "contract_validation_error"

    for malformed_candidate in [
        {"candidates": [{"id": [], "checks": []}]},
        {"candidates": [{"id": {}, "checks": []}]},
        {"candidates": [{"id": "A", "checks": {}}]},
    ]:
        assert_contract_retry(candidate_protocol, malformed_candidate, VALID_CANDIDATE)

    valid_binding = VALID_RELATION["bindings"][0]
    for malformed_relation in [
        {"bindings": [{**valid_binding, "subject_id": []}]},
        {"bindings": [{**valid_binding, "related_id": {}}]},
        {"bindings": [{key: value for key, value in valid_binding.items() if key != "status"}]},
    ]:
        assert_contract_retry(relation_protocol, malformed_relation, VALID_RELATION)
    print("Phase 8 protocol retry: PASS")


if __name__ == "__main__":
    main()
