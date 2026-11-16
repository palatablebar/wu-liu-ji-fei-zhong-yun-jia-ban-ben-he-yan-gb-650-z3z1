"""M1 入口：运单页、采信触发、运单与隔离区查询。"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse

from app import config, store, web
from app.modules.m1_waybill import service
from app.modules.m3_quality import service as quality

router = APIRouter(tags=["waybills"])


@router.get("/waybills", response_class=HTMLResponse)
def page_waybills(request: Request):
    context = web.shell(request, active="waybills")
    run_id = context["run_id"]
    context.update({
        "waybills": service.rows_for(run_id) if run_id else [],
        "quarantine": quality.rows(run_id) if run_id else [],
        "distribution": quality.distribution(run_id) if run_id else [],
        "samples": {"waybills": config.SAMPLE_WAYBILLS,
                    "gb": config.SAMPLE_WAYBILLS_GB,
                    "trunc": config.SAMPLE_WAYBILLS_TRUNC},
    })
    return web.page("waybills.html", context)


@router.get("/api/waybills")
def api_waybills(run: str = ""):
    run_id = run or store.latest_run_id()
    return {
        "ok": True,
        "run_id": run_id,
        "counts": service.counts(run_id) if run_id else {},
        "rows": service.rows_for(run_id) if run_id else [],
    }


@router.post("/api/waybills/import")
async def api_import(file: UploadFile | None = File(default=None),
                     sample: str = Form(default=config.SAMPLE_WAYBILLS)):
    if file is not None and file.filename:
        raw = await file.read()
        name = file.filename
    else:
        name = sample
        result = service.import_sample(name)
        return {"ok": True, "result": result}
    result = service.import_bytes(raw, name)
    return {"ok": True, "result": result}
