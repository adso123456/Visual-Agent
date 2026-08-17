"""Assemble the vision-model candidate review into the official review document.

来源：对 24 张 Test 图片的 122 个 raw candidate 逐一进行视觉复核
（vision_glance 读取 render_review_sheets 生成的 review card），
按契约六分类（VALID/PARTIAL/DUPLICATE/MIXED/FALSE/AMBIGUOUS）给出分类。

本脚本：
1. 读取 raw candidates 与 frozen GT；
2. 读取逐候选视觉复核文件 manual_visual_audit_v1.json；
3. 分类与 GT 映射均以视觉判断为准，IoU/containment 不参与自动分类或映射；
4. 校验 image/candidate 集合与 mapped GT ID；
5. 通过 schema 校验后写入 reviews/grounding_dino_base.json。

注意：本文件是「assistant 视觉复核草稿」，正式定稿仍应在 annotation_tool review
界面由人工确认（与 GT 的 assistant_draft -> human review 流程一致）。
"""

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# 旧视觉草稿，仅保留为诊断历史；main() 不再读取，禁止用于自动映射。
# 当前草稿来源为 reviews/manual_visual_audit_v1.json。
# 格式：image_id -> {candidate_id: {"class": ..., "completeness": ..., "notes": ...}}
# mapped GT 不在此处给出，统一由 best-IoU 确定性锚定。
# ---------------------------------------------------------------------------
VISION_CLASS: dict[str, dict[str, dict[str, str]]] = {
    "TST_SPARSE_001": {
        "C001": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色粗框完整覆盖前景白衣人物全身，无遮挡或截断。"},
        "C002": {"class": "PARTIAL_INSTANCE", "completeness": "USABLE_PARTIAL", "notes": "仅覆盖人物躯干至大腿，未包含头部与左臂，属部分检测。"},
        "C003": {"class": "PARTIAL_INSTANCE", "completeness": "USABLE_PARTIAL", "notes": "聚焦背景人物上半身及腿部，未含完整身体，属部分检测。"},
        "C004": {"class": "FALSE_DETECTION", "completeness": "UNUSABLE_PARTIAL", "notes": "框内仅为模糊背景人群局部，无人体显著特征，不构成有效实例。"},
    },
    "TST_SPARSE_002": {
        "C001": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整覆盖一只大型犬，无遮挡，姿态清晰。"},
    },
    "TST_SPARSE_003": {
        "C001": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色粗框完整覆盖一艘大型帆船（GT I01），无遮挡、无截断。"},
        "C002": {"class": "PARTIAL_INSTANCE", "completeness": "USABLE_PARTIAL", "notes": "黄色框仅覆盖小艇主体，船头/船尾略有截断；GT 仅收录 I01 主帆船。"},
        "C003": {"class": "PARTIAL_INSTANCE", "completeness": "USABLE_PARTIAL", "notes": "黄色框覆盖右侧快艇大部分，船尾被遮挡或截断；GT 未收录该实例。"},
        "C004": {"class": "PARTIAL_INSTANCE", "completeness": "USABLE_PARTIAL", "notes": "黄色小框仅包含小艇前端一小段，明显截断；GT 未收录。"},
        "C005": {"class": "DUPLICATE_INSTANCE", "completeness": "COMPLETE", "notes": "与 C001 重叠覆盖同一艘大帆船（I01），C001 为更优完整检测。"},
        "C006": {"class": "AMBIGUOUS", "completeness": "USABLE_PARTIAL", "notes": "黄色框完整包围白色快艇，为独立真实船只，但 GT 未收录，存在 GT 覆盖缺口。"},
    },
    "TST_ADJACENT_001": {
        "C001": {"class": "PARTIAL_INSTANCE", "completeness": "USABLE_PARTIAL", "notes": "黄色框覆盖左侧人物部分身体（躯干及腿部），未包含完整人物。"},
        "C002": {"class": "PARTIAL_INSTANCE", "completeness": "USABLE_PARTIAL", "notes": "黄色框覆盖右侧人物部分身体，主体可见，属可用的部分检测。"},
    },
    "TST_ADJACENT_002": {
        "C001": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "完整覆盖左侧人物，框内仅一人，姿态清晰。"},
        "C002": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "完整覆盖中间人物，框内仅一人，无截断。"},
        "C003": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "完整覆盖右侧人物，可见部分完整，无重叠。"},
    },
    "TST_ADJACENT_003": {
        "C001": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整覆盖左侧狗（GT I01），无其他物体。"},
        "C002": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整覆盖右侧狗（GT I02），姿态清晰，无遮挡。"},
    },
    "TST_DENSE_001": {
        "C001": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色粗框完整覆盖戴彩色羽毛帽的单人，主体清晰完整。"},
        "C002": {"class": "FALSE_DETECTION", "completeness": "UNUSABLE_PARTIAL", "notes": "仅截取右侧红衣人肩臂部分，无完整人脸或躯干，非独立个体。"},
        "C003": {"class": "FALSE_DETECTION", "completeness": "UNUSABLE_PARTIAL", "notes": "框内为模糊红衣人群局部，无法辨识为单一人物。"},
        "C004": {"class": "DUPLICATE_INSTANCE", "completeness": "USABLE_PARTIAL", "notes": "仅覆盖主人员头部侧影，C001 已更完整覆盖该人。"},
    },
    "TST_DENSE_002": {
        "C001": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整覆盖前景穿格子衫女性（GT I15）。"},
        "C002": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整覆盖右侧穿深色上衣女性（GT I16）。"},
        "C003": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整覆盖中央前景女性（GT I07）。"},
        "C004": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整覆盖左侧红上衣人物（GT I01）。"},
        "C005": {"class": "AMBIGUOUS", "completeness": "USABLE_PARTIAL", "notes": "仅截取远处帐篷前一人上半身，无对应 GT 框，属 GT 漏标区域。"},
        "C006": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整覆盖白衬衫人物（GT I03）。"},
        "C007": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整包裹红衣人物（GT I13）。"},
        "C008": {"class": "DUPLICATE_INSTANCE", "completeness": "COMPLETE", "notes": "覆盖白衬衫人物但比 C006 更宽，C006 已更优覆盖。"},
        "C009": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整包含长发人物（GT I14）。"},
        "C010": {"class": "DUPLICATE_INSTANCE", "completeness": "COMPLETE", "notes": "与 C006 同覆盖白衬衫人物（GT I03），属重复检测。"},
        "C011": {"class": "MIXED_INSTANCE", "completeness": "COMPLETE", "notes": "黄框覆盖至少两名真实人物，属多人混检。"},
        "C012": {"class": "MIXED_INSTANCE", "completeness": "COMPLETE", "notes": "黄框横跨多人群体，包含多个 GT 实例，明显混检。"},
        "C013": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框覆盖中央深色衣着人物（GT I10）。"},
    },
    "TST_DENSE_003": {
        "C001": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整覆盖左侧站立男性（GT I01）。"},
        "C002": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整覆盖右侧站立男性（GT I04）。"},
        "C003": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整覆盖坐姿人物（GT I07）。"},
        "C004": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整覆盖坐姿人物（GT I05）。"},
        "C005": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整覆盖坐姿人物（GT I06）。"},
        "C006": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色粗框完整覆盖站立人物（GT I02）。"},
        "C007": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色粗框精准框住站立人物（GT I03），全身可见。"},
    },
    "TST_SMALL_001": {
        "C001": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整覆盖左侧卷发女性（GT I01）。"},
        "C002": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框准确框住戴墨镜女性侧脸（GT I02）。"},
        "C003": {"class": "DUPLICATE_INSTANCE", "completeness": "COMPLETE", "notes": "与 C004 重叠覆盖同一男性（GT I03），C004 更紧凑。"},
        "C004": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框紧贴中间男性面部（GT I03），完整、无干扰。"},
        "C005": {"class": "DUPLICATE_INSTANCE", "completeness": "COMPLETE", "notes": "与 C001 重复框选同一女性（GT I01），位置偏移但主体相同。"},
    },
    "TST_SMALL_002": {
        "C001": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色粗框完整覆盖一辆银色轿车（GT I01），无遮挡或截断。"},
    },
    "TST_SMALL_003": {
        "C001": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整覆盖渔船（GT I01），无遮挡。"},
        "C002": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框精确包围白色帆船（GT I02）。"},
        "C003": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整包含白船（GT I03），无截断。"},
        "C004": {"class": "PARTIAL_INSTANCE", "completeness": "USABLE_PARTIAL", "notes": "仅覆盖船前半部，船尾被截断，但主体可辨识（GT I04）。"},
        "C005": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整框住帆船（GT I05）。"},
    },
    "TST_OCCLUSION_001": {
        "C001": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色粗框完整覆盖左侧水手（GT I01），无遮挡。"},
        "C002": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色粗框完整覆盖中间水手（GT I02），全身可见。"},
        "C003": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色粗框完整覆盖右侧水手（GT I03），面部与身体清晰。"},
        "C004": {"class": "AMBIGUOUS", "completeness": "USABLE_PARTIAL", "notes": "小框内为站立人员，但无对应 GT 框，疑似背景人员，GT 缺失。"},
        "C005": {"class": "DUPLICATE_INSTANCE", "completeness": "USABLE_PARTIAL", "notes": "小框落在 I03 区域内，C003 已更完整覆盖，属重复检测。"},
        "C006": {"class": "AMBIGUOUS", "completeness": "USABLE_PARTIAL", "notes": "框内为站立人员，无对应 GT 框，疑似背景人员。"},
        "C007": {"class": "DUPLICATE_INSTANCE", "completeness": "USABLE_PARTIAL", "notes": "小框落在 I03 区域内，C003 为更优候选，属重复检测。"},
        "C008": {"class": "AMBIGUOUS", "completeness": "USABLE_PARTIAL", "notes": "左侧小框，位置在 GT I01 之外，无对应 GT，属 GT 覆盖缺口。"},
        "C009": {"class": "MIXED_INSTANCE", "completeness": "COMPLETE", "notes": "框内含至少两人，属多人混合检测。"},
        "C010": {"class": "AMBIGUOUS", "completeness": "USABLE_PARTIAL", "notes": "小框位于 I02 顶部上方，无对应 GT，属 GT 覆盖缺口。"},
        "C011": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整覆盖前景水兵（GT I02），姿态清晰。"},
        "C012": {"class": "AMBIGUOUS", "completeness": "USABLE_PARTIAL", "notes": "小框覆盖水兵头部区域，无对应 GT 锚定，属覆盖缺口。"},
        "C013": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框精准框住左侧站立水兵（GT I01），全身可见。"},
        "C014": {"class": "AMBIGUOUS", "completeness": "USABLE_PARTIAL", "notes": "仅框出一人下半身，上半身被遮挡；无对应 GT 框，疑似漏标。"},
        "C015": {"class": "DUPLICATE_INSTANCE", "completeness": "COMPLETE", "notes": "与 C003 重叠覆盖同一人（I03），C003 更居中完整。"},
        "C016": {"class": "DUPLICATE_INSTANCE", "completeness": "COMPLETE", "notes": "覆盖中间水手（I02），C011 已更完整覆盖。"},
        "C017": {"class": "PARTIAL_INSTANCE", "completeness": "USABLE_PARTIAL", "notes": "仅覆盖人物上半身（头至腰），下半身被遮挡（GT I03 区域）。"},
        "C018": {"class": "PARTIAL_INSTANCE", "completeness": "USABLE_PARTIAL", "notes": "覆盖人物躯干与头部，腿部被遮挡（GT I01 区域）。"},
        "C019": {"class": "AMBIGUOUS", "completeness": "USABLE_PARTIAL", "notes": "小框覆盖水手侧脸+肩部，无对应 GT 框，属 GT 遗漏。"},
        "C020": {"class": "FALSE_DETECTION", "completeness": "UNUSABLE_PARTIAL", "notes": "框内仅含模糊背景布料/结构，无人体特征，非真实人物。"},
        "C021": {"class": "PARTIAL_INSTANCE", "completeness": "USABLE_PARTIAL", "notes": "小框覆盖中间水手头部区域，清晰但仅为局部（GT I02 区域）。"},
    },
    "TST_OCCLUSION_002": {
        "C001": {"class": "MIXED_INSTANCE", "completeness": "COMPLETE", "notes": "黄框同时包含两人，属多人混检。"},
        "C002": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄框精准覆盖行人全身（GT I02），无其他干扰。"},
        "C003": {"class": "DUPLICATE_INSTANCE", "completeness": "COMPLETE", "notes": "与 C001 重叠且更窄，GT 已被覆盖，属重复检测。"},
        "C004": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄框紧贴行人（GT I04），完整覆盖单人。"},
        "C005": {"class": "DUPLICATE_INSTANCE", "completeness": "COMPLETE", "notes": "紧邻 C004，同覆盖一人（GT I04），属重复检测。"},
    },
    "TST_OCCLUSION_003": {
        "C001": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色粗框完整覆盖右侧前景行人（GT I01），单人且无遮挡干扰。"},
        "C002": {"class": "MIXED_INSTANCE", "completeness": "COMPLETE", "notes": "框内含 2 个真实人物，属混合检测。"},
        "C003": {"class": "PARTIAL_INSTANCE", "completeness": "USABLE_PARTIAL", "notes": "仅覆盖推婴儿车者上半身，下半身被截断（GT I02 区域）。"},
        "C004": {"class": "DUPLICATE_INSTANCE", "completeness": "COMPLETE", "notes": "与 C003 重叠，同覆盖推婴儿车者（GT I02），C003 更优。"},
        "C005": {"class": "DUPLICATE_INSTANCE", "completeness": "COMPLETE", "notes": "再次覆盖推婴儿车者（GT I02），属冗余检测。"},
        "C006": {"class": "PARTIAL_INSTANCE", "completeness": "USABLE_PARTIAL", "notes": "仅覆盖前景右侧人物上半身（GT I01 区域），属部分遮挡。"},
        "C007": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整包含推婴儿车者（GT I02），从头到脚无截断。"},
        "C008": {"class": "PARTIAL_INSTANCE", "completeness": "USABLE_PARTIAL", "notes": "覆盖穿红衣行人上半身（GT I03 区域），脚部被裁切。"},
    },
    "TST_SCALE_001": {
        "C001": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整覆盖前景左侧渔船（GT I01）。"},
        "C002": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整包裹前景右侧渔船（GT I02）。"},
        "C003": {"class": "PARTIAL_INSTANCE", "completeness": "USABLE_PARTIAL", "notes": "仅截取中景船只局部；GT 未收录该实例。"},
        "C004": {"class": "DUPLICATE_INSTANCE", "completeness": "COMPLETE", "notes": "与 C002 重叠同覆盖 I02 船只，C002 更紧致准确。"},
        "C005": {"class": "DUPLICATE_INSTANCE", "completeness": "COMPLETE", "notes": "与 C001 高度重叠同覆盖 I01 船只，C001 更优。"},
    },
    "TST_SCALE_002": {
        "C001": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整覆盖左侧站立者（GT I01）。"},
        "C002": {"class": "MIXED_INSTANCE", "completeness": "COMPLETE", "notes": "框内含至少两人，属多人混检。"},
        "C003": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框准确框住穿黑白格纹披风者（GT I04）。"},
        "C004": {"class": "FALSE_DETECTION", "completeness": "UNUSABLE_PARTIAL", "notes": "仅框出单手比 V 手势，无完整人体。"},
        "C005": {"class": "PARTIAL_INSTANCE", "completeness": "USABLE_PARTIAL", "notes": "框出人物后脑勺部分（GT I05 区域），属可用局部。"},
        "C006": {"class": "PARTIAL_INSTANCE", "completeness": "USABLE_PARTIAL", "notes": "仅覆盖一人后脑勺，无完整躯干；GT 未收录该区域。"},
        "C007": {"class": "MIXED_INSTANCE", "completeness": "COMPLETE", "notes": "黄框同时包含两人，属混合检测。"},
        "C008": {"class": "DUPLICATE_INSTANCE", "completeness": "COMPLETE", "notes": "与 C007 重叠同覆盖一人（GT I03 区域），已被更好候选覆盖。"},
        "C009": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "清晰覆盖白衣背影完整上半身（GT I02）。"},
    },
    "TST_SCALE_003": {
        "C001": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整覆盖一辆灰色轿车（GT I01）。"},
        "C002": {"class": "PARTIAL_INSTANCE", "completeness": "USABLE_PARTIAL", "notes": "覆盖黑色车主体，车尾被遮挡/截断（GT I02 区域）。"},
        "C003": {"class": "FALSE_DETECTION", "completeness": "UNUSABLE_PARTIAL", "notes": "框内仅见模糊植被与墙体，无可见车辆。"},
        "C004": {"class": "DUPLICATE_INSTANCE", "completeness": "COMPLETE", "notes": "与 C002 同指向 GT I02（黑色车），C002 已更完整覆盖。"},
        "C005": {"class": "PARTIAL_INSTANCE", "completeness": "USABLE_PARTIAL", "notes": "覆盖红色车前部（GT I04 区域），车尾被遮挡。"},
        "C006": {"class": "MIXED_INSTANCE", "completeness": "COMPLETE", "notes": "框内包含多辆真实汽车，属多实例混检。"},
    },
    "TST_INTERFERENCE_001": {
        "C001": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色粗框完整覆盖手持黑伞（GT I01），伞体完整可见。"},
    },
    "TST_INTERFERENCE_002": {
        "C001": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整覆盖撑开的红色雨伞（GT I01），无遮挡或截断。"},
    },
    "TST_INTERFERENCE_003": {
        "C001": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整覆盖一辆白色轿车（GT I01）。"},
        "C002": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框准确包围一辆深色轿车（GT I02），整车可见。"},
        "C003": {"class": "PARTIAL_INSTANCE", "completeness": "USABLE_PARTIAL", "notes": "仅覆盖银色轿车前半部分（GT I03 区域），后部被遮挡。"},
        "C004": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整框出一辆深色轿车（GT I04），清晰可辨。"},
        "C005": {"class": "MIXED_INSTANCE", "completeness": "COMPLETE", "notes": "框内含两辆车，属多车混检。"},
        "C006": {"class": "PARTIAL_INSTANCE", "completeness": "USABLE_PARTIAL", "notes": "仅覆盖红色车前部（GT I01 区域），未含完整车身。"},
        "C007": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整包围银色轿车（GT I02），无遮挡。"},
        "C008": {"class": "DUPLICATE_INSTANCE", "completeness": "COMPLETE", "notes": "与 C009 重叠覆盖同一红色车（GT I03），C009 更紧致。"},
        "C009": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框紧密完整包围红色车（GT I03）。"},
        "C010": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色框完整覆盖右侧白色车（GT I04），边界清晰。"},
    },
    "TST_DOMAIN_001": {
        "C001": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色粗框完整覆盖一台挖掘机（GT I01），无遮挡。"},
    },
    "TST_DOMAIN_002": {
        "C001": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色粗框完整覆盖木制闸门结构（GT I01）。"},
    },
    "TST_DOMAIN_003": {
        "C001": {"class": "VALID_INSTANCE", "completeness": "COMPLETE", "notes": "黄色粗框完整覆盖闸门结构（GT I01），含立柱、横梁及栅栏。"},
    },
}


def _iou(left, right):
    x1, y1 = max(left[0], right[0]), max(left[1], right[1])
    x2, y2 = min(left[2], right[2]), min(left[3], right[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    union = (left[2] - left[0]) * (left[3] - left[1]) + (right[2] - right[0]) * (right[3] - right[1]) - intersection
    return 0.0 if union <= 0 else intersection / union


def _containment(candidate, gt):
    """candidate 落在 gt 内的比例（candidate 面积中属于该 GT 的比例）。"""
    x1, y1 = max(candidate[0], gt[0]), max(candidate[1], gt[1])
    x2, y2 = min(candidate[2], gt[2]), min(candidate[3], gt[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    candidate_area = (candidate[2] - candidate[0]) * (candidate[3] - candidate[1])
    return 0.0 if candidate_area <= 0 else intersection / candidate_area


def _anchor(candidate, gt_instances):
    """返回 (mapped_gt, anchor_score)：anchor_score = max(IoU, containment)。
    小框完全落在大 GT 实例内时 containment 接近 1，适合把局部框判为 PARTIAL。"""
    best_id, best_score = None, 0.0
    for gt in gt_instances:
        iou = _iou(candidate["bbox"], gt["bbox"])
        containment = _containment(candidate["bbox"], gt["bbox"])
        score = max(iou, containment)
        if score > best_score:
            best_id, best_score = gt["instance_id"], score
    return best_id, best_score


def main() -> None:
    raw = json.loads((ROOT / "runs" / "grounding_dino_base" / "candidates.json").read_text(encoding="utf-8"))
    gt = json.loads((ROOT / "annotations" / "ground_truth.json").read_text(encoding="utf-8"))
    gt_by = {item["image_id"]: item for item in gt["images"]}
    audit = json.loads((ROOT / "reviews" / "manual_visual_audit_v1.json").read_text(encoding="utf-8"))
    audit_by = {item["image_id"]: item for item in audit["images"]}

    document = {
        "benchmark_version": audit["benchmark_version"],
        "review_source": audit["review_source"],
        "warning": audit["warning"],
        "images": [],
    }
    for row in raw["images"]:
        image_id = row["image_id"]
        gt_ids = {item["instance_id"] for item in gt_by[image_id]["instances"]}
        reviews = audit_by[image_id]["candidates"]
        raw_ids = [item["id"] for item in row["candidates"]]
        review_ids = [item["candidate_id"] for item in reviews]
        if raw_ids != review_ids:
            raise RuntimeError(
                f"manual visual review mismatch for {image_id}: raw={raw_ids}, review={review_ids}"
            )
        for review in reviews:
            mapped_id = review["mapped_gt_instance_id"]
            if mapped_id is not None and mapped_id not in gt_ids:
                raise RuntimeError(f"manual visual review maps missing GT: {image_id}/{review['candidate_id']}/{mapped_id}")
        document["images"].append({
            "image_id": image_id,
            "review_status": "IN_PROGRESS",
            "updated_at": None,
            "reviewed_by": "codex_manual_visual_audit",
            "candidates": reviews,
        })
    out_path = ROOT / "reviews" / "grounding_dino_base.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")
    print(f"wrote {out_path}")
    print("images:", len(document["images"]), "candidates:", sum(len(i["candidates"]) for i in document["images"]))
    classes = Counter(item["classification"] for entry in document["images"] for item in entry["candidates"])
    print("classification:", dict(classes))
    unmapped = [(entry["image_id"], item["candidate_id"])
                for entry in document["images"] for item in entry["candidates"]
                if item["classification"] in {"VALID_INSTANCE", "PARTIAL_INSTANCE", "DUPLICATE_INSTANCE"}
                and item["mapped_gt_instance_id"] is None]
    print("instance-class without mapped GT:", unmapped)


if __name__ == "__main__":
    main()
