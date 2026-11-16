"""端到端：样例脏运单 → 采信 → 计费重 → 账单 → 对账 → 导出，以及页面可用。"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from fixtures.expected import AMOUNT_TOTAL, ROWS_IN, ROWS_OK, ROWS_QUARANTINED

from app.main import app
from app.modules.m6_reconcile import service as reconcile


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_sample_flow_end_to_end(pipeline):
    report = reconcile.reconcile(pipeline["run_id"])
    assert report["rows_in"] == ROWS_IN
    assert report["rows_ok"] == ROWS_OK
    assert report["amount_total"] == AMOUNT_TOTAL
    assert report["verdict"]["balanced"] is True


def test_web_pages_return_200(client):
    pages = ["/", "/waybills", "/weights", "/charges", "/reconcile", "/rebates", "/export"]
    for page in pages:
        response = client.get(page)
        assert response.status_code == 200, page
        assert "freightrate" in response.text
    assert len(pages) == 7


def test_api_health(client):
    payload = client.get("/api/health").json()
    assert payload["ok"] is True
    assert payload["display_tz"] == "Asia/Shanghai"
    assert payload["rate_set_version"] == 3


def test_export_endpoints_are_not_empty(client):
    invoice = client.get("/api/export/invoice.csv")
    assert invoice.status_code == 200
    assert invoice.text.strip().splitlines()[0].startswith("waybill_no")

    evidence = client.get("/api/export/evidence.csv")
    assert evidence.status_code == 200
    assert "line_no" in evidence.text.splitlines()[0]

    manifest = client.get("/api/export/manifest.json")
    assert manifest.status_code == 200
    doc = json.loads(manifest.text)
    assert doc["rows"]["input"] == ROWS_IN
    assert len(doc["input_sha256"]) == 64


def test_reconcile_endpoint_balanced(client):
    report = client.get("/api/reconcile").json()["report"]
    assert report["verdict"]["balanced"] is True
    assert report["total"] == AMOUNT_TOTAL


def test_quarantine_endpoints(client):
    payload = client.get("/api/quarantine").json()
    assert payload["metrics"]["quarantined_lines"] == ROWS_QUARANTINED
    body = client.get("/api/quarantine.csv")
    assert body.status_code == 200
    assert body.text.strip().splitlines()[0].startswith("line_no")


def test_rebate_flow_end_to_end(client):
    # 档位随启动种子装载
    tiers = client.get("/api/rebates/tiers").json()["tiers"]
    assert len(tiers) >= 10

    compute = client.post("/api/rebates/compute").json()["result"]
    assert compute["hit_months"] == 3
    assert compute["rebate_total"] == "50.22"

    # 重跑不重复返利
    again = client.post("/api/rebates/compute").json()["result"]
    assert again["rebate_total"] == compute["rebate_total"]
    assert again["rebate_lines"] == compute["rebate_lines"]

    report = client.get("/api/rebates/reconcile").json()["report"]
    assert report["balanced"] is True
    assert report["gross_receivable"] == AMOUNT_TOTAL
    assert report["net_receivable"] == "1470.82"

    # 发布后重算被 409 拒绝
    published = client.post("/api/rebates/publish?carrier=SF&month=2026-04")
    assert published.status_code == 200
    locked = client.post("/api/rebates/compute")
    assert locked.status_code == 409
    assert locked.json()["code"] == "REBATE_PUBLISHED_LOCKED"

    # 撤回后恢复可重算
    assert client.post("/api/rebates/revoke?carrier=SF&month=2026-04").status_code == 200
    assert client.post("/api/rebates/compute").status_code == 200


def test_rebate_publish_requires_balanced_month(client):
    missing = client.post("/api/rebates/publish?carrier=SF&month=2099-01")
    assert missing.status_code == 404
    assert missing.json()["code"] == "REBATE_MONTH_NOT_FOUND"


def test_rebate_csv_and_manifest_include_rebate(client):
    client.post("/api/rebates/compute")
    body = client.get("/api/export/rebate.csv")
    assert body.status_code == 200
    header = body.text.strip().splitlines()[0]
    assert header.startswith("row_kind,carrier,month")
    assert "allocation" in body.text and "month" in body.text

    doc = json.loads(client.get("/api/export/manifest.json").text)
    assert doc["rebate"]["rebate_total"] == "50.22"
    assert doc["rebate"]["net_receivable"] == "1470.82"
    assert doc["rebate"]["balanced"] is True
