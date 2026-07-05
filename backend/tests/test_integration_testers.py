"""Tests for POST /api/admin/integrations/test — Facebook/Instagram must accurately
report 'invalid' when the saved Meta creds cannot publish (missing scopes / IG id
is actually a Page id). Also confirms GET /api/admin/integrations lists all 8
providers and that whatsapp/email test endpoints don't 500 (structural)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://batch-contact.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@leadflow.com"
ADMIN_PASSWORD = "admin123"

EXPECTED_PROVIDERS = {"whatsapp", "facebook", "instagram", "email", "ai", "twilio", "elevenlabs", "openai"}


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    token = r.json().get("token") or r.json().get("access_token")
    assert token, f"no token in login response: {r.json()}"
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


def _post_test(client, provider):
    return client.post(f"{BASE_URL}/api/admin/integrations/test", json={"provider": provider}, timeout=60)


# --- Facebook: must be invalid with pages_manage_posts guidance ---
def test_facebook_test_returns_invalid_missing_publish_scope(client):
    r = _post_test(client, "facebook")
    assert r.status_code == 200, f"expected 200, got {r.status_code} {r.text[:300]}"
    body = r.json()
    assert body.get("ok") is False, f"facebook ok should be False, got: {body}"
    assert body.get("status") == "invalid", f"facebook status should be 'invalid', got: {body.get('status')}"
    detail = (body.get("detail") or "").lower()
    assert "pages_manage_posts" in detail, f"detail must mention 'pages_manage_posts', got: {body.get('detail')}"


# --- Instagram: must be invalid with IG-business/Page-ID guidance ---
def test_instagram_test_returns_invalid_page_id_not_ig(client):
    r = _post_test(client, "instagram")
    assert r.status_code == 200, f"expected 200, got {r.status_code} {r.text[:300]}"
    body = r.json()
    assert body.get("ok") is False, f"instagram ok should be False, got: {body}"
    assert body.get("status") == "invalid", f"instagram status should be 'invalid', got: {body.get('status')}"
    detail = (body.get("detail") or "").lower()
    # accept either the app's crafted guidance OR a Meta error stating the object doesn't exist
    acceptable_markers = ["not an instagram business", "page id", "instagram_basic", "instagram_content_publish",
                          "does not exist", "unsupported get request"]
    assert any(m in detail for m in acceptable_markers), \
        f"instagram detail must explain IG business / page id issue, got: {body.get('detail')}"


# --- GET /api/admin/integrations lists 8 providers with fb/ig status not-connected ---
def test_list_integrations_reflects_error_status(client):
    # Ensure the two tests above have run (they set meta status). Re-run defensively.
    _post_test(client, "facebook")
    _post_test(client, "instagram")
    r = client.get(f"{BASE_URL}/api/admin/integrations", timeout=30)
    assert r.status_code == 200, f"list failed: {r.status_code} {r.text[:200]}"
    items = r.json()
    assert isinstance(items, list)
    providers = {i["provider"] for i in items}
    assert providers == EXPECTED_PROVIDERS, f"providers mismatch: {providers}"
    by = {i["provider"]: i for i in items}
    for p in ("facebook", "instagram"):
        st = by[p]["status"]
        assert st in ("invalid", "error", "needs_verification"), \
            f"{p} status should reflect failure (invalid/error), got: {st}"
        assert st != "connected", f"{p} must NOT be 'connected'"


# --- Regression: whatsapp / email test endpoints do not 500 (structural) ---
@pytest.mark.parametrize("provider", ["whatsapp", "email"])
def test_other_providers_no_500(client, provider):
    r = _post_test(client, provider)
    # Accept 200 (tester ran) or 400 (not configured). Never 500.
    assert r.status_code in (200, 400), f"{provider} unexpected status {r.status_code}: {r.text[:200]}"
    if r.status_code == 200:
        body = r.json()
        assert "status" in body and body["status"] in ("connected", "invalid")


# --- Optional sanity: endpoint shape returns ok/status/detail/response_time_ms ---
def test_test_endpoint_response_shape(client):
    r = _post_test(client, "facebook")
    assert r.status_code == 200
    body = r.json()
    for k in ("ok", "status", "detail", "response_time_ms"):
        assert k in body, f"missing key '{k}' in response: {body}"
    assert isinstance(body["response_time_ms"], int)
