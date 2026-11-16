"""M3 入口：隔离区查询与证据 CSV。"""

from __future__ import annotations

from fastapi import APIRouter, Response

from app import store
from app.modules.m3_quality import service

router = APIRouter(tags=["quality"])


@router.get("/api/quarantine")
def api_quarantine(run: str = ""):
    run_id = run or store.latest_run_id()
    return {
        "ok": True,
        "run_id": run_id,
        "rows": service.rows(run_id),
        "distribution": service.distribution(run_id),
        "metrics": service.metrics(run_id),
    }


@router.get("/api/quarantine.csv")
def api_quarantine_csv(run: str = ""):
    run_id = run or store.latest_run_id()
    body = service.csv_text(run_id)
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="quarantine.csv"'},
    )
