"""模板渲染与展示格式化：页面共用一套上下文，数字统一在这里定格式。"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app import config, manifest, store

templates = Jinja2Templates(directory=str(config.BASE_DIR / "templates"))


def fmt_money(value) -> str:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    return f"{amount:,.2f}"


def fmt_kg(value) -> str:
    try:
        amount = Decimal(str(value)).quantize(config.WEIGHT_QUANT)
    except (InvalidOperation, ValueError):
        return str(value)
    text = f"{amount:f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def fmt_local(value) -> str:
    return manifest.local_display(str(value or ""))


def rule(width: int = 72) -> str:
    return "─" * width


def shell(request: Request, active: str = "", run_id: str = "") -> dict:
    """页面外壳上下文：批次号、规则版本、生成时间、时区。"""
    row = store.get_run(run_id) if run_id else None
    if row is None:
        latest = store.latest_run_id()
        row = store.get_run(latest) if latest else None
    row = row or {}
    return {
        "request": request,
        "active": active,
        "run": row,
        "run_id": row.get("run_id", ""),
        "rules_version": config.RULES_VERSION,
        "generated_at": manifest.local_display(manifest.utc_now_iso()),
        "display_tz": config.DISPLAY_TZ,
        "runs": store.list_runs(8),
    }


def page(name: str, context: dict):
    request = context["request"]
    return templates.TemplateResponse(request=request, name=name, context=context)


def tojson(value, indent: int = 2) -> str:
    return json.dumps(value, ensure_ascii=False, indent=indent, sort_keys=True, default=str)


templates.env.filters["tojson"] = tojson
templates.env.filters["money"] = fmt_money
templates.env.filters["kg"] = fmt_kg
templates.env.filters["local"] = fmt_local
templates.env.globals["rule"] = rule
templates.env.globals["addon_order"] = ("base", "step", "remote", "fuel", "insurance")
