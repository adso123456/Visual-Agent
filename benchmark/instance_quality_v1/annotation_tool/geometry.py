import math


def screen_to_original(point, zoom, offset):
    if not isinstance(zoom, (int, float)) or not math.isfinite(zoom) or zoom <= 0:
        raise ValueError("zoom must be a positive finite number")
    return [(point[0] - offset[0]) / zoom, (point[1] - offset[1]) / zoom]


def original_to_screen(point, zoom, offset):
    if not isinstance(zoom, (int, float)) or not math.isfinite(zoom) or zoom <= 0:
        raise ValueError("zoom must be a positive finite number")
    return [point[0] * zoom + offset[0], point[1] * zoom + offset[1]]


def normalize_clip_bbox(start, end, width, height):
    values = [*start, *end]
    if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in values):
        raise ValueError("bbox coordinates must be finite")
    x1, x2 = sorted((max(0, min(width, start[0])), max(0, min(width, end[0]))))
    y1, y2 = sorted((max(0, min(height, start[1])), max(0, min(height, end[1]))))
    if x2 <= x1 or y2 <= y1:
        raise ValueError("bbox must have positive area")
    return [round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2)]


def move_bbox(box, dx, dy, width, height):
    box_width, box_height = box[2] - box[0], box[3] - box[1]
    x1 = min(max(0, box[0] + dx), width - box_width)
    y1 = min(max(0, box[1] + dy), height - box_height)
    return [round(x1, 2), round(y1, 2), round(x1 + box_width, 2), round(y1 + box_height, 2)]

