"""M4 计费重：体积重、台阶进位、取大、来源标记。"""

from __future__ import annotations

from decimal import Decimal

from fixtures.expected import BILLABLE_TOTAL, VOLUMETRIC_HITS, WAYBILLS

from app.modules.m4_weights import billable, rounding, volumetric
from app.modules.m4_weights import service as weights


def test_volumetric_with_divisor_6000():
    value = volumetric.volumetric_kg(Decimal("40"), Decimal("30"), Decimal("25"), 6000)
    assert value == Decimal("5.000")
    assert billable.pick(Decimal("3.200"), value)[0] == Decimal("5.000")


def test_volumetric_rounds_to_three_decimals():
    assert volumetric.volumetric_kg(Decimal("10"), Decimal("10"), Decimal("10"), 6000) == Decimal("0.167")
    assert volumetric.volumetric_kg(Decimal("10"), Decimal("10"), Decimal("10"), 5000) == Decimal("0.200")


def test_zero_divisor_falls_back():
    assert volumetric.volumetric_kg(Decimal("10"), Decimal("10"), Decimal("10"), 0) == Decimal("0.167")


def test_ceil_to_half_kilogram():
    assert rounding.ceil_to_step(Decimal("12.800"), Decimal("0.5")) == Decimal("13.0")
    assert rounding.ceil_to_step(Decimal("20.833"), Decimal("0.5")) == Decimal("21.0")
    assert rounding.ceil_to_step(Decimal("5.000"), Decimal("0.5")) == Decimal("5.0")


def test_steps_zero_within_first_weight():
    assert rounding.steps_above(Decimal("1.000"), Decimal("1.000"), Decimal("0.5")) == 0
    assert rounding.steps_above(Decimal("0.500"), Decimal("1.000"), Decimal("0.5")) == 0
    assert rounding.steps_above(Decimal("2.000"), Decimal("1.000"), Decimal("0.5")) == 2


def test_pick_prefers_volumetric_and_tags_source():
    value, source = billable.pick(Decimal("1.200"), Decimal("1.800"))
    assert value == Decimal("1.800")
    assert source == billable.VOLUMETRIC
    assert billable.source_codes(source) == ["VOLUMETRIC_APPLIED"]
    assert billable.label(source) == "体积重"


def test_tie_counts_as_actual():
    value, source = billable.pick(Decimal("5.000"), Decimal("5.000"))
    assert value == Decimal("5.000")
    assert source == billable.TIE
    assert billable.source_codes(source) == []


def test_every_billable_matches_expected(pipeline):
    lines = {row["waybill_no"]: row for row in weights.lines(pipeline["run_id"])}
    for waybill_no, expected in WAYBILLS.items():
        assert lines[waybill_no]["actual_kg"] == expected["actual"], waybill_no
        assert lines[waybill_no]["volumetric_kg"] == expected["volume"], waybill_no
        assert lines[waybill_no]["billable_kg"] == expected["billable"], waybill_no
        assert int(lines[waybill_no]["steps"]) == expected["steps"], waybill_no


def test_summary_counts_and_total(pipeline):
    summary = weights.summary(pipeline["run_id"])
    assert summary["count"] == len(WAYBILLS)
    assert summary["volumetric_hits"] == VOLUMETRIC_HITS
    assert summary["actual_hits"] == len(WAYBILLS) - VOLUMETRIC_HITS
    assert summary["billable_total"] == BILLABLE_TOTAL
