import cv2
import numpy as np


ACTION_TYPES = {"highlight", "outline", "blur_target", "dim_background", "cutout"}


class ImageActionExecutor:
    def execute(self, image: np.ndarray, masks: list[np.ndarray], action_type: str) -> np.ndarray:
        if action_type not in ACTION_TYPES:
            raise ValueError(f"不支持的图片操作：{action_type}")
        if not masks:
            return image.copy()

        combined_mask = np.logical_or.reduce(masks)
        if action_type == "highlight":
            return self._highlight(image, combined_mask)
        if action_type == "outline":
            return self._outline(image, combined_mask)
        if action_type == "blur_target":
            return self._blur_target(image, combined_mask)
        if action_type == "dim_background":
            return self._dim_background(image, combined_mask)
        return self._cutout(image, combined_mask)

    @staticmethod
    def _highlight(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        result = image.copy()
        red = np.zeros_like(image)
        red[:, :] = (0, 0, 255)
        blended = cv2.addWeighted(image, 0.55, red, 0.45, 0)
        result[mask] = blended[mask]
        return result

    @staticmethod
    def _outline(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        result = image.copy()
        binary_mask = mask.astype(np.uint8) * 255
        contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(result, contours, -1, (0, 0, 255), 2)
        return result

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
