"""计费重取大：实重与体积重比大小，并留下依据来源。"""

from __future__ import annotations

from decimal import Decimal

ACTUAL = "actual"
VOLUMETRIC = "volumetric"
TIE = "tie"
UNBILLED = "unbilled"

SOURCE_LABEL = {
    ACTUAL: "实重",
    VOLUMETRIC: "体积重",
    TIE: "实重",
    UNBILLED: "未计费",
}


def pick(actual_kg: Decimal, volumetric_kg: Decimal) -> tuple[Decimal, str]:
    if volumetric_kg > actual_kg:
        return volumetric_kg, VOLUMETRIC
    if volumetric_kg == actual_kg:
        return actual_kg, TIE
    return actual_kg, ACTUAL


def source_codes(source: str) -> list[str]:
    return ["VOLUMETRIC_APPLIED"] if source == VOLUMETRIC else []


def label(source: str) -> str:
    return SOURCE_LABEL.get(source, source)
