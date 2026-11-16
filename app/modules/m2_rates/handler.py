"""M2 入口：运价手册页、运价查询、运价文件校验与替换。"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse

from app import config, store, web
from app.modules.m2_rates import service

router = APIRouter(tags=["rates"])


@router.get("/", response_class=HTMLResponse)
def page_index(request: Request):
    context = web.shell(request, active="rates")
    context.update({
        "coverage": service.coverage(),
        "overlaps": service.overlaps(),
        "rate_set_version": store.max_rate_set_version(),
        "card_count": len(service.cards()),
        "samples": service.sample_names(),
    })
    return web.page("index.html", context)


@router.get("/api/rates")
def api_rates():
    return {
        "ok": True,
        "rate_set_version": store.max_rate_set_version(),
        "count": len(service.cards()),
        "coverage": service.coverage(),
        "overlaps": service.overlaps(),
        "digest": service.rate_digest(),
    }


@router.post("/api/rates/audit")
async def api_audit(file: UploadFile | None = File(default=None),
                    sample: str = Form(default=config.SAMPLE_RATES_OVERLAP)):
    if file is not None and file.filename:
        raw = await file.read()
        name = file.filename
    else:
        name = sample
        path = config.SAMPLE_DIR / name
        raw = path.read_bytes() if path.exists() else b""
    return {"ok": True, "report": service.audit(raw, name)}


@router.post("/api/rates/import")
async def api_import(file: UploadFile | None = File(default=None),
                     sample: str = Form(default=config.SAMPLE_RATES)):
    if file is not None and file.filename:
        raw = await file.read()
        name = file.filename
    else:
        name = sample
        path = config.SAMPLE_DIR / name
        raw = path.read_bytes() if path.exists() else b""
    return {"ok": True, "result": service.import_rate_set(raw, name)}
