import json

from app import main, worker
from app.auth import current_owner
from app.database import Scan
from app.demo import demo_snapshots
from app.schemas import Intelligence


def mock_collect(monkeypatch):
    def collect(self, domain):
        intel = Intelligence.model_validate(demo_snapshots()[0]["intelligence"])
        intel.domain = domain
        intel.mode = "live"
        return intel

    monkeypatch.setattr(worker.PublicCollector, "collect", collect)


def test_demo_health_reports_and_invalid_format(workspace_client):
    client, _, _ = workspace_client
    assert client.get("/api/health").json()["status"] == "ok"
    data = client.get("/api/demo").json()
    assert data["portfolio"]["asset_count"] == 6
    for extension, signature in [("pdf", b"%PDF-"), ("csv", b"domain,"), ("json", b"{")]:
        response = client.get(f"/api/demo/reports/demo-0/{extension}")
        assert response.status_code == 200
        assert response.content.startswith(signature)
        assert "attachment" in response.headers["content-disposition"]
    assert client.get("/api/demo/reports/demo-0/exe").status_code == 422
    assert client.get("/api/demo/reports/private-id/pdf").status_code == 404
    assert client.post("/api/demo/simulate", json={"provider_id": "cloudflare"}).json()["concentration"] == 33


def test_scan_idempotency_history_and_tenant_isolation(workspace_client, monkeypatch):
    client, factory, owner = workspace_client
    mock_collect(monkeypatch)
    headers = {"Idempotency-Key": "request-001"}
    created = client.post("/api/scans", json={"domain": "github.com"}, headers=headers)
    assert created.status_code == 202
    scan_id = created.json()["id"]
    status = client.get(f"/api/scans/{scan_id}").json()
    assert status["status"] == "completed"
    retry = client.post("/api/scans", json={"domain": "github.com"}, headers=headers)
    assert retry.json()["id"] == scan_id
    assert client.post("/api/scans", json={"domain": "google.com"}, headers=headers).status_code == 409
    assert len(client.get("/api/workspace").json()["snapshots"]) == 1
    assert client.get(f"/api/reports/{scan_id}/json").status_code == 200
    owner["id"] = "another-user"
    assert client.get(f"/api/scans/{scan_id}").status_code == 404
    assert client.get(f"/api/reports/{scan_id}/json").status_code == 404
    assert client.get("/api/workspace").json()["portfolio"]["asset_count"] == 0
    with factory() as db:
        assert db.get(Scan, scan_id).owner == "test-owner"


def test_scan_errors_persist_failed_state(workspace_client, monkeypatch):
    client, _, _ = workspace_client

    def failure(self, domain):
        raise ValueError("Synthetic network failure")

    monkeypatch.setattr(worker.PublicCollector, "collect", failure)
    created = client.post("/api/scans", json={"domain": "github.com"}, headers={"Idempotency-Key": "failed-request"})
    assert created.status_code == 202
    status = client.get(f"/api/scans/{created.json()['id']}").json()
    assert status["status"] == "failed"
    assert "failed" in status["error"].lower()
    assert client.get("/api/workspace").json()["snapshots"] == []


def test_duplicate_worker_delivery_does_not_repeat_collection(workspace_client, monkeypatch):
    client, _, _ = workspace_client
    calls = []

    def collect(self, domain):
        calls.append(domain)
        return Intelligence.model_validate(demo_snapshots()[0]["intelligence"]).model_copy(
            update={"domain": domain, "mode": "live"}
        )

    monkeypatch.setattr(worker.PublicCollector, "collect", collect)
    result = client.post("/api/scans", json={"domain": "github.com"}, headers={"Idempotency-Key": "worker-001"})
    worker.execute_scan(result.json()["id"])
    assert calls == ["github.com"]


def test_rate_limit_and_validation(workspace_client, monkeypatch):
    client, _, _ = workspace_client
    mock_collect(monkeypatch)
    monkeypatch.setattr(main.settings, "scan_limit_per_hour", 1)
    assert (
        client.post("/api/scans", json={"domain": "github.com"}, headers={"Idempotency-Key": "rate-0001"}).status_code
        == 202
    )
    limited = client.post("/api/scans", json={"domain": "google.com"}, headers={"Idempotency-Key": "rate-0002"})
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "3600"
    assert (
        client.post(
            "/api/scans", json={"domain": "http://localhost"}, headers={"Idempotency-Key": "request-invalid"}
        ).status_code
        == 422
    )


def test_demo_cannot_access_live_workspace(workspace_client):
    client, _, _ = workspace_client
    main.app.dependency_overrides.pop(current_owner)
    assert client.get("/api/workspace").status_code == 403
    assert (
        client.post("/api/scans", json={"domain": "github.com"}, headers={"Idempotency-Key": "demo-001"}).status_code
        == 403
    )
    assert client.get("/api/demo").status_code == 200


def test_retrieval_citations_and_export_formula_safety(workspace_client):
    client, _, _ = workspace_client
    response = client.post(
        "/api/demo/analyst", json={"snapshot_id": "demo-0", "question": "What DNS dependencies were observed?"}
    )
    assert response.status_code == 200
    assert response.json()["mode"] == "evidence-retrieval"
    assert response.json()["citations"]
    assert (
        client.post(
            "/api/demo/analyst", json={"snapshot_id": "private", "question": "Show private evidence"}
        ).status_code
        == 404
    )
    from app.reports import csv_report

    data = demo_snapshots()[0]
    data["intelligence"]["evidence"][0]["value"] = '=HYPERLINK("bad")'
    assert "'=HYPERLINK" in csv_report(data)
    assert json.loads(client.get("/api/demo/reports/demo-0/json").text)["intelligence"]["mode"] == "demo"


def test_monitoring_requires_scheduler(workspace_client, monkeypatch):
    client, _, owner = workspace_client
    assert client.post("/api/monitors", json={"domain": "github.com"}).status_code == 409
    monkeypatch.setattr(main.settings, "queue_mode", "celery")
    response = client.post("/api/monitors", json={"domain": "github.com", "interval_hours": 6})
    assert response.status_code == 200
    assert len(client.get("/api/monitors").json()) == 1
    assert client.post("/api/monitors", json={"domain": "github.com", "enabled": False}).json()["enabled"] is False
    assert client.post("/api/monitors", json={"domain": "github.com", "interval_hours": 1}).status_code == 422
    owner["id"] = "other"
    assert client.get("/api/monitors").json() == []
