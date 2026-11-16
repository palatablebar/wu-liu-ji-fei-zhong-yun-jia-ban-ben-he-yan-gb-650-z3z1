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
    pages = ["/", "/waybills", "/weights", "/charges", "/reconcile", "/export"]
    for page in pages:
        response = client.get(page)
        assert response.status_code == 200, page
        assert "freightrate" in response.text
    assert len(pages) == 6


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
