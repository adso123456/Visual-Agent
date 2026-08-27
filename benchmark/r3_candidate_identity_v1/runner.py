"""冻结 schedule 的 benchmark-only 执行记录器；不导入任何模型客户端。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .evidence_builder import ArmEvidence


VALID_STATUSES = {"satisfied", "not_satisfied", "uncertain"}


@dataclass(frozen=True)
class Slot:
    case_id: str
    repetition: int
    arm: str
    candidate: dict[str, object]

    @property
    def slot_id(self) -> str:
        return f"{self.case_id}|r{self.repetition}|{self.arm}|{self.candidate['id']}"


def expand_schedule(
    selection: dict[str, object], schedule: dict[str, object]
) -> list[Slot]:
    if schedule.get("failed_execution_replacement") is not False:
        raise ValueError("冻结合同要求 failed_execution_replacement=false")
    cases = {row["case_id"]: row for row in selection["cases"]}
    slots: list[Slot] = []
    rows = list(schedule["challenge_schedule"]) + list(schedule["F1_schedule"])
    for row in rows:
        case = cases[row["case_id"]]
        for arm in row["arm_order"]:
            for candidate in case["candidates"]:
                slots.append(
                    Slot(
                        case_id=row["case_id"],
                        repetition=int(row["repetition"]),
                        arm=arm,
                        candidate=candidate,
                    )
                )
    expected = schedule.get("totals", {}).get("scheduled_first_pass_candidate_calls")
    if expected is not None and len(slots) != expected:
        raise ValueError("展开后的 first-pass slot 数与冻结 schedule 不一致")
    return slots


class ResultRecorder:
    """每个 slot 只允许一个 terminal record；失败保留且不得替换。"""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seen: set[str] = set()
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self._seen.add(json.loads(line)["slot_id"])

    def append(self, record: dict[str, object]) -> None:
        slot_id = str(record["slot_id"])
        if slot_id in self._seen:
            raise ValueError(f"slot 已存在 terminal record，禁止替换: {slot_id}")
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(
                json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            )
        self._seen.add(slot_id)

    def has_terminal_record(self, slot_id: str) -> bool:
        return slot_id in self._seen


EvidenceProvider = Callable[[Slot], ArmEvidence]
Verifier = Callable[[tuple[object, ...]], str]


def classify_fallback(
    candidate: dict[str, object], final_status: str
) -> str:
    """按冻结合同机械分类 uncertain fallback，禁止人工重解释。"""
    if final_status not in VALID_STATUSES:
        raise ValueError(f"非法 final status: {final_status}")
    allowed = candidate.get("allowed")
    if allowed is not None:
        allowed_set = set(allowed)
        if allowed_set == {"not_satisfied", "uncertain"}:
            return "fallback_harm" if final_status == "satisfied" else "non_harm"
        raise ValueError("未知 allowed 状态合同")

    expected = candidate.get("expected")
    classifications = {
        "satisfied": {
            "satisfied": "correctly_resolved",
            "uncertain": "still_uncertain",
            "not_satisfied": "fallback_harm",
        },
        "not_satisfied": {
            "not_satisfied": "correctly_resolved",
            "uncertain": "still_uncertain",
            "satisfied": "fallback_harm",
        },
        "uncertain": {
            "uncertain": "correctly_preserved",
            "satisfied": "fallback_harm",
            "not_satisfied": "fallback_harm",
        },
    }
    if expected not in classifications:
        raise ValueError("candidate 缺少可识别的 expected/allowed 合同")
    return classifications[expected][final_status]


def run_slots(
    slots: list[Slot],
    *,
    evidence_provider: EvidenceProvider,
    verifier: Verifier,
    recorder: ResultRecorder,
) -> None:
    """供未来获批执行使用；本轮测试仅注入 stub verifier。"""
    for slot in slots:
        if recorder.has_terminal_record(slot.slot_id):
            continue
        record: dict[str, object] = {
            "slot_id": slot.slot_id,
            "case_id": slot.case_id,
            "repetition": slot.repetition,
            "arm": slot.arm,
            "candidate_id": slot.candidate["id"],
        }
        try:
            evidence = evidence_provider(slot)
            first = verifier(tuple(evidence.first_pass))
            if first not in VALID_STATUSES:
                raise ValueError(f"非法 verifier status: {first}")
            record["first_pass_status"] = first
            final = first
            fallback_used = False
            if first == "uncertain" and slot.arm in {"A", "C"}:
                if evidence.fallback is None:
                    raise ValueError("冻结 fallback arm 缺少 full-scene evidence")
                final = verifier((evidence.fallback,))
                if final not in VALID_STATUSES:
                    raise ValueError(f"非法 verifier status: {final}")
                fallback_used = True
                record["fallback_classification"] = classify_fallback(
                    slot.candidate, final
                )
            record.update(
                {
                    "fallback_used": fallback_used,
                    "final_status": final,
                    "terminal": "success",
                }
            )
        except Exception as error:  # 保留原始失败，继续后续冻结 slot。
            record.update(
                {
                    "terminal": "failed",
                    "failure_type": type(error).__name__,
                    "failure_message": str(error),
                }
            )
        recorder.append(record)
