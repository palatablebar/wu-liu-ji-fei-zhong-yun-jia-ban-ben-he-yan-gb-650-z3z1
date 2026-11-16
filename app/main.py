"""应用装配：路由注册与启动引导（装运价 → 采信 → 计费重 → 账单）。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import config, errors, store
from app.modules.m1_waybill import service as waybill_service
from app.modules.m1_waybill.handler import router as waybills_router
from app.modules.m2_rates import service as rate_service
from app.modules.m2_rates.handler import router as rates_router
from app.modules.m3_quality.handler import router as quality_router
from app.modules.m4_weights import service as weight_service
from app.modules.m4_weights.handler import router as weights_router
from app.modules.m5_charges import service as charge_service
from app.modules.m5_charges.handler import router as charges_router
from app.modules.m6_reconcile.handler import router as reconcile_router
from app.modules.m7_export.handler import router as export_router


def bootstrap() -> dict:
    """幂等引导：库里已有运单且阶段齐全时不重复计算。"""
    store.init_db()
    seeded = rate_service.seed_sample()
    run = waybill_service.ensure_sample_run()
    run_id = run.get("run_id", "")
    if run_id:
        row = store.get_run(run_id) or {}
        stages = row.get("stages") or ""
        if "weights" not in stages:
            weight_service.compute_weights(run_id)
        row = store.get_run(run_id) or {}
        if "charges" not in (row.get("stages") or ""):
            charge_service.compute_charges(run_id)
    return {"rates": seeded, "run": run}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    bootstrap()
    yield


app = FastAPI(title="freightrate", lifespan=lifespan, docs_url="/docs", redoc_url=None)
errors.register(app)
app.mount("/static", StaticFiles(directory=str(config.BASE_DIR / "static")), name="static")

for router in (
    rates_router,
    waybills_router,
    quality_router,
    weights_router,
    charges_router,
    reconcile_router,
    export_router,
):
    app.include_router(router)


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "rules_version": config.RULES_VERSION,
        "run_id": store.latest_run_id(),
        "rate_set_version": store.max_rate_set_version(),
        "display_tz": config.DISPLAY_TZ,
    }
