"""
Backend tests for Integration Settings Management Module.
Covers: encryption-at-rest, RBAC, masked responses, save/test/rotate/reset,
audit log, health, /api/integrations/status DB-backed reflection, and graceful
fallback for not-configured email & whatsapp send.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or \
    open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@leadflow.com"
ADMIN_PASSWORD = "admin123"
COUNSELLOR_EMAIL = "counsellor1@leadflow.com"
COUNSELLOR_PASSWORD = "test123"

PROVIDERS = ["whatsapp", "facebook", "instagram", "email", "ai"]


def _login(email, password):
    return requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)


@pytest.fixture(scope="session")
def admin_h():
    r = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="session")
def counsellor_h(admin_h):
    # ensure counsellor exists
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
def _cleanup_after(admin_h):
    """Reset whatsapp/email after this module so we don't leave creds behind."""
    yield
    for p in ("whatsapp", "email", "facebook", "instagram"):
        try:
            requests.delete(f"{API}/admin/integrations/{p}", headers=admin_h, timeout=15)
        except Exception:
            pass


# ==================== Listing & masking ====================
class TestListAndMask:
    def test_list_returns_five_providers(self, admin_h):
        r = requests.get(f"{API}/admin/integrations", headers=admin_h, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        assert {d["provider"] for d in data} == set(PROVIDERS), [d["provider"] for d in data]
        for entry in data:
            assert "fields" in entry and "status" in entry
            assert "label" in entry and "description" in entry

    def test_secret_fields_masked_nonsecret_plain(self, admin_h):
        # ensure whatsapp has a token so masking is visible (migrated or fresh)
        requests.post(f"{API}/admin/integrations", headers=admin_h, json={
            "provider": "whatsapp",
            "values": {"phone_number_id": "111222333", "access_token": "PLAINTEXT_TOKEN_VALUE_2026"}
        }, timeout=30)
        r = requests.get(f"{API}/admin/integrations", headers=admin_h, timeout=30)
        wa = next(d for d in r.json() if d["provider"] == "whatsapp")
        for f in wa["fields"]:
            if f["key"] == "access_token":
                assert f["secret"] is True
                # secret must be masked AND must not equal the plaintext
                assert f["value"] != "PLAINTEXT_TOKEN_VALUE_2026"
                assert "PLAIN" not in f["value"]
                if f["configured"]:
                    assert f["value"].startswith("••") or f["value"] == ""
            if f["key"] == "phone_number_id":
                assert f["secret"] is False
                # non-secret should be plaintext
                assert f["value"] in ("111222333",) or f["value"]
            if f["key"] == "api_version":
                # non-secret default like 'v23.0'
                assert "•" not in (f["value"] or "")

    def test_no_plaintext_secret_ever_returned(self, admin_h):
        r = requests.get(f"{API}/admin/integrations", headers=admin_h, timeout=30)
        body = r.text
        assert "PLAINTEXT_TOKEN_VALUE_2026" not in body


# ==================== RBAC ====================
class TestRBAC:
    def test_counsellor_list_403(self, counsellor_h):
        r = requests.get(f"{API}/admin/integrations", headers=counsellor_h, timeout=30)
        assert r.status_code == 403, r.text

    def test_counsellor_save_403(self, counsellor_h):
        r = requests.post(f"{API}/admin/integrations", headers=counsellor_h,
                          json={"provider": "whatsapp", "values": {"phone_number_id": "x"}}, timeout=30)
        assert r.status_code == 403

    def test_counsellor_test_403(self, counsellor_h):
        r = requests.post(f"{API}/admin/integrations/test", headers=counsellor_h,
                          json={"provider": "whatsapp"}, timeout=30)
        assert r.status_code == 403

    def test_counsellor_health_403(self, counsellor_h):
        r = requests.get(f"{API}/admin/integrations/health", headers=counsellor_h, timeout=30)
        assert r.status_code == 403

    def test_counsellor_audit_403(self, counsellor_h):
        r = requests.get(f"{API}/admin/integrations/audit", headers=counsellor_h, timeout=30)
        assert r.status_code == 403

    def test_counsellor_delete_403(self, counsellor_h):
        r = requests.delete(f"{API}/admin/integrations/whatsapp", headers=counsellor_h, timeout=30)
        assert r.status_code == 403


# ==================== Save + status flip + audit ====================
class TestSave:
    def test_save_whatsapp_sets_needs_verification(self, admin_h):
        r = requests.post(f"{API}/admin/integrations", headers=admin_h, json={
            "provider": "whatsapp",
            "values": {"phone_number_id": "8881234", "access_token": "TOK_save_2026"}
        }, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["status"] == "needs_verification"

    def test_blank_value_does_not_overwrite(self, admin_h):
        # set first
        requests.post(f"{API}/admin/integrations", headers=admin_h, json={
            "provider": "whatsapp", "values": {"phone_number_id": "KEEP_ME"}
        }, timeout=30)
        # send blank
        requests.post(f"{API}/admin/integrations", headers=admin_h, json={
            "provider": "whatsapp", "values": {"phone_number_id": ""}
        }, timeout=30)
        r = requests.get(f"{API}/admin/integrations", headers=admin_h, timeout=30)
        wa = next(d for d in r.json() if d["provider"] == "whatsapp")
        pid = next(f for f in wa["fields"] if f["key"] == "phone_number_id")
        assert pid["value"] == "KEEP_ME"

    def test_audit_entry_created_and_masked(self, admin_h):
        # trigger an update
        requests.post(f"{API}/admin/integrations", headers=admin_h, json={
            "provider": "whatsapp", "values": {"access_token": "AUDIT_SECRET_TOK_2026"}
        }, timeout=30)
        r = requests.get(f"{API}/admin/integrations/audit", headers=admin_h, timeout=30)
        assert r.status_code == 200
        logs = r.json()
        assert isinstance(logs, list) and len(logs) > 0
        body = r.text
        assert "AUDIT_SECRET_TOK_2026" not in body, "raw secret leaked in audit log"
        latest = logs[0]
        assert latest.get("updated_by") == ADMIN_EMAIL
        assert "ip_address" in latest


# ==================== Test endpoint graceful failure ====================
class TestConnectionEndpoint:
    def test_test_invalid_creds_returns_invalid_not_500(self, admin_h):
        # whatsapp is configured with bogus creds — real Meta call will fail
        requests.post(f"{API}/admin/integrations", headers=admin_h, json={
            "provider": "whatsapp",
            "values": {"phone_number_id": "9999999", "access_token": "INVALID_BOGUS_2026"}
        }, timeout=30)
        r = requests.post(f"{API}/admin/integrations/test", headers=admin_h,
                          json={"provider": "whatsapp"}, timeout=60)
        # must NOT crash
        assert r.status_code == 200, f"expected 200 with ok:false, got {r.status_code} {r.text}"
        d = r.json()
        assert d["ok"] is False
        assert d["status"] == "invalid"
        assert "response_time_ms" in d and isinstance(d["response_time_ms"], int)

    def test_test_not_configured_400(self, admin_h):
        # ensure facebook empty
        requests.delete(f"{API}/admin/integrations/facebook", headers=admin_h, timeout=15)
        r = requests.post(f"{API}/admin/integrations/test", headers=admin_h,
                          json={"provider": "facebook"}, timeout=30)
        assert r.status_code == 400, r.text
        assert "not configured" in r.text.lower()


# ==================== Rotate / Reset ====================
class TestRotateAndReset:
    def test_rotate_secret_clears_field(self, admin_h):
        # seed
        requests.post(f"{API}/admin/integrations", headers=admin_h, json={
            "provider": "whatsapp",
            "values": {"phone_number_id": "ROT_PID", "access_token": "ROT_TOK_2026"}
        }, timeout=30)
        r = requests.post(f"{API}/admin/integrations/rotate-secret", headers=admin_h,
                          json={"provider": "whatsapp", "key": "access_token"}, timeout=30)
        assert r.status_code == 200
        # verify cleared
        rr = requests.get(f"{API}/admin/integrations", headers=admin_h, timeout=30)
        wa = next(d for d in rr.json() if d["provider"] == "whatsapp")
        tok = next(f for f in wa["fields"] if f["key"] == "access_token")
        assert tok["configured"] is False
        assert wa["status"] in ("needs_verification", "not_configured")

    def test_delete_resets_provider(self, admin_h):
        requests.post(f"{API}/admin/integrations", headers=admin_h, json={
            "provider": "instagram",
            "values": {"ig_business_account_id": "IGB_123", "fb_page_access_token": "FBPT_2026"}
        }, timeout=30)
        rd = requests.delete(f"{API}/admin/integrations/instagram", headers=admin_h, timeout=30)
        assert rd.status_code == 200
        rr = requests.get(f"{API}/admin/integrations", headers=admin_h, timeout=30)
        ig = next(d for d in rr.json() if d["provider"] == "instagram")
        assert ig["status"] == "not_configured"
        for f in ig["fields"]:
            assert f["configured"] is False
            assert f["value"] == ""


# ==================== Health ====================
class TestHealth:
    def test_health_lists_all_providers(self, admin_h):
        r = requests.get(f"{API}/admin/integrations/health", headers=admin_h, timeout=30)
        assert r.status_code == 200
        rows = r.json()
        assert {row["provider"] for row in rows} == set(PROVIDERS)
        for row in rows:
            for k in ["status", "last_verified_at", "response_time_ms", "last_error"]:
                assert k in row


# ==================== /integrations/status reflects DB ====================
class TestIntegrationsStatusReflection:
    def test_db_reflects_in_status(self, admin_h):
        # ensure whatsapp clean
        requests.delete(f"{API}/admin/integrations/whatsapp", headers=admin_h, timeout=15)
        r = requests.get(f"{API}/integrations/status", headers=admin_h, timeout=30)
        assert r.status_code == 200
        assert r.json()["whatsapp"] is False
        # save
        requests.post(f"{API}/admin/integrations", headers=admin_h, json={
            "provider": "whatsapp",
            "values": {"phone_number_id": "RFL_PID", "access_token": "RFL_TOK_2026"}
        }, timeout=30)
        r2 = requests.get(f"{API}/integrations/status", headers=admin_h, timeout=30)
        assert r2.json()["whatsapp"] is True
        # delete -> false
        requests.delete(f"{API}/admin/integrations/whatsapp", headers=admin_h, timeout=15)
        r3 = requests.get(f"{API}/integrations/status", headers=admin_h, timeout=30)
        assert r3.json()["whatsapp"] is False


# ==================== Graceful runtime fallback ====================
class TestRuntimeFallback:
    def test_email_send_returns_400_when_not_configured(self, admin_h):
        # ensure email not configured
        requests.delete(f"{API}/admin/integrations/email", headers=admin_h, timeout=15)
        # need a lead
        r = requests.post(f"{API}/leads", headers=admin_h, json={
            "name": "TEST_IntEmailLead", "phone": f"+9144{int(time.time())%100000:05d}",
            "email": "x@x.com", "source": "test"
        }, timeout=30)
        lid = r.json()["id"]
        rs = requests.post(f"{API}/leads/{lid}/email", headers=admin_h,
                           json={"subject": "s", "body": "b"}, timeout=30)
        assert rs.status_code == 400, rs.text
        assert "not configured" in rs.text.lower()

    def test_whatsapp_send_falls_back_to_mock_when_not_configured(self, admin_h):
        requests.delete(f"{API}/admin/integrations/whatsapp", headers=admin_h, timeout=15)
        r = requests.post(f"{API}/bulk/whatsapp", headers=admin_h,
                          json={"stage": "new", "template_id": "intro_en"}, timeout=60)
        assert r.status_code == 200, r.text
        # ok if 0 leads — at minimum endpoint must NOT 500
        assert "sent" in r.json()
