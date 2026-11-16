"""返利计算引擎：月度归集 → 越档择档 → 按票分摊 → 尾差吸收。

全程 Decimal、量化到分；任何 float 累加都会破坏分账守恒（与 TRAP-10 同源）。
"""

from __future__ import annotations

from decimal import Decimal

from app import config
from app.modules.m5_charges.money import ZERO, q2, total
from app.modules.m8_rebate import tiers as tier_rules


def month_of(pickup_utc: str) -> str:
    """按 UTC 归一后的提货时刻取自然月 YYYY-MM（与择版同一时刻口径）。"""
    return pickup_utc[:7]


def waybill_base(charge_row: dict) -> Decimal:
    """返利基数 = 基础运费 + 续重运费（运输性运费），不含附加费。"""
    return total([
        Decimal(charge_row[field]) for field in config.REBATE_BASE_FIELDS
    ])


def select_tier(base_sum: Decimal, tiers: list[dict]) -> dict | None:
    """命中满足 ``tier_from <= 基数 < tier_to`` 的唯一档；敞口档 tier_to 为极大值。"""
    for tier in tiers:
        low = Decimal(tier["tier_from"])
        high = Decimal(tier["tier_to"])
        if low <= base_sum < high:
            return tier
    return None


def allocate(base_sum: Decimal, rebate_total: Decimal,
             waybill_bases: list[tuple[str, Decimal]]) -> list[dict]:
    """把月度返利按票基础运费权重分摊，尾差吸收到月内最后一票。

    除最后一票外按 ``返利 × 票基数 / 月基数`` 量化到分；
    最后一票 = 月度返利 - 已分摊之和，保证逐票之和严格等于月度返利（一分不差）。
    月基数为 0 时不分摊（调用方已保证不进入）。
    """
    allocations: list[dict] = []
    if not waybill_bases or base_sum <= 0:
        return allocations

    running = ZERO
    last_index = len(waybill_bases) - 1
    share_quant = Decimal("0.000001")
    shares: list[Decimal] = []
    for index, (waybill_no, base) in enumerate(waybill_bases):
        is_last = index == last_index
        if is_last:
            # 末票吸收两处尾差：金额尾差（返利 - 已分摊）与权重舍入残差
            amount = q2(rebate_total - running)
            share = (Decimal("1.000000") - sum(shares, ZERO)).quantize(share_quant)
        else:
            amount = q2(rebate_total * base / base_sum)
            running += amount
            share = (base / base_sum).quantize(share_quant)
        shares.append(share)
        allocations.append({
            "waybill_no": waybill_no,
            "base_amount": str(q2(base)),
            "weight_share": str(share),
            "rebate_amount": str(amount),
            "is_absorbing": is_last,
        })
    return allocations


def compute_month(carrier: str, month: str,
                  waybill_bases: list[tuple[str, Decimal]],
                  tier_rows: list[dict]) -> dict:
    """单个承运商单个自然月的返利汇总与逐票分摊。

    返回 ``hit=False`` 表示未越档（零费率档或无匹配档），不产生返利行。
    """
    base_sum = total([base for _wb, base in waybill_bases])
    tier = select_tier(base_sum, tier_rows)
    if tier is None:
        return {
            "carrier": carrier, "month": month, "hit": False,
            "base_total": str(base_sum), "rebate_pct": "0.0000",
            "tier_from": "", "tier_to": "", "rebate_total": "0.00",
            "allocations": [],
        }

    pct = Decimal(tier["rebate_pct"])
    rebate_total = q2(base_sum * pct)
    hit = pct > 0 and rebate_total > 0
    allocations = allocate(base_sum, rebate_total, waybill_bases) if hit else []
    return {
        "carrier": carrier,
        "month": month,
        "hit": hit,
        "base_total": str(base_sum),
        "tier_from": tier["tier_from"],
        "tier_to": tier["tier_to"],
        "rebate_pct": str(pct),
        "rebate_total": str(rebate_total),
        "allocations": allocations,
    }


def group_waybills(charge_rows: list[dict],
                   waybill_rows: list[dict]) -> dict[tuple[str, str], list[tuple[str, Decimal]]]:
    """把计费行按 (承运商, 自然月) 归集，值为 (运单号, 基础运费) 并按运单号稳定排序。"""
    pickup_of = {row["waybill_no"]: row["pickup_utc"] for row in waybill_rows}
    carrier_of = {row["waybill_no"]: row["carrier"] for row in waybill_rows}
    buckets: dict[tuple[str, str], list[tuple[str, Decimal]]] = {}
    for charge in charge_rows:
        waybill_no = charge["waybill_no"]
        pickup = pickup_of.get(waybill_no, "")
        carrier = carrier_of.get(waybill_no, "")
        if not pickup or not carrier:
            continue
        base = waybill_base(charge)
        if base <= 0:
            continue
        key = (carrier, month_of(pickup))
        buckets.setdefault(key, []).append((waybill_no, base))
    for items in buckets.values():
        items.sort(key=lambda pair: pair[0])
    return buckets


def tier_index(rows: list[dict]) -> dict[tuple[str, str], list[dict]]:
    return tier_rules.group_by_carrier_month(rows)
