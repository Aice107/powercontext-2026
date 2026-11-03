"""数值规则：只做"事实计算"，不做与玩法相关的叙事决策。

边界（对应运行说明里的分工）：
- 本模块只把"事件 + 严重度"换算成仇值增量，并把原始数值返回给 Dify；
- 档位（tier）与反应分支由 Dify 的 IF/ELSE 决定，不在后端实现。
"""

from __future__ import annotations

ACTION_TYPES = {
    "drink": {"label": "酒水", "base": 2},
    "food": {"label": "吃食", "base": 2},
    "property": {"label": "财物", "base": 3},
    "hygiene": {"label": "卫生", "base": 3},
    "noise": {"label": "扰民", "base": 2},
    "guest": {"label": "客人", "base": 4},
    "violence": {"label": "动手", "base": 5},
    "kindness": {"label": "善举", "base": -1},
    "other": {"label": "其它", "base": 1},
}

MAX_GRUDGE = 100
REPEAT_BONUS_PER = 2      # 同类事件"屡教不改"加成
REPEAT_BONUS_CAP = 3      # 最多累计 3 次加成
KINDNESS_MULTIPLIER = 8   # 善举降仇值倍率


def clamp_grudge(v: int) -> int:
    return max(0, min(MAX_GRUDGE, int(v)))


def grudge_delta(severity: int, repeat_cnt: int) -> int:
    """事件对仇值的增量。

    severity >= 1：severity*6 + min(repeat_cnt,3)*2
    severity <= -1：severity*8（负值，降仇）
    severity == 0：0（闲聊，不记账）
    """
    if severity >= 1:
        bonus = min(max(repeat_cnt, 0), REPEAT_BONUS_CAP) * REPEAT_BONUS_PER
        return severity * 6 + bonus
    if severity <= -1:
        return severity * KINDNESS_MULTIPLIER
    return 0


def tier_of(grudge: int) -> int:
    """参考映射（Dify 内用 IF/ELSE 复现，此处仅供样例与自测对照）。"""
    if grudge >= 80:
        return 4
    if grudge >= 60:
        return 3
    if grudge >= 40:
        return 2
    if grudge >= 20:
        return 1
    return 0


TIER_LABELS = {0: "和善", 1: "戒备", 2: "冷脸", 3: "报复", 4: "逐客"}
