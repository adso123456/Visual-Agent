from benchmark.f4_small_held_object_localization_v1.run_gate_l import (
    bbox_iou,
    hand_crops,
    localization_metrics,
    remap_bbox,
    stable_deduplicate,
)


REFERENCE = {"bbox": [820, 690, 945, 780], "center": [885, 735]}


def test_reference_localization_requires_all_three_conditions():
    assert localization_metrics([820, 690, 945, 780], REFERENCE)["localized"]
    assert not localization_metrics([800, 650, 1100, 740], REFERENCE)["localized"]
    assert not localization_metrics([820, 690, 870, 730], REFERENCE)["localized"]


def test_bbox_remap_and_iou():
    assert remap_bbox([1, 2, 11, 12], [100, 200, 300, 400]) == [101, 202, 111, 212]
    assert bbox_iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0


def test_deduplication_keeps_higher_confidence_stably():
    items = [
        {"bbox": [0, 0, 10, 10], "confidence": 0.4},
        {"bbox": [0, 0, 10, 10], "confidence": 0.8},
        {"bbox": [20, 20, 30, 30], "confidence": 0.5},
    ]
    assert stable_deduplicate(items) == [items[1], items[2]]


def test_hand_crops_filter_sort_top_two_and_expand():
    call = {
        "remapped_detections": [
            {"bbox": [100, 100, 200, 200], "confidence": 0.6},
            {"bbox": [300, 300, 400, 400], "confidence": 0.9},
            {"bbox": [500, 500, 600, 600], "confidence": 0.8},
            {"bbox": [1300, 100, 1400, 200], "confidence": 0.99},
        ]
    }
    assert hand_crops([0, 0, 1538, 2811], [0, 0, 1140, 2078], call) == [
        [200, 200, 500, 500],
        [400, 400, 700, 700],
    ]
