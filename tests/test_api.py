"""Basic integration tests for the REST API endpoints."""
import json
import os
import sys
import time
import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("FLASK_ENV", "testing")


@pytest.fixture(scope="module")
def app():
    from app import app as flask_app
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    yield flask_app


@pytest.fixture(scope="module")
def client(app):
    return app.test_client()


@pytest.fixture(scope="module")
def api_token(client):
    """Register a test tenant and get an API token."""
    from modules import db
    slug = f"test_{int(time.time())}"
    tenant_id = db.create_tenant(f"Test Co {slug}", slug)
    from werkzeug.security import generate_password_hash
    user_id = db.create_user(tenant_id, f"owner_{slug}",
                              f"owner_{slug}@test.com",
                              generate_password_hash("Test@1234"), "owner")

    resp = client.post("/api/v1/auth/login",
                       json={"email": f"owner_{slug}@test.com", "password": "Test@1234"},
                       content_type="application/json")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    data = resp.get_json()
    return data["token"]


# ── Auth ──────────────────────────────────────────────────────────────────────

class TestAuth:
    def test_login_bad_password(self, client):
        resp = client.post("/api/v1/auth/login",
                           json={"email": "nobody@test.com", "password": "wrong"},
                           content_type="application/json")
        assert resp.status_code == 401

    def test_login_missing_fields(self, client):
        resp = client.post("/api/v1/auth/login", json={},
                           content_type="application/json")
        assert resp.status_code == 400

    def test_me_no_token(self, client):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_me_with_token(self, client, api_token):
        resp = client.get("/api/v1/auth/me",
                          headers={"Authorization": f"Bearer {api_token}"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "user" in data
        assert "tenant" in data


# ── Clients ───────────────────────────────────────────────────────────────────

class TestClients:
    def test_list_empty(self, client, api_token):
        resp = client.get("/api/v1/clients",
                          headers={"Authorization": f"Bearer {api_token}"})
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_list_unauthenticated(self, client):
        resp = client.get("/api/v1/clients")
        assert resp.status_code == 401


# ── Settings ──────────────────────────────────────────────────────────────────

class TestSettings:
    def test_get_settings(self, client, api_token):
        resp = client.get("/api/v1/settings",
                          headers={"Authorization": f"Bearer {api_token}"})
        assert resp.status_code == 200

    def test_put_settings(self, client, api_token):
        resp = client.put("/api/v1/settings",
                          json={"company_name": "Test Corp"},
                          headers={"Authorization": f"Bearer {api_token}"},
                          content_type="application/json")
        assert resp.status_code == 200

        # Verify persisted
        resp2 = client.get("/api/v1/settings",
                           headers={"Authorization": f"Bearer {api_token}"})
        assert resp2.get_json().get("company_name") == "Test Corp"


# ── Health ────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] in ("ok", "degraded")
        assert "checks" in data


# ── Files ─────────────────────────────────────────────────────────────────────

class TestFiles:
    def test_list_files(self, client, api_token):
        resp = client.get("/api/v1/files",
                          headers={"Authorization": f"Bearer {api_token}"})
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_download_missing(self, client, api_token):
        resp = client.get("/api/v1/files/nonexistent.pdf",
                          headers={"Authorization": f"Bearer {api_token}"})
        assert resp.status_code == 404


# ── Billing ───────────────────────────────────────────────────────────────────

class TestBilling:
    def test_new_tenant_gets_trial(self, client, api_token):
        from modules import billing
        from modules import db
        resp = client.get("/api/v1/auth/me",
                          headers={"Authorization": f"Bearer {api_token}"})
        tenant_id = resp.get_json()["tenant"]["id"]
        sub = billing.get_subscription(tenant_id)
        # New tenants start on trial
        assert sub["status"] in ("trial", "active", "free")
        # Effective plan during trial should be pro
        plan = billing.effective_plan(tenant_id)
        assert plan in ("pro", "free")

    def test_check_limit_free(self, client, api_token):
        from modules import billing
        resp = client.get("/api/v1/auth/me",
                          headers={"Authorization": f"Bearer {api_token}"})
        tenant_id = resp.get_json()["tenant"]["id"]
        # Force to free plan for limit test
        billing.update_subscription(tenant_id, "free", "active")
        allowed, used, limit = billing.check_limit(tenant_id, "clients")
        assert limit == billing.PLANS["free"]["limits"]["clients"]


# ── Audit Chain ───────────────────────────────────────────────────────────────

class TestAuditChain:
    def test_chain_integrity(self, client, api_token):
        from modules import audit_chain
        from modules import db
        resp = client.get("/api/v1/auth/me",
                          headers={"Authorization": f"Bearer {api_token}"})
        tenant_id = resp.get_json()["tenant"]["id"]

        # Write some entries
        audit_chain.add(tenant_id, "127.0.0.1", "tester", "TEST_ACTION", "detail1")
        audit_chain.add(tenant_id, "127.0.0.1", "tester", "TEST_ACTION", "detail2")

        result = audit_chain.verify_chain(tenant_id)
        assert result["ok"] is True
        assert result["entries"] >= 2
