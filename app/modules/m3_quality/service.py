"""M3 编排：隔离区查询、原因分布、证据 CSV、质量指标。"""

from __future__ import annotations

from app import store
from app.modules.m3_quality import metrics as metrics_calc
from app.modules.m3_quality import quarantine


def rows(run_id: str) -> list[dict]:
    return store.quarantine(run_id) if run_id else []


def distribution(run_id: str) -> list[dict]:
    return quarantine.distribution(rows(run_id))


def csv_text(run_id: str) -> str:
    return quarantine.csv_text(rows(run_id))


def metrics(run_id: str) -> dict:
    run = store.get_run(run_id) or {}
    items = rows(run_id)
    dist = quarantine.distribution(items)
    return metrics_calc.summary(
        int(run.get("rows_in") or 0),
        int(run.get("rows_ok") or 0),
        items,
        dist,
    )


def codes(run_id: str) -> list[str]:
    return quarantine.codes_of(rows(run_id))
