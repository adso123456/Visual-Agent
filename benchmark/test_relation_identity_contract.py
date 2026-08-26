import json
from types import SimpleNamespace

from PIL import Image

from visual_agent import relations


class _Completions:
    def __init__(self, content: str):
        self.content = content
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self.content)
                )
            ]
        )


def test_relation_prompt_requires_requested_object_identity_before_satisfied(
    tmp_path, monkeypatch
):
    image_path = tmp_path / "scene.jpg"
    Image.new("RGB", (40, 32), "white").save(image_path)
    subject = {"id": "A", "bbox": [2, 2, 18, 30]}
    related = {"id": "R1", "bbox": [12, 8, 24, 28]}
    response = json.dumps(
        {
            "bindings": [
                {
                    "subject_id": "A",
                    "related_id": "R1",
                    "relation": "held_by_target",
                    "status": "not_satisfied",
                    "evidence": "蓝框不是所请求的雨伞",
                }
            ]
        },
        ensure_ascii=False,
    )
    completions = _Completions(response)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    monkeypatch.setattr(relations, "_client", lambda: client)

    relations.verify_relations(
        image_path,
        [subject],
        [related],
        "umbrella",
        "held_by_target",
    )

    request_text = json.dumps(
        completions.calls[0]["messages"],
        ensure_ascii=False,
    )
    assert "蓝框候选本身可确认是用户请求中指定的关联实体" in request_text
    assert "蓝框不是所请求实体时绝不能 satisfied" in request_text
