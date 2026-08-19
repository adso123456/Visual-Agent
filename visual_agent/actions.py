import cv2
import numpy as np


ACTION_TYPES = {"highlight", "outline", "box", "blur_target", "dim_background", "cutout"}


class ImageActionExecutor:
    def execute(
        self,
        image: np.ndarray,
        masks: list[np.ndarray],
        action_type: str,
        boxes: list[list[float]] | None = None,
        action_color: str = "#ff0000",
    ) -> np.ndarray:
        if action_type not in ACTION_TYPES:
            raise ValueError(f"不支持的图片操作：{action_type}")
        if action_type == "box":
            return self._box(image, boxes or [], action_color)
        if not masks:
            return image.copy()

        combined_mask = np.logical_or.reduce(masks)
        if action_type == "highlight":
            return self._highlight(image, combined_mask, action_color)
        if action_type == "outline":
            return self._outline(image, combined_mask, action_color)
        if action_type == "blur_target":
            return self._blur_target(image, combined_mask)
        if action_type == "dim_background":
            return self._dim_background(image, combined_mask)
        return self._cutout(image, combined_mask)

    @staticmethod
    def _highlight(
        image: np.ndarray, mask: np.ndarray, color: str = "#ff0000"
    ) -> np.ndarray:
        result = image.copy()
        overlay = np.zeros_like(image)
        overlay[:, :] = ImageActionExecutor._hex_to_bgr(color)
        blended = cv2.addWeighted(image, 0.55, overlay, 0.45, 0)
        result[mask] = blended[mask]
        return result

    @staticmethod
    def _outline(
        image: np.ndarray, mask: np.ndarray, color: str = "#ff0000"
    ) -> np.ndarray:
        result = image.copy()
        binary_mask = mask.astype(np.uint8) * 255
        contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(result, contours, -1, ImageActionExecutor._hex_to_bgr(color), 2)
        return result

    @staticmethod
    def _box(
        image: np.ndarray, boxes: list[list[float]], color: str = "#ff0000"
    ) -> np.ndarray:
        result = image.copy()
        height, width = image.shape[:2]
        line_width = max(2, round(min(height, width) / 300))
        bgr_color = ImageActionExecutor._hex_to_bgr(color)
        for box in boxes:
            if len(box) != 4:
                raise ValueError(f"bbox 必须包含 4 个坐标：{box}")
            x1, y1, x2, y2 = (
                max(0, min(width - 1, round(float(box[0])))),
                max(0, min(height - 1, round(float(box[1])))),
                max(0, min(width - 1, round(float(box[2])))),
                max(0, min(height - 1, round(float(box[3])))),
            )
            if x2 <= x1 or y2 <= y1:
                raise ValueError(f"bbox 坐标无效：{box}")
            cv2.rectangle(result, (x1, y1), (x2, y2), bgr_color, line_width)
        return result

    @staticmethod
    def _hex_to_bgr(color: str) -> tuple[int, int, int]:
        if (
            not isinstance(color, str)
            or len(color) != 7
            or not color.startswith("#")
            or any(character not in "0123456789abcdefABCDEF" for character in color[1:])
        ):
            raise ValueError(f"动作颜色必须是 #RRGGBB：{color}")
        red, green, blue = (int(color[index:index + 2], 16) for index in (1, 3, 5))
        return blue, green, red

    @staticmethod
    def _blur_target(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        result = image.copy()
        blurred = cv2.GaussianBlur(image, (31, 31), 0)
        result[mask] = blurred[mask]
        return result

    @staticmethod
    def _dim_background(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        result = (image.astype(np.float32) * 0.3).astype(np.uint8)
        result[mask] = image[mask]
        return result

    @staticmethod
    def _cutout(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        result = cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)
        result[:, :, 3] = mask.astype(np.uint8) * 255
        result[~mask, :3] = 0
        return result
