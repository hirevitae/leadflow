"""Tests for social publish bug-fix: DB-backed creds, public image endpoint, publish history."""
import os
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
POST_WITH_IMAGE_ID = "b0521a2c-9f7a-4dd9-b47a-425ec8c7aa80"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "admin@leadflow.com", "password": "admin123"}, timeout=15)
    assert r.status_code == 200
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


# --- providers configured ---
def test_facebook_provider_connected(auth):
    r = requests.get(f"{BASE_URL}/api/admin/integrations", headers=auth, timeout=15)
    assert r.status_code == 200
    fb = next(p for p in r.json() if p["provider"] == "facebook")
    assert fb["status"] == "connected", fb


def test_instagram_provider_connected(auth):
    r = requests.get(f"{BASE_URL}/api/admin/integrations", headers=auth, timeout=15)
    ig = next(p for p in r.json() if p["provider"] == "instagram")
    assert ig["status"] == "connected", ig


# --- public image endpoint (no auth) ---
def test_public_image_endpoint_returns_bytes():
    r = requests.get(f"{BASE_URL}/api/social/image/{POST_WITH_IMAGE_ID}", timeout=20)
    assert r.status_code == 200
    assert r.headers["content-type"] in ("image/jpeg", "image/png")
    assert len(r.content) > 1000


def test_public_image_endpoint_404_on_bad_id():
    r = requests.get(f"{BASE_URL}/api/social/image/does-not-exist-xxx", timeout=15)
    assert r.status_code == 404


# --- history endpoint & bug-fix confirmation ---
def test_history_has_entry_with_required_fields(auth):
    r = requests.get(f"{BASE_URL}/api/social/history", headers=auth, timeout=15)
    assert r.status_code == 200
    docs = r.json()
    assert isinstance(docs, list) and len(docs) >= 1
    d = docs[0]
    for k in ("post_id", "topic", "caption", "targets", "results", "published_by", "published_at"):
        assert k in d, f"missing field {k} in history entry: {d}"
    assert isinstance(d["results"], dict)
    assert "facebook" in d["results"] or "instagram" in d["results"]


def test_history_no_placeholder_strings(auth):
    """The bug fix: results must not be 'not_configured' (fb) or 'needs_image_and_keys' (ig)
    when creds+image are present. Real Meta error strings are acceptable."""
    r = requests.get(f"{BASE_URL}/api/social/history", headers=auth, timeout=15)
    docs = r.json()
    # Focus on entries for the seeded image-bearing post
    entries = [d for d in docs if d.get("post_id") == POST_WITH_IMAGE_ID]
    assert entries, "expected at least one history entry for the seeded image post"
    for e in entries:
        results = e["results"]
        fb_r = results.get("facebook")
        ig_r = results.get("instagram")
        # Must NOT be the old placeholder strings
        assert fb_r != "not_configured", f"facebook still returns not_configured: {e}"
        assert ig_r not in ("needs_image_and_keys", "needs_image"), f"instagram returns placeholder: {e}"
        # Should be either a published dict OR a real Meta error string
        for platform, res in (("facebook", fb_r), ("instagram", ig_r)):
            if res is None:
                continue
            if isinstance(res, dict):
                assert res.get("status") == "published"
            else:
                assert isinstance(res, str) and res.startswith("error:"), \
                    f"{platform} result unexpected: {res}"
