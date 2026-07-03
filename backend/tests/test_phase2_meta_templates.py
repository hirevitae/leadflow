"""
Phase 2 backend tests:
  - /api/admin/integrations/history (admin)
  - /api/admin/integrations/export (encrypted secrets) + audit
  - /api/admin/integrations/import (round-trip restore)
  - /api/admin/integrations/test appends to history

P0 Meta-approved WhatsApp template tests (graceful 400s, never 500):
  - GET  /api/whatsapp/meta-templates
  - POST /api/leads/{id}/whatsapp-template
  - POST /api/bulk/whatsapp-template

Regression:
  - POST /api/bulk/whatsapp        (mock mode 200)
  - POST /api/bulk/calls           (mock mode 200)
"""
import os
import uuid
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]).rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL, ADMIN_PASSWORD = "admin@leadflow.com", "admin123"
COUNSELLOR_EMAIL, COUNSELLOR_PASSWORD = "counsellor1@leadflow.com", "test123"


def _login(email, password):
    return requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)


@pytest.fixture(scope="session")
def admin_h():
    r = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="session")
def counsellor_h(admin_h):
    r = _login(COUNSELLOR_EMAIL, COUNSELLOR_PASSWORD)
    if r.status_code != 200:
        requests.post(f"{API}/users", headers=admin_h, json={
            "email": COUNSELLOR_EMAIL, "password": COUNSELLOR_PASSWORD,
            "name": "Counsellor One", "role": "counsellor"
        }, timeout=30)
        r = _login(COUNSELLOR_EMAIL, COUNSELLOR_PASSWORD)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module", autouse=True)
def _cleanup(admin_h):
    yield
    # Reset whatsapp/email/facebook/instagram, leave AI alone
    for p in ("whatsapp", "email", "facebook", "instagram"):
        try:
            requests.delete(f"{API}/admin/integrations/{p}", headers=admin_h, timeout=15)
        except Exception:
            pass


@pytest.fixture(scope="module")
def sample_lead(admin_h):
    """Create a TEST_ lead for whatsapp-template send tests."""
    payload = {"name": "TEST_phase2_lead",
               "phone": "+919999000111",
               "course": "Python Basics",
               "source": "test"}
    r = requests.post(f"{API}/leads", headers=admin_h, json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    lead = r.json()
    yield lead
    try:
        requests.delete(f"{API}/leads/{lead['id']}", headers=admin_h, timeout=15)
    except Exception:
        pass


# =========================================================================
# Phase 2: History endpoint
# =========================================================================
class TestHistory:
    def test_history_requires_admin(self, counsellor_h):
        r = requests.get(f"{API}/admin/integrations/history?limit=50", headers=counsellor_h, timeout=20)
        assert r.status_code == 403

    def test_history_returns_list(self, admin_h):
        r = requests.get(f"{API}/admin/integrations/history?limit=50", headers=admin_h, timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_test_appends_to_history(self, admin_h):
        # Save dummy whatsapp creds first so /test can run
        requests.post(f"{API}/admin/integrations", headers=admin_h, json={
            "provider": "whatsapp",
            "values": {"phone_number_id": "111", "access_token": "dummy", "api_version": "v23.0"}
        }, timeout=30)
        before = requests.get(f"{API}/admin/integrations/history?provider=whatsapp&limit=200",
                              headers=admin_h, timeout=20).json()
        # Run /test twice
        for _ in range(2):
            r = requests.post(f"{API}/admin/integrations/test", headers=admin_h,
                              json={"provider": "whatsapp"}, timeout=60)
            assert r.status_code == 200, r.text  # graceful even when invalid
            body = r.json()
            assert "status" in body and "response_time_ms" in body
        after = requests.get(f"{API}/admin/integrations/history?provider=whatsapp&limit=200",
                             headers=admin_h, timeout=20).json()
        assert len(after) >= len(before) + 2
        # Validate fields on the most recent entry
        last = after[-1]
        for key in ("provider", "status", "response_time_ms", "detail", "created_at"):
            assert key in last, f"missing key {key} in history entry {last}"
        assert last["provider"] == "whatsapp"


# =========================================================================
# Phase 2: Export / Import (encrypted round-trip)
# =========================================================================
class TestExportImport:
    def test_export_requires_admin(self, counsellor_h):
        r = requests.get(f"{API}/admin/integrations/export", headers=counsellor_h, timeout=20)
        assert r.status_code == 403

    def test_import_requires_admin(self, counsellor_h):
        r = requests.post(f"{API}/admin/integrations/import", headers=counsellor_h,
                          json={"settings": []}, timeout=20)
        assert r.status_code == 403

    def test_export_structure_and_encryption(self, admin_h):
        # Seed a unique secret token so we can detect plaintext leakage
        secret_plain = f"PLAINTOKEN_{uuid.uuid4().hex}"
        requests.post(f"{API}/admin/integrations", headers=admin_h, json={
            "provider": "whatsapp",
            "values": {"phone_number_id": "555", "access_token": secret_plain, "api_version": "v23.0"}
        }, timeout=30)
        r = requests.get(f"{API}/admin/integrations/export", headers=admin_h, timeout=20)
        assert r.status_code == 200
        data = r.json()
        for key in ("version", "exported_at", "note", "settings"):
            assert key in data
        assert isinstance(data["settings"], list) and len(data["settings"]) > 0
        # Plaintext secret MUST NOT appear anywhere in export
        assert secret_plain not in r.text, "plaintext secret leaked into export!"
        # access_token entry: is_encrypted=True, setting_value present and != plaintext
        tok_row = next((s for s in data["settings"]
                        if s["provider"] == "whatsapp" and s["setting_key"] == "access_token"), None)
        assert tok_row is not None
        assert tok_row["is_encrypted"] is True
        assert tok_row["setting_value"] and tok_row["setting_value"] != secret_plain

    def test_export_writes_audit_entry(self, admin_h):
        before = requests.get(f"{API}/admin/integrations/audit", headers=admin_h, timeout=20).json()
        requests.get(f"{API}/admin/integrations/export", headers=admin_h, timeout=20)
        after = requests.get(f"{API}/admin/integrations/audit", headers=admin_h, timeout=20).json()
        # Most recent should be export action
        assert any(a.get("action") == "export" for a in after["items"][:5])
        assert after["total"] >= before["total"] + 1

    def test_roundtrip_export_reset_import_restores(self, admin_h):
        # Seed a unique value
        secret_plain = f"ROUNDTRIP_{uuid.uuid4().hex}"
        requests.post(f"{API}/admin/integrations", headers=admin_h, json={
            "provider": "whatsapp",
            "values": {"phone_number_id": "777", "access_token": secret_plain, "api_version": "v23.0"}
        }, timeout=30)
        # 1. Export
        exp = requests.get(f"{API}/admin/integrations/export", headers=admin_h, timeout=20).json()
        wa_settings = [s for s in exp["settings"] if s["provider"] == "whatsapp"]
        assert len(wa_settings) >= 2
        # 2. Reset (delete) whatsapp
        d = requests.delete(f"{API}/admin/integrations/whatsapp", headers=admin_h, timeout=20)
        assert d.status_code == 200
        # Confirm reset: GET shows not_configured
        lst = requests.get(f"{API}/admin/integrations", headers=admin_h, timeout=20).json()
        wa_card = next(p for p in lst if p["provider"] == "whatsapp")
        assert wa_card["status"] == "not_configured"
        # Status endpoint should reflect
        st = requests.get(f"{API}/integrations/status", headers=admin_h, timeout=20).json()
        assert st.get("whatsapp") is False
        # 3. Import the previously exported settings (only whatsapp ones)
        imp = requests.post(f"{API}/admin/integrations/import", headers=admin_h,
                            json={"settings": wa_settings}, timeout=30)
        assert imp.status_code == 200, imp.text
        body = imp.json()
        assert body.get("ok") is True
        assert body.get("imported") == len(wa_settings)
        # 4. Verify masked value reappears + status reflects configured
        lst2 = requests.get(f"{API}/admin/integrations", headers=admin_h, timeout=20).json()
        wa_card2 = next(p for p in lst2 if p["provider"] == "whatsapp")
        assert wa_card2["status"] == "needs_verification"
        tok_field = next(f for f in wa_card2["fields"] if f["key"] == "access_token")
        assert tok_field["configured"] is True
        assert tok_field["value"].startswith("•") and tok_field["value"] != secret_plain
        # 5. /integrations/status reflects restored
        st2 = requests.get(f"{API}/integrations/status", headers=admin_h, timeout=20).json()
        assert st2.get("whatsapp") is True

    def test_import_writes_audit_entry(self, admin_h):
        # Get current state to import (no-op import)
        exp = requests.get(f"{API}/admin/integrations/export", headers=admin_h, timeout=20).json()
        before = requests.get(f"{API}/admin/integrations/audit", headers=admin_h, timeout=20).json()
        requests.post(f"{API}/admin/integrations/import", headers=admin_h,
                      json={"settings": exp["settings"][:1]}, timeout=20)
        after = requests.get(f"{API}/admin/integrations/audit", headers=admin_h, timeout=20).json()
        assert any(a.get("action") == "import" for a in after["items"][:5])
        assert after["total"] >= before["total"] + 1


# =========================================================================
# P0 Meta-approved WhatsApp Templates  (graceful 400s)
# =========================================================================
class TestMetaTemplates:
    def test_meta_templates_400_when_not_configured(self, admin_h):
        # Clean slate first
        requests.delete(f"{API}/admin/integrations/whatsapp", headers=admin_h, timeout=20)
        r = requests.get(f"{API}/whatsapp/meta-templates", headers=admin_h, timeout=20)
        assert r.status_code == 400, r.text
        assert "not configured" in r.text.lower()

    def test_meta_templates_400_without_business_account_id(self, admin_h):
        # Configure phone_number_id + access_token but NOT business_account_id
        requests.delete(f"{API}/admin/integrations/whatsapp", headers=admin_h, timeout=20)
        requests.post(f"{API}/admin/integrations", headers=admin_h, json={
            "provider": "whatsapp",
            "values": {"phone_number_id": "999", "access_token": "dummy"}
        }, timeout=30)
        r = requests.get(f"{API}/whatsapp/meta-templates", headers=admin_h, timeout=20)
        assert r.status_code == 400
        assert "business account id" in r.text.lower()

    def test_lead_whatsapp_template_400_when_not_configured(self, admin_h, sample_lead):
        # Reset whatsapp first
        requests.delete(f"{API}/admin/integrations/whatsapp", headers=admin_h, timeout=20)
        r = requests.post(f"{API}/leads/{sample_lead['id']}/whatsapp-template",
                          headers=admin_h,
                          json={"template_name": "hello_world", "language": "en_US", "params": ["TestUser"]},
                          timeout=20)
        assert r.status_code == 400, f"expected graceful 400 got {r.status_code} {r.text}"
        assert "not configured" in r.text.lower()

    def test_lead_whatsapp_template_404_for_unknown_lead(self, admin_h):
        # whichever state, unknown lead must 404 (validates endpoint exists & validates)
        r = requests.post(f"{API}/leads/non-existent-lead/whatsapp-template",
                          headers=admin_h,
                          json={"template_name": "x", "language": "en_US", "params": []},
                          timeout=20)
        assert r.status_code == 404

    def test_bulk_whatsapp_template_400_when_not_configured(self, admin_h):
        requests.delete(f"{API}/admin/integrations/whatsapp", headers=admin_h, timeout=20)
        r = requests.post(f"{API}/bulk/whatsapp-template", headers=admin_h, json={
            "stage": "new", "template_name": "hello_world", "language": "en_US", "params": []
        }, timeout=20)
        assert r.status_code == 400
        assert "not configured" in r.text.lower()


# =========================================================================
# Regression: existing bulk endpoints (mock mode)
# =========================================================================
class TestRegression:
    def test_bulk_whatsapp_still_works_mock(self, admin_h):
        # whatsapp not configured -> mock mode 200
        requests.delete(f"{API}/admin/integrations/whatsapp", headers=admin_h, timeout=20)
        templates = requests.get(f"{API}/config/templates", headers=admin_h, timeout=20).json()
        tpl_id = templates["whatsapp_templates"][0]["id"]
        r = requests.post(f"{API}/bulk/whatsapp", headers=admin_h,
                          json={"stage": "new", "template_id": tpl_id}, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        for key in ("ok", "sent", "failed"):
            assert key in data
        assert "stage" in data or "stages" in data
        assert data["ok"] is True

    def test_bulk_calls_still_works_mock(self, admin_h):
        r = requests.post(f"{API}/bulk/calls", headers=admin_h,
                          json={"stage": "new", "language": "english"}, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "called" in data
        assert data.get("ok") is True
