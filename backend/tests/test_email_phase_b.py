"""Email Outreach (Phase B) — template versioning, A/B testing, recurrence."""
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://batch-contact.preview.emergentagent.com").rstrip("/")
EMAIL_BASE = f"{BASE_URL}/api/email"


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "admin@leadflow.com", "password": "admin123"}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def client(token):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    return s


# ---------- Template versioning ----------
class TestTemplateVersioning:
    tid = None
    v1_id = None

    def test_create_template(self, client):
        r = client.post(f"{EMAIL_BASE}/templates",
                        json={"name": "TEST_ver_" + uuid.uuid4().hex[:6],
                              "category": "Newsletter",
                              "subject": "v0 subject", "html": "<p>v0</p>"})
        assert r.status_code == 200, r.text
        TestTemplateVersioning.tid = r.json()["id"]

    def test_update_snapshots_v1(self, client):
        # PUT should snapshot previous state as v1
        r = client.put(f"{EMAIL_BASE}/templates/{TestTemplateVersioning.tid}",
                       json={"subject": "v1 subject", "html": "<p>v1</p>"})
        assert r.status_code == 200
        assert r.json()["subject"] == "v1 subject"
        # list versions
        r2 = client.get(f"{EMAIL_BASE}/templates/{TestTemplateVersioning.tid}/versions")
        assert r2.status_code == 200
        versions = r2.json()
        assert isinstance(versions, list) and len(versions) >= 1
        # first snapshot should contain v0 content
        v0_like = [v for v in versions if v.get("subject") == "v0 subject"]
        assert v0_like, f"expected snapshot of v0 subject, got: {versions}"
        TestTemplateVersioning.v1_id = v0_like[0]["id"]
        assert "version_no" in v0_like[0]

    def test_update_snapshots_v2(self, client):
        client.put(f"{EMAIL_BASE}/templates/{TestTemplateVersioning.tid}",
                   json={"subject": "v2 subject", "html": "<p>v2</p>"})
        r = client.get(f"{EMAIL_BASE}/templates/{TestTemplateVersioning.tid}/versions")
        assert r.status_code == 200
        versions = r.json()
        subjects = {v["subject"] for v in versions}
        assert "v0 subject" in subjects and "v1 subject" in subjects
        assert len(versions) >= 2

    def test_restore_version(self, client):
        # restore v0
        r = client.post(f"{EMAIL_BASE}/templates/{TestTemplateVersioning.tid}/versions/{TestTemplateVersioning.v1_id}/restore")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["subject"] == "v0 subject"
        # verify GET reflects restored state
        r2 = client.get(f"{EMAIL_BASE}/templates/{TestTemplateVersioning.tid}")
        assert r2.status_code == 200
        assert r2.json()["subject"] == "v0 subject"


# ---------- A/B testing ----------
class TestAB:
    cid = None

    def test_create_ab_campaign(self, client):
        payload = {
            "name": "TEST_ab_" + uuid.uuid4().hex[:6],
            "template_id": None,
            "subject": "A subject",
            "html": "<p>A</p>",
            "stages": ["contacted", "interested"],
            "schedule": {"mode": "now", "send_at": None, "timezone": "UTC"},
            "throttle": {"per_minute": 120, "business_hours_only": False},
            "ab": {
                "enabled": True,
                "variants": [
                    {"name": "A", "subject": "A subject", "html": "<p>A body</p>"},
                    {"name": "B", "subject": "B subject", "html": "<p>B body</p>"},
                ],
                "test_percent": 40,
                "winner_metric": "click_rate",
                "winner_after_minutes": 0,
            },
            "recurrence": {"enabled": False, "frequency": "weekly"},
        }
        r = client.post(f"{EMAIL_BASE}/campaigns", json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        TestAB.cid = d["id"]
        assert d["ab"]["enabled"] is True
        assert len(d["ab"]["variants"]) == 2
        # status should be testing (worker may not have ticked yet, could still be 'sending' briefly)
        assert d["status"] in ("testing", "sending", "scheduled"), f"unexpected status {d['status']}"

    def test_ab_progresses_to_completion(self, client):
        # Give the worker up to ~90s to send test batch (fails in sandbox), pick winner, release holdback, complete
        final = None
        for _ in range(30):
            time.sleep(3)
            r = client.get(f"{EMAIL_BASE}/campaigns/{TestAB.cid}")
            assert r.status_code == 200
            d = r.json()
            if d["status"] == "completed":
                final = d
                break
        assert final is not None, f"campaign did not complete; last status={d['status']}"
        # winner selected
        assert final["ab"].get("winner_variant_id"), "winner_variant_id should be set after decision"
        # variants should have per-variant stats objects
        for v in final["ab"]["variants"]:
            assert "stats" in v
            # sandbox: sends fail, so counts are 0 — but structure must exist
            for key in ("sent", "opened", "clicked"):
                assert key in v["stats"]


# ---------- Recurrence ----------
class TestRecurrence:
    def test_recurring_campaign_spawns_child(self, client):
        payload = {
            "name": "TEST_rec_" + uuid.uuid4().hex[:6],
            "template_id": None,
            "subject": "Recurring hello",
            "html": "<p>hi</p>",
            "stages": ["contacted"],
            "schedule": {"mode": "now", "send_at": None, "timezone": "UTC"},
            "throttle": {"per_minute": 120, "business_hours_only": False},
            "ab": {"enabled": False, "variants": [], "test_percent": 30,
                   "winner_metric": "click_rate", "winner_after_minutes": 60},
            "recurrence": {"enabled": True, "frequency": "daily"},
        }
        r = client.post(f"{EMAIL_BASE}/campaigns", json=payload)
        assert r.status_code == 200, r.text
        parent = r.json()
        parent_id = parent["id"]
        assert parent.get("recurrence", {}).get("enabled") is True

        # wait for parent to complete + child to spawn
        child = None
        for _ in range(40):
            time.sleep(3)
            r = client.get(f"{EMAIL_BASE}/campaigns")
            assert r.status_code == 200
            campaigns = r.json()
            matches = [c for c in campaigns if c.get("is_recurrence_child_of") == parent_id]
            if matches:
                child = matches[0]
                break
        assert child is not None, "no recurrence child campaign was spawned"
        assert child["status"] == "scheduled"
        # send_at should be in the future
        send_at = child.get("send_at") or child.get("schedule", {}).get("send_at")
        assert send_at, f"child missing send_at: {child}"
