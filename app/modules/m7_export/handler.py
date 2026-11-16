"""M7 入口：导出页、账单 CSV、证据 CSV、运行清单。"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse

from app import store, web
from app.modules.m7_export import service

router = APIRouter(tags=["export"])


@router.get("/export", response_class=HTMLResponse)
def page_export(request: Request):
    context = web.shell(request, active="export")
    run_id = context["run_id"]
    context.update({"overview": service.overview(run_id) if run_id else {}})
    return web.page("export.html", context)


@router.get("/api/export/invoice.csv")
def api_invoice(run: str = ""):
    run_id = run or store.latest_run_id()
    return Response(
        content=service.invoice_csv(run_id),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="invoice.csv"'},
    )


@router.get("/api/export/evidence.csv")
def api_evidence(run: str = ""):
    run_id = run or store.latest_run_id()
    return Response(
        content=service.evidence_csv(run_id),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="evidence.csv"'},
    )


@router.get("/api/export/manifest.json")
def api_manifest(run: str = ""):
    run_id = run or store.latest_run_id()
    return Response(
        content=service.manifest_json(run_id),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="manifest.json"'},
    )
