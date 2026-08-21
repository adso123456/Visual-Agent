"""SYSTEM_RELIABILITY_FIX_V1: Qwen PNG evidence payload normalization unit tests."""
from PIL import Image
import pytest

from visual_agent import vlm
from visual_agent.vlm import (
    _pil_image_data_url,
    _take_evidence_telemetry,
    EVIDENCE_PAYLOAD_SAFE_LIMIT,
    EVIDENCE_NORMALIZE_TARGET_PIXELS,
    _DATA_URI_PNG_PREFIX,
)

def _payload_len(url):
    return len(url) - len(_DATA_URI_PNG_PREFIX)

def test_small_evidence_untouched():
    im = Image.new("RGB", (512, 512), (120, 80, 40))
    url = _pil_image_data_url(im)
    assert _payload_len(url) <= EVIDENCE_PAYLOAD_SAFE_LIMIT
    tel = _take_evidence_telemetry()
    assert tel is not None, "telemetry missing"
    assert tel["normalization_triggered"] is False
    assert tel["original_dimensions"] == [512, 512]
    assert tel["normalized_dimensions"] == [512, 512]
    assert tel["original_payload_bytes"] == tel["normalized_payload_bytes"]

def test_oversized_noise_evidence_normalized():
    rng = Image.effect_noise((3000, 4000), 60).convert("RGB")
    url = _pil_image_data_url(rng)
    payload = _payload_len(url)
    assert payload <= EVIDENCE_PAYLOAD_SAFE_LIMIT
    tel = _take_evidence_telemetry()
    assert tel["normalization_triggered"] is True
    o = tel["original_dimensions"]
    n = tel["normalized_dimensions"]
    assert (n[0], n[1]) != (o[0], o[1])
    assert abs((n[0] / o[0]) - (n[1] / o[1])) < 0.02
    assert n[0] <= o[0] and n[1] <= o[1]
    assert tel["original_payload_bytes"] > EVIDENCE_PAYLOAD_SAFE_LIMIT
    assert tel["normalized_payload_bytes"] <= EVIDENCE_PAYLOAD_SAFE_LIMIT

def test_4mp_first_pass_target_used():
    rng = Image.effect_noise((3000, 4000), 60).convert("RGB")
    _pil_image_data_url(rng)
    tel = _take_evidence_telemetry()
    assert tel["normalization_triggered"] is True
    n = tel["normalized_dimensions"]
    px = n[0] * n[1]
    # first pass targets ~4 MP: normalization must stop at the first 4 MP attempt
    # (i.e. the 4 MP re-encode already satisfies the safe cap), not degrade further.
    assert abs(px - EVIDENCE_NORMALIZE_TARGET_PIXELS) <= EVIDENCE_NORMALIZE_TARGET_PIXELS * 0.10


def test_unconverged_normalization_raises(monkeypatch):
    im = Image.new("RGB", (4000, 3000), (10, 20, 30))

    def fake_encoder(_image):
        # every re-encode reports an oversized payload: normalization can never converge
        oversized = EVIDENCE_PAYLOAD_SAFE_LIMIT + 1
        return _DATA_URI_PNG_PREFIX + "A" * oversized, oversized

    monkeypatch.setattr(vlm, "_encode_png_data_url", fake_encoder)
    with pytest.raises(RuntimeError, match="failed to satisfy safe limit"):
        _pil_image_data_url(im)