"""M8 入口：月度返利页、重算、发布/撤回与对账接口。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app import store, web
from app.modules.m8_rebate import service

router = APIRouter(tags=["rebates"])


@router.get("/rebates", response_class=HTMLResponse)
def page_rebates(request: Request):
    context = web.shell(request, active="rebates")
    run_id = context["run_id"]
    context.update({
        "tiers": service.tier_rows() if run_id else [],
        "summary": service.month_summary(run_id) if run_id else [],
        "lines": service.lines(run_id) if run_id else [],
        "report": service.reconcile_run(run_id) if run_id else {},
    })
    return web.page("rebates.html", context)


@router.get("/api/rebates/tiers")
def api_tiers(carrier: str = "", month: str = ""):
    return {"ok": True, "tiers": service.tier_rows(carrier, month)}


@router.post("/api/rebates/tiers/seed")
def api_seed_tiers():
    return {"ok": True, "result": service.seed_sample_tiers(force=True)}


@router.post("/api/rebates/compute")
def api_compute(run: str = ""):
    run_id = run or store.latest_run_id()
    return {"ok": True, "result": service.compute_rebates(run_id)}


@router.get("/api/rebates/lines")
def api_lines(run: str = "", carrier: str = "", month: str = ""):
    run_id = run or store.latest_run_id()
    return {"ok": True, "lines": service.lines(run_id, carrier, month)}


@router.get("/api/rebates/reconcile")
def api_reconcile(run: str = ""):
    run_id = run or store.latest_run_id()
    return {"ok": True, "report": service.reconcile_run(run_id)}


@router.post("/api/rebates/publish")
def api_publish(carrier: str, month: str, run: str = ""):
    run_id = run or store.latest_run_id()
    return {"ok": True, "result": service.publish(run_id, carrier, month)}


@router.post("/api/rebates/revoke")
def api_revoke(carrier: str, month: str, run: str = ""):
    run_id = run or store.latest_run_id()
    return {"ok": True, "result": service.revoke(run_id, carrier, month)}
