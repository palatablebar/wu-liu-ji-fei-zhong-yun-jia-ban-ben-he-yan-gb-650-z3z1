"""运行清单：run_id、输入摘要、规则版本、参数、耗时。

run_id 只由输入字节与规则版本决定，因此同一份输入重复导入必得同一个 run_id，
这是幂等重跑的依据。时间戳只写进清单，不参与 run_id。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from app import config


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def make_run_id(input_sha256: str, profile: str | None = None) -> str:
    seed = f"{input_sha256}|{config.RULES_VERSION}|{profile or config.PROFILE}"
    return "RUN-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12].upper()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def local_display(iso_text: str) -> str:
    """把已存的 UTC 文本转成 +08:00 展示。解析失败原样返回。"""
    if not iso_text:
        return ""
    try:
        stamp = datetime.fromisoformat(iso_text.replace("Z", "+00:00"))
    except ValueError:
        return iso_text
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(config.CN_TZ).strftime("%Y-%m-%d %H:%M:%S")


def build(run_row: dict, stage_bits: dict) -> dict:
    """把库里的一行组装成对外清单。"""
    return {
        "run_id": run_row.get("run_id", ""),
        "input_name": run_row.get("input_name", ""),
        "input_sha256": run_row.get("input_sha256", ""),
        "rules_version": run_row.get("rules_version", config.RULES_VERSION),
        "profile": run_row.get("profile", config.PROFILE),
        "rows_in": run_row.get("rows_in", 0),
        "rows_ok": run_row.get("rows_ok", 0),
        "rows_quarantined": run_row.get("rows_quarantined", 0),
        "amount_total": run_row.get("amount_total", "0.00"),
        "rate_digest": run_row.get("rate_digest", ""),
        "stages": (run_row.get("stages") or "").split(",") if run_row.get("stages") else [],
        "notes": run_row.get("notes", ""),
        "created_at": run_row.get("created_at", ""),
        "updated_at": run_row.get("updated_at", ""),
        "generated_at": utc_now_iso(),
        "display_tz": config.DISPLAY_TZ,
        **stage_bits,
    }


def dumps(data) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
