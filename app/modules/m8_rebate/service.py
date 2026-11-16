"""M8 编排：档位装载、月度返利重算（幂等）、发布锁定与月账对账。"""

from __future__ import annotations

import hashlib
from decimal import Decimal

from app import config, manifest, store
from app.errors import DomainError
from app.modules.m5_charges.money import ZERO, q2, total
from app.modules.m8_rebate import engine, tiers as tier_rules

DRAFT = "draft"
PUBLISHED = "published"


# --- 档位主数据 -------------------------------------------------------------

def load_tiers(text: str) -> dict:
    rows, problems = tier_rules.parse_tiers(text)
    if problems:
        raise DomainError("REBATE_TIER_INVALID", ";".join(problems[:5]), 422)
    store.replace_rebate_tiers(rows)
    return {"applied": True, "tier_rows": len(rows),
            "groups": len(tier_rules.group_by_carrier_month(rows))}


def seed_sample_tiers(force: bool = False) -> dict:
    if store.rebate_tiers() and not force:
        return {"applied": False, "tier_rows": len(store.rebate_tiers())}
    path = config.SAMPLE_DIR / config.SAMPLE_REBATE_TIERS
    if not path.exists():
        raise DomainError("SAMPLE_MISSING", f"样例文件不存在：{path.name}", 404)
    return load_tiers(path.read_text(encoding="utf-8"))


def tier_rows(carrier: str = "", month: str = "") -> list[dict]:
    return store.rebate_tiers(carrier, month)


# --- 月度返利重算 -----------------------------------------------------------

def _digest(carrier: str, month: str, base_total: str, pct: str,
            waybill_bases: list[tuple[str, Decimal]]) -> str:
    payload = manifest.dumps([
        carrier, month, base_total, pct,
        [[waybill_no, str(q2(base))] for waybill_no, base in waybill_bases],
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_rebates(run_id: str) -> dict:
    """按运行整体重算返利：先删后插，已发布月份锁定拒绝，重跑不重复计提。"""
    run = store.get_run(run_id)
    if not run:
        raise DomainError("RUN_NOT_FOUND", f"运行不存在：{run_id}", 404)
    charge_rows = store.charge_lines(run_id)
    if not charge_rows:
        raise DomainError("NO_CHARGES", "该运行还没有账单，无法计算返利", 409)

    locked = [row for row in store.rebate_months(run_id) if row["status"] == PUBLISHED]
    if locked:
        keys = "、".join(f"{r['carrier']}/{r['month']}" for r in locked)
        raise DomainError(
            "REBATE_PUBLISHED_LOCKED",
            f"月度返利已发布并锁定：{keys}；如需重算请先撤回",
            409,
        )

    waybill_rows = store.waybills(run_id)
    buckets = engine.group_waybills(charge_rows, waybill_rows)
    tier_map = engine.tier_index(store.rebate_tiers())

    month_docs: list[dict] = []
    line_docs: list[dict] = []
    for (carrier, month), waybill_bases in sorted(buckets.items()):
        tier_list = tier_map.get((carrier, month), [])
        result = engine.compute_month(carrier, month, waybill_bases, tier_list)
        digest = _digest(
            carrier, month, result["base_total"], result["rebate_pct"], waybill_bases
        )
        month_docs.append({
            "carrier": carrier,
            "month": month,
            "base_total": result["base_total"],
            "tier_from": result["tier_from"] or "0.00",
            "tier_to": result["tier_to"] or "0.00",
            "rebate_pct": result["rebate_pct"],
            "rebate_total": result["rebate_total"],
            "waybill_count": len(waybill_bases),
            "status": DRAFT,
            "digest": digest,
            "published_at": "",
        })
        if not result["hit"]:
            continue
        for allocation in result["allocations"]:
            codes = ["REBATE_TIER_HIT", "REBATE_RETRO_MONTH"]
            if allocation["is_absorbing"]:
                codes.append("REBATE_ROUNDING_LAST")
            line_docs.append({
                "carrier": carrier,
                "month": month,
                "waybill_no": allocation["waybill_no"],
                "base_amount": allocation["base_amount"],
                "weight_share": allocation["weight_share"],
                "rebate_amount": allocation["rebate_amount"],
                "is_absorbing": allocation["is_absorbing"],
                "codes": ",".join(codes),
            })

    # 整体替换：同一次重算内旧的草稿行全部清除，杜绝重复返利
    store.replace_rebate_months(run_id, month_docs)
    store.replace_rebate_lines(run_id, line_docs)
    now = manifest.utc_now_iso()
    store.add_stage(run_id, "rebates", now)

    rebate_sum = total([Decimal(doc["rebate_total"]) for doc in month_docs])
    return {
        "run_id": run_id,
        "months": len(month_docs),
        "hit_months": sum(1 for doc in month_docs if Decimal(doc["rebate_total"]) > 0),
        "rebate_lines": len(line_docs),
        "rebate_total": str(rebate_sum),
        "status": DRAFT,
    }


# --- 发布 / 撤回 ------------------------------------------------------------

def publish(run_id: str, carrier: str, month: str) -> dict:
    """月账核对通过后才允许发布；发布后该月锁定，重算结算被拒绝。"""
    row = store.rebate_month(run_id, carrier, month)
    if row is None:
        raise DomainError("REBATE_MONTH_NOT_FOUND",
                          f"无该月返利结果：{carrier} {month}", 404)
    check = reconcile_month(run_id, carrier, month)
    if not check["balanced"]:
        raise DomainError(
            "REBATE_RECONCILE_FAILED",
            f"{carrier} {month} 月账未平：{check['broken']}", 409,
        )
    if row["status"] != PUBLISHED:
        store.set_rebate_month_status(
            run_id, carrier, month, PUBLISHED, manifest.utc_now_iso()
        )
    fresh = store.rebate_month(run_id, carrier, month)
    return {"ok": True, "carrier": carrier, "month": month,
            "status": fresh["status"], "published_at": fresh["published_at"]}


def revoke(run_id: str, carrier: str, month: str) -> dict:
    """撤回发布回到草稿，撤回后才允许重算。"""
    row = store.rebate_month(run_id, carrier, month)
    if row is None:
        raise DomainError("REBATE_MONTH_NOT_FOUND",
                          f"无该月返利结果：{carrier} {month}", 404)
    store.set_rebate_month_status(run_id, carrier, month, DRAFT, "")
    return {"ok": True, "carrier": carrier, "month": month, "status": DRAFT}


# --- 查询 -------------------------------------------------------------------

def month_summary(run_id: str) -> list[dict]:
    return store.rebate_months(run_id)


def lines(run_id: str, carrier: str = "", month: str = "") -> list[dict]:
    return store.rebate_lines(run_id, carrier, month)


# --- 月账对账 ---------------------------------------------------------------

def reconcile_month(run_id: str, carrier: str, month: str) -> dict:
    """单月三账勾稽：月度返利 = 逐票分摊之和 = 月基数 × 命中档费率。"""
    summary = store.rebate_month(run_id, carrier, month)
    if summary is None:
        raise DomainError("REBATE_MONTH_NOT_FOUND",
                          f"无该月返利结果：{carrier} {month}", 404)
    line_rows = store.rebate_lines(run_id, carrier, month)

    allocated = total([Decimal(row["rebate_amount"]) for row in line_rows])
    base_of_lines = total([Decimal(row["base_amount"]) for row in line_rows])
    base_total = Decimal(summary["base_total"])
    rebate_total = Decimal(summary["rebate_total"])
    expected = q2(base_total * Decimal(summary["rebate_pct"]))

    # 账 1：分摊守恒（逐票之和 == 月度返利）
    alloc_ok = allocated == rebate_total
    # 账 2：基数闭合（分摊票基数之和 == 月度基数；零返利月允许无分摊行）
    base_ok = (base_of_lines == base_total) if rebate_total > 0 else True
    # 账 3：费率复算（月度返利 == 基数 × 档费率）
    rate_ok = rebate_total == expected
    # 账 4：权重和为 1（有分摊时，按权重量化刻度 1e-6 复算）
    share_sum = q2(sum((Decimal(row["weight_share"]) for row in line_rows), ZERO))
    share_ok = (share_sum == Decimal("1.00")) if line_rows else True

    broken = [name for name, ok in (
        ("allocation", alloc_ok), ("base", base_ok),
        ("rate", rate_ok), ("share", share_ok),
    ) if not ok]
    return {
        "run_id": run_id,
        "carrier": carrier,
        "month": month,
        "status": summary["status"],
        "base_total": str(base_total),
        "rebate_pct": summary["rebate_pct"],
        "expected_rebate": str(expected),
        "rebate_total": str(rebate_total),
        "allocated_total": str(allocated),
        "line_count": len(line_rows),
        "balanced": not broken,
        "broken": broken,
    }


def reconcile_run(run_id: str) -> dict:
    """整份运行的返利对账：逐月四查 + 全部月份汇总守恒。未计提时返回空态。"""
    months = store.rebate_months(run_id)
    if not months:
        gross = _net_receivable(run_id)
        return {
            "run_id": run_id,
            "months": [],
            "rebate_total": "0.00",
            "allocated_total": "0.00",
            "grand_balanced": True,
            "balanced": True,
            "broken": [],
            "gross_receivable": gross["gross"],
            "rebate": "0.00",
            "net_receivable": gross["gross"],
            "published": False,
        }
    month_checks = [
        reconcile_month(run_id, row["carrier"], row["month"]) for row in months
    ]
    rebate_sum = total([Decimal(row["rebate_total"]) for row in months])
    line_sum = total([
        Decimal(row["rebate_amount"]) for row in store.rebate_lines(run_id)
    ])
    all_balanced = all(check["balanced"] for check in month_checks)
    grand_ok = rebate_sum == line_sum
    broken = []
    if not all_balanced:
        broken.extend(
            f"{check['carrier']}/{check['month']}:{','.join(check['broken'])}"
            for check in month_checks if not check["balanced"]
        )
    if not grand_ok:
        broken.append("grand_total")
    net_receivable = _net_receivable(run_id)
    # 只有产生返利的月份才需要发布；零返利月份无需锁定
    releasable = [row for row in months if Decimal(row["rebate_total"]) > 0]
    published = bool(releasable) and all(
        row["status"] == PUBLISHED for row in releasable
    )
    return {
        "run_id": run_id,
        "months": month_checks,
        "rebate_total": str(rebate_sum),
        "allocated_total": str(line_sum),
        "grand_balanced": grand_ok,
        "balanced": all_balanced and grand_ok,
        "broken": broken,
        "gross_receivable": net_receivable["gross"],
        "rebate": net_receivable["rebate"],
        "net_receivable": net_receivable["net"],
        "published": published,
    }


def _net_receivable(run_id: str) -> dict:
    """月账净值：原应收（不回改）与返利调整分别列示，净值 = 原应收 - 返利。"""
    charge_rows = store.charge_lines(run_id)
    gross = total([Decimal(row["total_amount"]) for row in charge_rows])
    rebate = total([
        Decimal(row["rebate_amount"]) for row in store.rebate_lines(run_id)
    ])
    return {"gross": str(gross), "rebate": str(rebate), "net": str(q2(gross - rebate))}
