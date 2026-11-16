"""SQLite 存取：运行清单、运价版本、运单、隔离区、计费重行、账单行。

只放数据访问，不放业务规则。每次调用开一个连接，用完即关。
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager

from app import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  input_name TEXT NOT NULL DEFAULT '',
  input_sha256 TEXT NOT NULL DEFAULT '',
  rules_version TEXT NOT NULL DEFAULT '',
  profile TEXT NOT NULL DEFAULT '',
  rows_in INTEGER NOT NULL DEFAULT 0,
  rows_ok INTEGER NOT NULL DEFAULT 0,
  rows_quarantined INTEGER NOT NULL DEFAULT 0,
  amount_total TEXT NOT NULL DEFAULT '0.00',
  rate_digest TEXT NOT NULL DEFAULT '',
  stages TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS rate_sets (
  carrier TEXT PRIMARY KEY,
  rate_set_version INTEGER NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rate_cards (
  carrier TEXT NOT NULL,
  service TEXT NOT NULL,
  zone TEXT NOT NULL,
  version_id TEXT NOT NULL,
  effective_from TEXT NOT NULL,
  effective_to TEXT NOT NULL,
  first_weight_kg TEXT NOT NULL,
  first_price TEXT NOT NULL,
  step_weight_kg TEXT NOT NULL,
  step_price TEXT NOT NULL,
  min_charge TEXT NOT NULL,
  volume_divisor INTEGER NOT NULL,
  fuel_pct TEXT NOT NULL,
  remote_fee TEXT NOT NULL,
  insurance_pct TEXT NOT NULL,
  currency TEXT NOT NULL,
  rate_set_version INTEGER NOT NULL,
  PRIMARY KEY (carrier, service, zone, version_id)
);
CREATE TABLE IF NOT EXISTS waybills (
  run_id TEXT NOT NULL,
  line_no INTEGER NOT NULL,
  waybill_no TEXT NOT NULL,
  carrier TEXT NOT NULL,
  service TEXT NOT NULL,
  zone TEXT NOT NULL,
  pickup_utc TEXT NOT NULL,
  weight_kg TEXT NOT NULL,
  length_cm TEXT NOT NULL,
  width_cm TEXT NOT NULL,
  height_cm TEXT NOT NULL,
  declared_value TEXT NOT NULL,
  pieces INTEGER NOT NULL,
  codes TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (run_id, waybill_no)
);
CREATE TABLE IF NOT EXISTS quarantine (
  run_id TEXT NOT NULL,
  line_no INTEGER NOT NULL,
  waybill_no TEXT NOT NULL DEFAULT '',
  code TEXT NOT NULL,
  detail TEXT NOT NULL DEFAULT '',
  raw TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (run_id, line_no, code)
);
CREATE TABLE IF NOT EXISTS weight_lines (
  run_id TEXT NOT NULL,
  waybill_no TEXT NOT NULL,
  version_id TEXT NOT NULL DEFAULT '',
  actual_kg TEXT NOT NULL DEFAULT '0.000',
  volumetric_kg TEXT NOT NULL DEFAULT '0.000',
  source TEXT NOT NULL DEFAULT '',
  billable_kg TEXT NOT NULL DEFAULT '0.000',
  steps INTEGER NOT NULL DEFAULT 0,
  codes TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (run_id, waybill_no)
);
CREATE TABLE IF NOT EXISTS charge_lines (
  run_id TEXT NOT NULL,
  waybill_no TEXT NOT NULL,
  version_id TEXT NOT NULL DEFAULT '',
  base_amount TEXT NOT NULL DEFAULT '0.00',
  step_amount TEXT NOT NULL DEFAULT '0.00',
  remote_amount TEXT NOT NULL DEFAULT '0.00',
  fuel_amount TEXT NOT NULL DEFAULT '0.00',
  insurance_amount TEXT NOT NULL DEFAULT '0.00',
  total_amount TEXT NOT NULL DEFAULT '0.00',
  codes TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (run_id, waybill_no)
);
CREATE TABLE IF NOT EXISTS rebate_tiers (
  carrier TEXT NOT NULL,
  month TEXT NOT NULL,
  tier_from TEXT NOT NULL,
  tier_to TEXT NOT NULL,
  rebate_pct TEXT NOT NULL,
  PRIMARY KEY (carrier, month, tier_from)
);
CREATE TABLE IF NOT EXISTS rebate_months (
  run_id TEXT NOT NULL,
  carrier TEXT NOT NULL,
  month TEXT NOT NULL,
  base_total TEXT NOT NULL DEFAULT '0.00',
  tier_from TEXT NOT NULL DEFAULT '0.00',
  tier_to TEXT NOT NULL DEFAULT '0.00',
  rebate_pct TEXT NOT NULL DEFAULT '0.0000',
  rebate_total TEXT NOT NULL DEFAULT '0.00',
  waybill_count INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'draft',
  digest TEXT NOT NULL DEFAULT '',
  published_at TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (run_id, carrier, month)
);
CREATE TABLE IF NOT EXISTS rebate_lines (
  run_id TEXT NOT NULL,
  carrier TEXT NOT NULL,
  month TEXT NOT NULL,
  waybill_no TEXT NOT NULL,
  base_amount TEXT NOT NULL DEFAULT '0.00',
  weight_share TEXT NOT NULL DEFAULT '0.000000',
  rebate_amount TEXT NOT NULL DEFAULT '0.00',
  is_absorbing INTEGER NOT NULL DEFAULT 0,
  codes TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (run_id, carrier, month, waybill_no)
);
"""


def connect() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with session() as conn:
        conn.executescript(SCHEMA)


def rows(sql: str, params: tuple = ()) -> list[dict]:
    with session() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def one(sql: str, params: tuple = ()) -> dict | None:
    got = rows(sql, params)
    return got[0] if got else None


def execute(sql: str, params: tuple = ()) -> None:
    with session() as conn:
        conn.execute(sql, params)


def executemany(sql: str, seq) -> None:
    with session() as conn:
        conn.executemany(sql, list(seq))


# --- 运行清单 -------------------------------------------------------------

RUN_COLUMNS = (
    "input_name", "input_sha256", "rules_version", "profile",
    "rows_in", "rows_ok", "rows_quarantined", "amount_total",
    "rate_digest", "stages", "notes", "created_at", "updated_at",
)


def get_run(run_id: str) -> dict | None:
    return one("SELECT * FROM runs WHERE run_id = ?", (run_id,))


def list_runs(limit: int = 20) -> list[dict]:
    return rows("SELECT * FROM runs ORDER BY created_at DESC, run_id DESC LIMIT ?", (limit,))


def upsert_run(run_id: str, data: dict) -> None:
    with session() as conn:
        existing = conn.execute("SELECT run_id FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if existing:
            fields = [c for c in RUN_COLUMNS if c in data]
            assignments = ", ".join(f"{c} = ?" for c in fields)
            conn.execute(
                f"UPDATE runs SET {assignments} WHERE run_id = ?",
                tuple(data[c] for c in fields) + (run_id,),
            )
        else:
            payload = {c: data.get(c, "") for c in RUN_COLUMNS}
            payload["rows_in"] = int(payload.get("rows_in") or 0)
            payload["rows_ok"] = int(payload.get("rows_ok") or 0)
            payload["rows_quarantined"] = int(payload.get("rows_quarantined") or 0)
            cols = ("run_id",) + RUN_COLUMNS
            conn.execute(
                f"INSERT INTO runs ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                (run_id,) + tuple(payload[c] for c in RUN_COLUMNS),
            )


def add_stage(run_id: str, stage: str, updated_at: str) -> None:
    run = get_run(run_id)
    if not run:
        return
    parts = [p for p in (run.get("stages") or "").split(",") if p]
    if stage not in parts:
        parts.append(stage)
    execute(
        "UPDATE runs SET stages = ?, updated_at = ? WHERE run_id = ?",
        (",".join(parts), updated_at, run_id),
    )


# --- 运价版本 -------------------------------------------------------------

CARD_COLUMNS = (
    "carrier", "service", "zone", "version_id", "effective_from", "effective_to",
    "first_weight_kg", "first_price", "step_weight_kg", "step_price", "min_charge",
    "volume_divisor", "fuel_pct", "remote_fee", "insurance_pct", "currency",
    "rate_set_version",
)


def replace_rate_cards(cards: list[dict], rate_set_version: int, updated_at: str) -> None:
    with session() as conn:
        conn.execute("DELETE FROM rate_cards")
        conn.executemany(
            f"INSERT INTO rate_cards ({', '.join(CARD_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in CARD_COLUMNS)})",
            [tuple(card[c] for c in CARD_COLUMNS) for card in cards],
        )
        carriers = sorted({card["carrier"] for card in cards})
        conn.execute("DELETE FROM rate_sets")
        conn.executemany(
            "INSERT INTO rate_sets (carrier, rate_set_version, updated_at) VALUES (?, ?, ?)",
            [(c, rate_set_version, updated_at) for c in carriers],
        )


def rate_cards() -> list[dict]:
    return rows("SELECT * FROM rate_cards ORDER BY carrier, service, zone, effective_from")


def rate_set_version(carrier: str) -> int:
    got = one("SELECT rate_set_version FROM rate_sets WHERE carrier = ?", (carrier,))
    return int(got["rate_set_version"]) if got else 0


def max_rate_set_version() -> int:
    got = one("SELECT MAX(rate_set_version) AS v FROM rate_sets")
    return int(got["v"]) if got and got["v"] is not None else 0


# --- 运单 / 隔离区 / 计费行 ------------------------------------------------

def replace_waybills(run_id: str, items: list[dict]) -> None:
    with session() as conn:
        conn.execute("DELETE FROM waybills WHERE run_id = ?", (run_id,))
        conn.executemany(
            "INSERT INTO waybills (run_id, line_no, waybill_no, carrier, service, zone, "
            "pickup_utc, weight_kg, length_cm, width_cm, height_cm, declared_value, pieces, codes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    run_id, it["line_no"], it["waybill_no"], it["carrier"], it["service"],
                    it["zone"], it["pickup_utc"], it["weight_kg"], it["length_cm"],
                    it["width_cm"], it["height_cm"], it["declared_value"], it["pieces"],
                    it["codes"],
                )
                for it in items
            ],
        )


def waybills(run_id: str) -> list[dict]:
    return rows("SELECT * FROM waybills WHERE run_id = ? ORDER BY line_no", (run_id,))


def replace_quarantine(run_id: str, items: list[dict]) -> None:
    with session() as conn:
        conn.execute("DELETE FROM quarantine WHERE run_id = ?", (run_id,))
        conn.executemany(
            "INSERT OR REPLACE INTO quarantine (run_id, line_no, waybill_no, code, detail, raw) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (run_id, it["line_no"], it["waybill_no"], it["code"], it["detail"], it["raw"])
                for it in items
            ],
        )


def quarantine(run_id: str) -> list[dict]:
    return rows(
        "SELECT * FROM quarantine WHERE run_id = ? ORDER BY line_no, code", (run_id,)
    )


def replace_weight_lines(run_id: str, items: list[dict]) -> None:
    with session() as conn:
        conn.execute("DELETE FROM weight_lines WHERE run_id = ?", (run_id,))
        conn.executemany(
            "INSERT INTO weight_lines (run_id, waybill_no, version_id, actual_kg, volumetric_kg, "
            "source, billable_kg, steps, codes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    run_id, it["waybill_no"], it["version_id"], it["actual_kg"],
                    it["volumetric_kg"], it["source"], it["billable_kg"], it["steps"],
                    it.get("codes", ""),
                )
                for it in items
            ],
        )


def weight_lines(run_id: str) -> list[dict]:
    return rows("SELECT * FROM weight_lines WHERE run_id = ? ORDER BY waybill_no", (run_id,))


def replace_charge_lines(run_id: str, items: list[dict]) -> None:
    with session() as conn:
        conn.execute("DELETE FROM charge_lines WHERE run_id = ?", (run_id,))
        conn.executemany(
            "INSERT INTO charge_lines (run_id, waybill_no, version_id, base_amount, step_amount, "
            "remote_amount, fuel_amount, insurance_amount, total_amount, codes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    run_id, it["waybill_no"], it["version_id"], it["base_amount"],
                    it["step_amount"], it["remote_amount"], it["fuel_amount"],
                    it["insurance_amount"], it["total_amount"], it["codes"],
                )
                for it in items
            ],
        )


def charge_lines(run_id: str) -> list[dict]:
    return rows("SELECT * FROM charge_lines WHERE run_id = ? ORDER BY waybill_no", (run_id,))


def latest_run_id() -> str:
    got = one("SELECT run_id FROM runs ORDER BY created_at DESC, run_id DESC LIMIT 1")
    return got["run_id"] if got else ""


# --- 返利档位 / 月度返利 / 分摊行 ------------------------------------------

TIER_COLUMNS = ("carrier", "month", "tier_from", "tier_to", "rebate_pct")


def replace_rebate_tiers(rows_in: list[dict]) -> None:
    """整表替换档位：档位是主数据，一次装载覆盖全量。"""
    with session() as conn:
        conn.execute("DELETE FROM rebate_tiers")
        conn.executemany(
            f"INSERT INTO rebate_tiers ({', '.join(TIER_COLUMNS)}) "
            f"VALUES ({', '.join('?' for _ in TIER_COLUMNS)})",
            [tuple(row[c] for c in TIER_COLUMNS) for row in rows_in],
        )


def rebate_tiers(carrier: str = "", month: str = "") -> list[dict]:
    sql = "SELECT * FROM rebate_tiers"
    clauses: list[str] = []
    params: list = []
    if carrier:
        clauses.append("carrier = ?")
        params.append(carrier)
    if month:
        clauses.append("month = ?")
        params.append(month)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY carrier, month, tier_from"
    return rows(sql, tuple(params))


def replace_rebate_months(run_id: str, rows_in: list[dict]) -> None:
    with session() as conn:
        conn.execute("DELETE FROM rebate_months WHERE run_id = ?", (run_id,))
        conn.executemany(
            "INSERT INTO rebate_months (run_id, carrier, month, base_total, tier_from, tier_to, "
            "rebate_pct, rebate_total, waybill_count, status, digest, published_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    run_id, row["carrier"], row["month"], row["base_total"],
                    row["tier_from"], row["tier_to"], row["rebate_pct"],
                    row["rebate_total"], int(row["waybill_count"]),
                    row["status"], row["digest"], row.get("published_at", ""),
                )
                for row in rows_in
            ],
        )


def rebate_months(run_id: str) -> list[dict]:
    return rows(
        "SELECT * FROM rebate_months WHERE run_id = ? ORDER BY month, carrier", (run_id,)
    )


def rebate_month(run_id: str, carrier: str, month: str) -> dict | None:
    return one(
        "SELECT * FROM rebate_months WHERE run_id = ? AND carrier = ? AND month = ?",
        (run_id, carrier, month),
    )


def set_rebate_month_status(run_id: str, carrier: str, month: str,
                            status: str, published_at: str = "") -> None:
    execute(
        "UPDATE rebate_months SET status = ?, published_at = ? "
        "WHERE run_id = ? AND carrier = ? AND month = ?",
        (status, published_at, run_id, carrier, month),
    )


def replace_rebate_lines(run_id: str, rows_in: list[dict]) -> None:
    """按运行整体重算返利分摊：先删后插，重跑不会叠加（幂等关键）。"""
    with session() as conn:
        conn.execute("DELETE FROM rebate_lines WHERE run_id = ?", (run_id,))
        conn.executemany(
            "INSERT INTO rebate_lines (run_id, carrier, month, waybill_no, base_amount, "
            "weight_share, rebate_amount, is_absorbing, codes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    run_id, row["carrier"], row["month"], row["waybill_no"],
                    row["base_amount"], row["weight_share"], row["rebate_amount"],
                    int(row["is_absorbing"]), row.get("codes", ""),
                )
                for row in rows_in
            ],
        )


def rebate_lines(run_id: str, carrier: str = "", month: str = "") -> list[dict]:
    sql = "SELECT * FROM rebate_lines WHERE run_id = ?"
    params: list = [run_id]
    if carrier:
        sql += " AND carrier = ?"
        params.append(carrier)
    if month:
        sql += " AND month = ?"
        params.append(month)
    sql += " ORDER BY month, carrier, waybill_no"
    return rows(sql, tuple(params))
