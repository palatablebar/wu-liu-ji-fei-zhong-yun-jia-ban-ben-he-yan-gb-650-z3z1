"""样例脏运单的确定性期望值。数值都由运价表与规则手工复算过。"""

HEADER = (
    "waybill_no,carrier,service,zone,pickup_date,weight,weight_unit,"
    "length,width,height,dim_unit,declared_value,pieces"
)

ROWS_IN = 27
ROWS_OK = 15
ROWS_QUARANTINED = 12
DUPLICATE_HEADERS = 1
SEGMENTS = 2

AMOUNT_TOTAL = "1521.04"
PARTS = {
    "base": "244.82",
    "step": "1104.48",
    "remote": "16.50",
    "fuel": "119.24",
    "insurance": "36.00",
}

# 每一票的实重、体积重、计费重、段数与应收
WAYBILLS = {
    "WB-1001": {"actual": "3.200", "volume": "5.000", "billable": "5.000", "steps": 8, "total": "42.67"},
    "WB-1002": {"actual": "0.800", "volume": "0.167", "billable": "1.000", "steps": 0, "total": "20.62"},
    "WB-1003": {"actual": "2.500", "volume": "12.000", "billable": "12.000", "steps": 22, "total": "108.74"},
    "WB-1004": {"actual": "12.500", "volume": "16.000", "billable": "16.000", "steps": 30, "total": "112.97"},
    "WB-1005": {"actual": "5.200", "volume": "72.000", "billable": "72.000", "steps": 142, "total": "697.05"},
    "WB-1006": {"actual": "1.200", "volume": "1.800", "billable": "2.000", "steps": 2, "total": "23.05"},
    "WB-1011": {"actual": "2.000", "volume": "1.333", "billable": "2.000", "steps": 2, "total": "19.44"},
    "WB-1012": {"actual": "1.000", "volume": "0.167", "billable": "1.000", "steps": 0, "total": "20.62"},
    "WB-1013": {"actual": "1.000", "volume": "0.167", "billable": "1.000", "steps": 0, "total": "19.44"},
    "WB-1015": {"actual": "3.000", "volume": "12.800", "billable": "13.000", "steps": 24, "total": "181.92"},
    "WB-1016": {"actual": "4.000", "volume": "20.833", "billable": "21.000", "steps": 40, "total": "156.24"},
    "WB-1017": {"actual": "3.200", "volume": "5.000", "billable": "5.000", "steps": 8, "total": "40.37"},
    "WB-1018": {"actual": "3.200", "volume": "5.000", "billable": "5.000", "steps": 8, "total": "36.67"},
    "WB-1019": {"actual": "2.000", "volume": "1.333", "billable": "2.000", "steps": 2, "total": "20.62"},
    "WB-1020": {"actual": "1.000", "volume": "0.167", "billable": "1.000", "steps": 0, "total": "20.62"},
}

BILLABLE_TOTAL = "159.000"
VOLUMETRIC_HITS = 9
ACTUAL_HITS = 6

QUARANTINE_CODES = [
    "ARITY_MISMATCH",
    "DATE_UNPARSEABLE",
    "DIM_RANGE",
    "DUP_CONFLICT",
    "NUM_UNPARSEABLE",
    "RATE_MISSING",
    "SENTINEL_VALUE",
    "TRUNCATED_TAIL",
    "UNIT_UNKNOWN",
    "UNKNOWN_CARRIER",
    "ZERO_DIMENSION",
]

VERSION_WINDOWS = {
    "v1": ("2026-01-01T00:00:00Z", "2026-04-01T00:00:00Z"),
    "v2": ("2026-04-01T00:00:00Z", "2026-07-01T00:00:00Z"),
}

RATE_CARD_ROWS = 38
RATE_KEYS = 19
RATE_SET_VERSION = 3
