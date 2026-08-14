"""进程内模型常驻复用注册表。

默认情况下 GroundingDetector / Sam2Segmenter 只在进程内加载一次，
后续调用直接复用，避免每次运行白白付出 ~17s 的模型加载开销
（DINO Base 约 11s，SAM2.1 Base+ 约 6s，见 measure_latency 报告）。

- get_detector / get_segmenter 返回 (实例, 是否本次命中缓存)。
- fresh=True 会强制重新加载（用于冷启动测量或隔离评测）。
- reset_models() 清空缓存（进程回收或 benchmark 隔离用）。
"""

import threading

from visual_agent.grounding import GroundingDetector
from visual_agent.segmentation import Sam2Segmenter

_lock = threading.Lock()
_detector: GroundingDetector | None = None
_segmenter: Sam2Segmenter | None = None


def get_detector(*, fresh: bool = False) -> tuple[GroundingDetector, bool]:
    """返回常驻 GroundingDetector；cached=True 表示本次未重新加载模型。"""
    global _detector
    with _lock:
        if fresh or _detector is None:
            _detector = GroundingDetector()
            return _detector, False
        return _detector, True


def get_segmenter(*, fresh: bool = False) -> tuple[Sam2Segmenter, bool]:
    """返回常驻 Sam2Segmenter；cached=True 表示本次未重新加载模型。"""
    global _segmenter
    with _lock:
        if fresh or _segmenter is None:
            _segmenter = Sam2Segmenter()
            return _segmenter, False
        return _segmenter, True


def reset_models() -> None:
    """清空常驻模型缓存（释放引用，进程结束时回收显存）。"""
    global _detector, _segmenter
    with _lock:
        _detector = None
        _segmenter = None
