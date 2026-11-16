"""原因码唯一来源：代码、中文标签、级别（block 进隔离区，info 只做标记）。"""

from __future__ import annotations

BLOCK = "block"
INFO = "info"

REASONS: dict[str, dict[str, str]] = {
    "BOM_STRIPPED": {"label": "首列带 BOM", "level": INFO},
    "ENCODING_FALLBACK": {"label": "非 UTF-8 编码回退", "level": INFO},
    "DUPLICATE_HEADER": {"label": "重复表头", "level": INFO},
    "ARITY_MISMATCH": {"label": "列数与表头不一致", "level": BLOCK},
    "TRUNCATED_TAIL": {"label": "尾行截断", "level": BLOCK},
    "MISSING_KEY": {"label": "关键字段为空", "level": BLOCK},
    "NUM_UNPARSEABLE": {"label": "数字无法解析", "level": BLOCK},
    "SENTINEL_VALUE": {"label": "空值哨兵", "level": BLOCK},
    "UNIT_UNKNOWN": {"label": "单位无法识别", "level": BLOCK},
    "UNIT_CONVERTED": {"label": "单位已换算", "level": INFO},
    "FULLWIDTH_NORMALIZED": {"label": "全角字符归一", "level": INFO},
    "ZERO_DIMENSION": {"label": "尺寸为 0", "level": BLOCK},
    "DIM_RANGE": {"label": "尺寸越界", "level": BLOCK},
    "DATE_UNPARSEABLE": {"label": "日期无法解析", "level": BLOCK},
    "TZ_MIXED": {"label": "时区写法混用", "level": INFO},
    "UNKNOWN_CARRIER": {"label": "承运商不存在", "level": BLOCK},
    "RATE_MISSING": {"label": "缺运价版本", "level": BLOCK},
    "RATE_OVERLAP": {"label": "版本生效区间重叠", "level": BLOCK},
    "RATE_STALE": {"label": "运价集版本陈旧", "level": BLOCK},
    "DUP_CONFLICT": {"label": "重复运单取值冲突", "level": BLOCK},
    "DUPLICATE_WAYBILL": {"label": "重复运单取值一致", "level": BLOCK},
    "MIN_CHARGE_APPLIED": {"label": "最低收费兜底", "level": INFO},
    "VOLUMETRIC_APPLIED": {"label": "体积重大于实重", "level": INFO},
    "ZONE_REMOTE": {"label": "偏远分区附加", "level": INFO},
}

CODES = tuple(REASONS)


def label(code: str) -> str:
    return REASONS.get(code, {}).get("label", code)


def level(code: str) -> str:
    return REASONS.get(code, {}).get("level", INFO)


def is_block(code: str) -> bool:
    return level(code) == BLOCK


def labels(codes) -> list[str]:
    return [f"{c} {label(c)}" for c in codes]


def sort_codes(codes) -> list[str]:
    """稳定排序：block 在前，其次按代码字母序。"""
    return sorted(set(codes), key=lambda c: (0 if is_block(c) else 1, c))
