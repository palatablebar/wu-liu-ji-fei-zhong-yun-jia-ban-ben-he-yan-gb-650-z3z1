"""M4 编排：按运单逐行择版、算体积重、取大、进位，落库计费重行。"""

from __future__ import annotations

from decimal import Decimal

from app import manifest, store
from app.errors import DomainError
from app.modules.m2_rates import service as rates
from app.modules.m2_rates import version as rateversion
from app.modules.m4_weights import billable, rounding, volumetric


def compute_weights(run_id: str) -> dict:
    run = store.get_run(run_id)
    if not run:
        raise DomainError("RUN_NOT_FOUND", f"运行不存在：{run_id}", 404)
    rows = store.waybills(run_id)
    if not rows:
        raise DomainError("NO_ROWS", "该运行没有可计费的运单", 409)

    index_map = rates.index()
    lines: list[dict] = []
    unbilled = 0
    for row in rows:
        pickup = rateversion.parse_utc(row["pickup_utc"])
        card, codes = rates.select_card(index_map, row["carrier"], row["service"], row["zone"], pickup)
        if card is None:
            unbilled += 1
            lines.append({
                "waybill_no": row["waybill_no"],
                "version_id": "",
                "actual_kg": row["weight_kg"],
                "volumetric_kg": "0.000",
                "source": billable.UNBILLED,
                "billable_kg": "0.000",
                "steps": 0,
                "codes": ",".join(codes),
            })
            continue

        actual = Decimal(row["weight_kg"])
        volume = volumetric.volumetric_kg(
            Decimal(row["length_cm"]),
            Decimal(row["width_cm"]),
            Decimal(row["height_cm"]),
            int(card["volume_divisor"]),
        )
        raw, source = billable.pick(actual, volume)
        step = Decimal(card["step_weight_kg"])
        billable_kg = rounding.ceil_to_step(raw, step)
        steps = rounding.steps_above(billable_kg, Decimal(card["first_weight_kg"]), step)
        lines.append({
            "waybill_no": row["waybill_no"],
            "version_id": card["version_id"],
            "actual_kg": str(actual),
            "volumetric_kg": str(volume),
            "source": source,
            "billable_kg": str(billable_kg),
            "steps": steps,
            "codes": ",".join(billable.source_codes(source)),
        })

    store.replace_weight_lines(run_id, lines)
    now = manifest.utc_now_iso()
    store.add_stage(run_id, "weights", now)
    return {
        "run_id": run_id,
        "billed": len(lines) - unbilled,
        "unbilled": unbilled,
        "volumetric_hits": sum(1 for line in lines if line["source"] == billable.VOLUMETRIC),
        "steps_total": sum(int(line["steps"]) for line in lines),
        "rate_digest": rates.rate_digest(),
    }


def lines(run_id: str) -> list[dict]:
    return store.weight_lines(run_id)


def summary(run_id: str) -> dict:
    items = lines(run_id)
    return {
        "count": len(items),
        "billed": sum(1 for i in items if i["source"] != billable.UNBILLED),
        "unbilled": sum(1 for i in items if i["source"] == billable.UNBILLED),
        "volumetric_hits": sum(1 for i in items if i["source"] == billable.VOLUMETRIC),
        "actual_hits": sum(1 for i in items if i["source"] in (billable.ACTUAL, billable.TIE)),
        "billable_total": str(sum((Decimal(i["billable_kg"]) for i in items), Decimal("0.000"))),
    }
