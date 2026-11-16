"""构造小份 CSV 的辅助函数，跟随主样例的列契约。"""

from __future__ import annotations

HEADER = (
    "waybill_no,carrier,service,zone,pickup_date,weight,weight_unit,"
    "length,width,height,dim_unit,declared_value,pieces"
)

DEFAULTS = {
    "carrier": "SF",
    "service": "standard",
    "zone": "Z1",
    "pickup": "2026-04-05T10:00:00+08:00",
    "weight": "1",
    "weight_unit": "kg",
    "length": "10",
    "width": "10",
    "height": "10",
    "dim_unit": "cm",
    "declared": "0",
    "pieces": "1",
}


def row(waybill_no: str, **overrides) -> str:
    data = {**DEFAULTS, **overrides}
    return ",".join([
        waybill_no,
        data["carrier"],
        data["service"],
        data["zone"],
        data["pickup"],
        data["weight"],
        data["weight_unit"],
        data["length"],
        data["width"],
        data["height"],
        data["dim_unit"],
        data["declared"],
        data["pieces"],
    ])


def csv_text(rows: list[str], header: str = HEADER, newline: str = "\n") -> str:
    return newline.join([header, *rows])


def csv_bytes(rows: list[str], header: str = HEADER, newline: str = "\n") -> bytes:
    return csv_text(rows, header, newline).encode("utf-8")
