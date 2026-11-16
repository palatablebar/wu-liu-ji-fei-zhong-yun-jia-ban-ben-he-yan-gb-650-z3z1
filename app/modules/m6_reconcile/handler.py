"""M6 入口：账单对账页与对账接口。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app import store, web
from app.modules.m6_reconcile import service

router = APIRouter(tags=["reconcile"])


@router.get("/reconcile", response_class=HTMLResponse)
def page_reconcile(request: Request):
    context = web.shell(request, active="reconcile")
    run_id = context["run_id"]
    context.update({"report": service.reconcile(run_id) if run_id else {}})
    return web.page("reconcile.html", context)


@router.get("/api/reconcile")
def api_reconcile(run: str = ""):
    run_id = run or store.latest_run_id()
    return {"ok": True, "report": service.reconcile(run_id)}
