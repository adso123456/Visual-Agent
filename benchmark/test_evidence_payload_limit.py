"""SYSTEM_RELIABILITY_FIX_V1: Qwen PNG evidence payload normalization unit tests."""
from PIL import Image
from visual_agent.vlm import (
    _pil_image_data_url,
    _take_evidence_telemetry,
    EVIDENCE_PAYLOAD_SAFE_LIMIT,
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
    n = tel["normalized_dimensions"]
    assert n[0] * n[1] <= 8_000_000