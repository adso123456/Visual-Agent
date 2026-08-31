"""Production Implementation Contract §3.2：preflight 两时点校验 + additive key 存在性。

BEFORE implementation：`git show be54f3c:<path>` 复算 8/8 冻结 SHA（对冻结基线复算，
而非修改后的当前文件）。
AFTER implementation：5 个不变文件当前工作区 == 冻结 SHA；pipeline.py / evidence.py / vlm.py
允许变化但 base（be54f3c）SHA 必须匹配冻结值。
合同 status：PRODUCTION_IMPLEMENTATION_CONTRACT.md 含 CONTRACT FROZEN。
additive key：stub 全链路 run 后 result 含 behavior_routing / relation_hand_fallback。
"""

import hashlib
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np

from visual_agent.pipeline import run_pipeline

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = (
    Path(r"E:\3\Visual Agent\_evidence_worktree")
    / "evidence"
    / "final_acceptance"
    / "GENERAL_RGB_BEHAVIOR_RELATION_PRODUCTION_IMPLEMENTATION_CONTRACT_V1"
)
FROZEN_BASE = "be54f3c89171d8b16f53c82397e9f468fb4b4c97"

FROZEN_SHA = {
    "visual_agent/pipeline.py": "531903d340e64faa6e745c9fb83d65532d553ff604a87789f2057a57aadb0452",
    "visual_agent/evidence.py": "8dc4f1d6a62f1873b1479a78c08130d0c4d79286a2afcaa24d11f93cb5749747",
    "visual_agent/vlm.py": "a2df5c9605deb3ee9d5e7803eab0effa83e5c6c21cc928633a0460f54ae6d83e",
    "visual_agent/relations.py": "293f2c983f792d541ec0c6021ef49e82ae0d0b8553963bc925424b555286f968",
    "visual_agent/grounding.py": "ac56602ecd1c4d09286784fc17eb79c18fe3ebb4c7f98f62ae96e0167c28f3be",
    "visual_agent/qwen_protocol.py": "89ccd004b9738804ecace48478044af660d5497aafa4d7753bc5e4a4c46ebfb3",
    "visual_agent/vlm_client.py": "a36782166b41fde299cb3cd328fb145bc0597ae8bd49c0510f1eb6d832a82c88",
    "visual_agent/deepseek_agent.py": "cdc6be9cdc4b518734b014ca9e44144d7b4da1895da6bdb74de9fed5290f1f12",
}
CHANGED_ALLOWED = {
    "visual_agent/pipeline.py",
    "visual_agent/evidence.py",
    "visual_agent/vlm.py",
}
UNCHANGED_REQUIRED = set(FROZEN_SHA) - CHANGED_ALLOWED


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_show(commit: str, rel: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{rel}"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
    ).stdout


def _worktree_form(commit: str, rel: str) -> bytes:
    """合同 SHA 按 Windows 工作区（CRLF checkout）复算；blob 为 LF，需归一化。"""
    blob = _git_show(commit, rel)
    sample = (REPO_ROOT / "visual_agent/vlm.py").read_bytes()
    if b"\r\n" in sample:
        blob = blob.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    return blob


def test_preflight_before_implementation_base_shas():
    """BEFORE：对冻结基线 be54f3c 复算 8/8 SHA（两时点分离规则）。"""
    for rel, want in FROZEN_SHA.items():
        got = _sha256(_worktree_form(FROZEN_BASE, rel))
        assert got == want, f"{rel} base SHA 不匹配：{got}"


def test_preflight_after_unchanged_files_still_frozen():
    """AFTER：5 个不变文件当前工作区必须仍等于冻结 SHA。"""
    for rel in UNCHANGED_REQUIRED:
        got = _sha256((REPO_ROOT / rel).read_bytes())
        assert got == FROZEN_SHA[rel], f"{rel} 被意外修改（必须字节级不变）"


def test_preflight_after_changed_files_have_frozen_base():
    """AFTER：三个已授权文件允许变化，但 base（be54f3c）SHA 必须匹配冻结值。"""
    for rel in CHANGED_ALLOWED:
        base = _sha256(_worktree_form(FROZEN_BASE, rel))
        assert base == FROZEN_SHA[rel], f"{rel} base 与冻结不一致"
        current = _sha256((REPO_ROOT / rel).read_bytes())
        assert current != FROZEN_SHA[rel], f"{rel} 未按合同实现（与冻结基线相同）"


def test_contract_status_frozen():
    contract = CONTRACT_DIR / "PRODUCTION_IMPLEMENTATION_CONTRACT.md"
    assert contract.is_file(), f"合同缺失：{contract}"
    text = contract.read_text(encoding="utf-8")
    assert "CONTRACT FROZEN" in text
    assert "revision 2" in text


def _image(tmp_path):
    path = tmp_path / "input.jpg"
    cv2.imwrite(str(path), np.zeros((32, 48, 3), dtype=np.uint8))
    return path


def _plan():
    return {
        "target_object": "person",
        "label": "测试人物",
        "constraints": [{"text": "正在钓鱼", "route": "behavior"}],
        "action": {"type": "box"},
        "related_objects": [],
    }


def test_result_additive_keys_exist(tmp_path, monkeypatch):
    """合同 §2.2 P2.4：result 必须包含 behavior_routing 与 relation_hand_fallback。"""

    class DetectorStub:
        device = "cpu"
        load_seconds = 0.0
        memory_after_load_mb = 0.0

        def __init__(self, count=2):
            self.count = count

        def detect(self, _image_path, target_object, threshold=0.3):
            if target_object == "hand":
                return []
            return [
                {
                    "bbox": [2 + 10 * index, 3, 10 + 10 * index, 20],
                    "text_label": target_object,
                    "confidence": 0.9,
                }
                for index in range(self.count)
            ]

    class SegmenterStub:
        device = "cpu"
        load_seconds = 0.0
        memory_after_load_mb = 0.0

        def segment(self, image_path, boxes):
            image = cv2.imread(str(image_path))
            results = []
            for box in boxes:
                mask = np.zeros(image.shape[:2], dtype=bool)
                x1, y1, x2, y2 = map(int, box)
                mask[y1:y2, x1:x2] = True
                results.append({"mask": mask, "score": 0.95})
            return results, {"model": "stub", "device": "cpu"}

    monkeypatch.setattr(
        "visual_agent.pipeline.get_detector", lambda fresh=False: (DetectorStub(), True)
    )
    monkeypatch.setattr(
        "visual_agent.pipeline.get_segmenter", lambda fresh=False: (SegmenterStub(), True)
    )
    monkeypatch.setattr(
        "visual_agent.pipeline.verify_subject_instance",
        lambda candidate, target, evidence: (
            {
                "candidate_id": candidate["id"],
                "target_object": target,
                "status": "valid",
                "evidence": "有效实例",
            },
            {"attempts": 1},
        ),
    )
    monkeypatch.setattr(
        "visual_agent.pipeline.verify_candidate_constraints",
        lambda candidate, constraints, evidence, route: (
            [
                {
                    "constraint": item["text"],
                    "status": "satisfied",
                    "evidence": "明确",
                }
                for item in constraints
            ],
            {"attempts": 1},
        ),
    )
    _, result_path = run_pipeline(
        _image(tmp_path),
        "框出正在钓鱼的人",
        plan=_plan(),
        verify=True,
        final_response=False,
        output_dir=tmp_path / "out",
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert "behavior_routing" in result
    assert "relation_hand_fallback" in result
    assert result["relation_hand_fallback"]["max_per_subject"] == 1
    assert isinstance(result["behavior_routing"], dict)
