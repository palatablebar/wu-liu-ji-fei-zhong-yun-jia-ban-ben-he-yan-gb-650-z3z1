"""M8 月度返利：整月补差、独立调整单、分摊守恒、发布锁定与重跑幂等。

关键业务场景（结算组提出的两难）：
同月前半已出账、月末才越档 —— 本模块采用整月补差：
原运费不回改，返利按整月基数 × 命中档费率计算后，以独立负向调整行
按票权重分摊回全月每一票，月账净值 = 原应收 - 返利。
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app import store
from app.errors import DomainError
from app.modules.m5_charges.money import q2
from app.modules.m5_charges import service as charges
from app.modules.m8_rebate import engine, service as rebate
from app.modules.m8_rebate import tiers as tier_rules

TIER_CSV = (
    "carrier,month,tier_from,tier_to,rebate_pct\n"
    "SF,2026-04,0.00,300.00,0.0000\n"
    "SF,2026-04,300.00,600.00,0.0200\n"
    "SF,2026-04,600.00,9999999.99,0.0400\n"
    "JD,2026-04,0.00,9999999.99,0.0000\n"
)


@pytest.fixture(scope="module")
def rebated(pipeline):
    run_id = pipeline["run_id"]
    rebate.seed_sample_tiers(force=True)
    rebate.compute_rebates(run_id)
    return run_id


# --- 档位解析 ---------------------------------------------------------------

def test_tier_csv_parses_and_validates():
    rows, problems = tier_rules.parse_tiers(TIER_CSV)
    assert problems == []
    groups = tier_rules.group_by_carrier_month(rows)
    assert set(groups) == {("SF", "2026-04"), ("JD", "2026-04")}
    assert len(groups[("SF", "2026-04")]) == 3


def test_tier_gap_is_rejected():
    broken = TIER_CSV.replace("300.00,600.00", "320.00,600.00")
    _rows, problems = tier_rules.parse_tiers(broken)
    assert any("断档" in p for p in problems)


def test_tier_pct_regression_is_rejected():
    broken = TIER_CSV.replace("0.0400", "0.0100")
    _rows, problems = tier_rules.parse_tiers(broken)
    assert any("回退" in p for p in problems)


def test_tier_bad_pct_and_month_rejected():
    bad = (
        "carrier,month,tier_from,tier_to,rebate_pct\n"
        "SF,2026-13,0.00,1.00,0.0100\n"
        "SF,2026-04,0.00,1.00,1.5000\n"
    )
    _rows, problems = tier_rules.parse_tiers(bad)
    assert len(problems) == 2


def test_load_invalid_tiers_raises_domain_error():
    bad = (
        "carrier,month,tier_from,tier_to,rebate_pct\n"
        "SF,2026-04,0.00,100.00,0.0200\n"
        "SF,2026-04,120.00,9999999.99,0.0300\n"
    )
    with pytest.raises(DomainError) as exc:
        rebate.load_tiers(bad)
    assert exc.value.code == "REBATE_TIER_INVALID"
    # 非法装载不覆盖既有档位
    assert store.rebate_tiers()


# --- 引擎纯函数 -------------------------------------------------------------

def test_select_tier_half_open_boundary():
    tiers = tier_rules.group_by_carrier_month(
        tier_rules.parse_tiers(TIER_CSV)[0]
    )[("SF", "2026-04")]
    assert engine.select_tier(Decimal("299.99"), tiers)["rebate_pct"] == "0.0000"
    assert engine.select_tier(Decimal("300.00"), tiers)["rebate_pct"] == "0.0200"
    assert engine.select_tier(Decimal("600.00"), tiers)["rebate_pct"] == "0.0400"


def test_allocate_conserves_with_last_ticket_absorbing_remainder():
    bases = [("WB-A", Decimal("33.80")), ("WB-B", Decimal("19.00")),
             ("WB-C", Decimal("630.60"))]
    base_sum = Decimal("683.40")
    rebate_total = Decimal("27.34")  # 683.40 × 4% = 27.336 → 27.34
    allocations = engine.allocate(base_sum, rebate_total, bases)

    assert len(allocations) == 3
    assert allocations[-1]["is_absorbing"] == 1
    assert sum(1 for a in allocations if a["is_absorbing"]) == 1
    summed = sum((Decimal(a["rebate_amount"]) for a in allocations), Decimal("0"))
    assert summed == rebate_total  # 一分不差
    share_sum = sum((Decimal(a["weight_share"]) for a in allocations), Decimal("0"))
    assert share_sum == Decimal("1.000000")


def test_month_of_uses_utc_calendar_month():
    # 北京时间 4 月 1 日 07:59 对应 UTC 3 月 31 日，归入 2026-03
    assert engine.month_of("2026-03-31T23:59:59Z") == "2026-03"
    assert engine.month_of("2026-04-01T00:00:00Z") == "2026-04"


def test_single_ticket_month_takes_whole_rebate_with_unit_share():
    allocations = engine.allocate(
        Decimal("100.00"), Decimal("4.00"), [("WB-1", Decimal("100.00"))]
    )
    assert allocations[0]["rebate_amount"] == "4.00"
    assert allocations[0]["weight_share"] == "1.000000"
    assert allocations[0]["is_absorbing"] == 1


def test_missing_tier_and_sub_cent_rebate_produce_no_lines():
    missed = engine.compute_month("XX", "2026-04", [("WB-1", Decimal("10.00"))], [])
    assert missed["hit"] is False and missed["allocations"] == []

    tiny = engine.compute_month(
        "SF", "2026-04", [("WB-1", Decimal("0.10"))],
        [{"tier_from": "0.00", "tier_to": "9999999.99", "rebate_pct": "0.0001"}],
    )
    assert tiny["rebate_total"] == "0.00" and tiny["hit"] is False


# --- 整月补差主流程（关键决策） ----------------------------------------------

def test_retro_full_month_rebate_hits_every_ticket(rebated):
    """越档后整月补差：同月早期已出账的运单也必须拿到返利分摊。"""
    sf_april = store.rebate_lines(rebated, "SF", "2026-04")
    waybills = {row["waybill_no"] for row in sf_april}
    # WB-1001/1002 是 4 月 3 日的早期运单，月末累计越档后仍被整月补差覆盖
    assert {"WB-1001", "WB-1002", "WB-1018"}.issubset(waybills)
    for row in sf_april:
        assert Decimal(row["rebate_amount"]) > 0


def test_original_charge_lines_are_never_rewritten(rebated):
    """返利以独立调整单列账，逐笔原运费与原应收 1521.04 保持不变。"""
    totals = charges.amounts(rebated)
    assert str(totals["total"]) == "1521.04"
    for row in store.charge_lines(rebated):
        # 账单行里没有任何返利字段被改写
        assert "rebate" not in row


def test_monthly_rebate_equals_base_times_tier_rate(rebated):
    summary = {
        (r["carrier"], r["month"]): r for r in store.rebate_months(rebated)
    }
    sf = summary[("SF", "2026-04")]
    assert sf["base_total"] == "914.00"
    assert sf["rebate_pct"] == "0.0400"          # 落入 600+ 的 4% 档
    assert sf["rebate_total"] == "36.56"         # 914.00 × 4% 量化到分
    jd = summary[("JD", "2026-04")]
    assert jd["rebate_pct"] == "0.0450"
    assert jd["rebate_total"] == "12.58"


def test_zero_rate_month_has_no_rebate_lines(rebated):
    yt = store.rebate_month(rebated, "YT", "2026-04")
    assert yt["rebate_total"] == "0.00"
    assert store.rebate_lines(rebated, "YT", "2026-04") == []


def test_march_tier_also_retro_covers_early_spring_tickets(rebated):
    """跨月样本：3 月只有两票，累计 36 越过 30 档线，两票各享 3% 补差。"""
    rows = store.rebate_lines(rebated, "SF", "2026-03")
    assert {r["waybill_no"] for r in rows} == {"WB-1011", "WB-1013"}
    assert sum((Decimal(r["rebate_amount"]) for r in rows), Decimal("0")) == Decimal("1.08")


# --- 三账勾稽 ---------------------------------------------------------------

def test_reconcile_balanced_for_every_month(rebated):
    report = rebate.reconcile_run(rebated)
    assert report["balanced"] is True
    assert report["broken"] == []
    for month in report["months"]:
        assert month["balanced"] is True
        assert month["allocated_total"] == month["rebate_total"]
        assert month["expected_rebate"] == month["rebate_total"]


def test_allocation_sum_equals_month_rebate_exactly(rebated):
    report = rebate.reconcile_run(rebated)
    assert report["rebate_total"] == report["allocated_total"] == "50.22"


def test_net_receivable_equals_gross_minus_rebate(rebated):
    report = rebate.reconcile_run(rebated)
    assert report["gross_receivable"] == "1521.04"
    assert report["rebate"] == "50.22"
    assert report["net_receivable"] == "1470.82"
    assert Decimal(report["net_receivable"]) == (
        Decimal(report["gross_receivable"]) - Decimal(report["rebate"])
    )


def test_tampered_allocation_breaks_reconcile_and_blocks_publish(rebated):
    store.execute(
        "UPDATE rebate_lines SET rebate_amount='0.01' WHERE run_id=? AND waybill_no='WB-1001'",
        (rebated,),
    )
    check = rebate.reconcile_month(rebated, "SF", "2026-04")
    assert check["balanced"] is False
    assert "allocation" in check["broken"]
    with pytest.raises(DomainError) as exc:
        rebate.publish(rebated, "SF", "2026-04")
    assert exc.value.code == "REBATE_RECONCILE_FAILED"


# --- 发布锁定与重跑幂等 ------------------------------------------------------

def test_rerun_is_idempotent_no_double_rebate(rebated):
    before_lines = len(store.rebate_lines(rebated))
    before_total = rebate.reconcile_run(rebated)["rebate_total"]
    rebate.compute_rebates(rebated)
    rebate.compute_rebates(rebated)
    after = rebate.reconcile_run(rebated)
    assert len(store.rebate_lines(rebated)) == before_lines
    assert after["rebate_total"] == before_total


def test_publish_locks_month_against_rerun(rebated):
    result = rebate.publish(rebated, "SF", "2026-04")
    assert result["status"] == "published"
    with pytest.raises(DomainError) as exc:
        rebate.compute_rebates(rebated)
    assert exc.value.code == "REBATE_PUBLISHED_LOCKED"
    # 发布是幂等的：重复发布不改变发布时间语义，只返回当前状态
    again = rebate.publish(rebated, "SF", "2026-04")
    assert again["status"] == "published"


def test_revoke_unlocks_and_rerun_reproduces_same_numbers(rebated):
    rebate.revoke(rebated, "SF", "2026-04")
    before = rebate.reconcile_run(rebated)["rebate_total"]
    rebate.compute_rebates(rebated)
    assert rebate.reconcile_run(rebated)["rebate_total"] == before
    assert store.rebate_month(rebated, "SF", "2026-04")["status"] == "draft"


def test_compute_unknown_run_raises():
    with pytest.raises(DomainError) as exc:
        rebate.compute_rebates("RUN-NOPE-NOPE")
    assert exc.value.code == "RUN_NOT_FOUND"


def test_reconcile_empty_state_is_balanced():
    """未计提返利时对账接口返回空态而非报错，净值等于原应收。"""
    report = rebate.reconcile_run("RUN-EMPTY-STATE")
    assert report["balanced"] is True
    assert report["months"] == []
    assert report["rebate_total"] == "0.00"
    assert report["net_receivable"] == report["gross_receivable"] == "0.00"


def test_publish_unknown_month_raises(rebated):
    with pytest.raises(DomainError) as exc:
        rebate.publish(rebated, "SF", "2099-01")
    assert exc.value.code == "REBATE_MONTH_NOT_FOUND"


def test_policy_choice_full_month_vs_post_threshold_only():
    """把题面两难固化成数字：同月前半已出账、月末才越档。

    构造月基数 1000、费率 4%、两票各 500（第二票才把累计推过档线）：
    - 整月补差（本模块选择）：两票各分摊 20.00，月返利 40.00；
    - 只作用越档后运单（被否决）：首票 0、次票 20.00，同票返利取决于它是否越档，
      且月返利只有 20.00，与"整月都可补差"的约定不符。
    """
    bases = [("WB-EARLY", Decimal("500.00")), ("WB-LATE", Decimal("1000.00") - Decimal("500.00"))]
    base_sum = Decimal("1000.00")
    monthly_rebate = Decimal("40.00")  # 1000 × 4%

    allocations = engine.allocate(base_sum, monthly_rebate, bases)
    by_ticket = {a["waybill_no"]: Decimal(a["rebate_amount"]) for a in allocations}

    # 整月补差：早期已出账运单同样拿到返利，且两票之和等于整月返利
    assert by_ticket["WB-EARLY"] == Decimal("20.00")
    assert by_ticket["WB-LATE"] == Decimal("20.00")
    assert sum(by_ticket.values(), Decimal("0")) == monthly_rebate

    # 反设"只作用越档后运单"：首票返利为 0，同一票在两种政策下返利不同
    post_only = {"WB-EARLY": Decimal("0.00"),
                 "WB-LATE": q2(Decimal("500.00") * Decimal("0.04"))}
    assert post_only["WB-EARLY"] != by_ticket["WB-EARLY"]
    assert sum(post_only.values(), Decimal("0")) == Decimal("20.00") != monthly_rebate


def test_rebate_lines_are_separate_from_charge_lines(rebated):
    """存储层隔离：返利行与账单行是两张表，账单行无返利列，重算互不覆盖。"""
    charge_columns = set(store.charge_lines(rebated)[0].keys())
    rebate_columns = set(store.rebate_lines(rebated)[0].keys())
    assert "rebate_amount" not in charge_columns
    assert "total_amount" not in rebate_columns
    # 仅键与只读基数同名，账单专有分项与返利专有分摊列互不侵入
    assert "fuel_amount" not in rebate_columns
    assert "insurance_amount" not in rebate_columns
    assert "weight_share" not in charge_columns
