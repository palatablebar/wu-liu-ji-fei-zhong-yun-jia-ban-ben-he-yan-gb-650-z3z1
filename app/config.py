"""运行期常量：路径、编码回退链、单位表、量化刻度、规则版本。

单位表与哨兵清单只在本文件定义，其它模块一律导入，不允许各自复制一份。
"""

from __future__ import annotations

import os
from datetime import timedelta, timezone
from decimal import Decimal
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

SAMPLE_DIR = Path(os.environ.get("FREIGHTRATE_SAMPLE") or PROJECT_DIR / "sample_data")
DATA_DIR = Path(os.environ.get("FREIGHTRATE_DATA") or PROJECT_DIR / "data")
DB_PATH = Path(os.environ.get("FREIGHTRATE_DB") or DATA_DIR / "freightrate.db")

RULES_VERSION = os.environ.get("FREIGHTRATE_RULES") or "fr-2026.11.15-b1"
PROFILE = "step-500g"

# 编码回退链：先按 BOM 感知的 UTF-8，再裸 UTF-8，最后 GB18030
ENCODINGS = ("utf-8-sig", "utf-8", "gb18030")

# 空值哨兵：小写比较。空字符串另外单独判断，语义与哨兵不同
SENTINELS = frozenset({"", "-", "--", "/", "n/a", "na", "null", "none", "未知", "无", "空"})

WEIGHT_UNITS = {
    "kg": Decimal("1"),
    "公斤": Decimal("1"),
    "千克": Decimal("1"),
    "g": Decimal("0.001"),
    "克": Decimal("0.001"),
    "t": Decimal("1000"),
    "吨": Decimal("1000"),
}

DIM_UNITS = {
    "cm": Decimal("1"),
    "厘米": Decimal("1"),
    "m": Decimal("100"),
    "米": Decimal("100"),
    "mm": Decimal("0.1"),
    "毫米": Decimal("0.1"),
}

# 计费重进位台阶、金额与体积重的量化刻度
STEP_QUANT = Decimal("0.5")
MONEY_QUANT = Decimal("0.01")
VOLUME_QUANT = Decimal("0.001")
WEIGHT_QUANT = Decimal("0.001")

# 单边尺寸上限，超过视为结构异常
DIM_MAX_CM = Decimal("400")
DIM_MIN_CM = Decimal("0")

RATE_SET_VERSION = 3

REQUIRED_COLUMNS = (
    "waybill_no",
    "carrier",
    "service",
    "zone",
    "pickup_date",
    "weight",
    "weight_unit",
    "length",
    "width",
    "height",
    "dim_unit",
    "declared_value",
    "pieces",
)

# 表头别名：只做列名归一，不改列语义
HEADER_ALIASES = {
    "waybill": "waybill_no",
    "order_no": "waybill_no",
    "运单号": "waybill_no",
    "carrier_code": "carrier",
    "承运商": "carrier",
    "service_level": "service",
    "分区": "zone",
    "提货时间": "pickup_date",
    "重量": "weight",
    "重量单位": "weight_unit",
    "长": "length",
    "宽": "width",
    "高": "height",
    "尺寸单位": "dim_unit",
    "声明价值": "declared_value",
    "件数": "pieces",
}

CN_TZ = timezone(timedelta(hours=8))
DISPLAY_TZ = "Asia/Shanghai"

SAMPLE_RATES = "rate_cards.csv"
SAMPLE_RATES_OVERLAP = "rate_cards_overlap.csv"
SAMPLE_WAYBILLS = "waybills_dirty.csv"
SAMPLE_WAYBILLS_GB = "waybills_gb18030.csv"
SAMPLE_WAYBILLS_TRUNC = "waybills_truncated.csv"
