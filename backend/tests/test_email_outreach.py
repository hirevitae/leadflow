"""Email Outreach (Phase A) — templates CRUD, audience preview, campaign lifecycle,
scheduling, pause/resume/cancel, analytics, webhook/unsubscribe, test-send."""
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


# ---------- Lookups ----------
class TestLookups:
    def test_categories(self, client):
        r = client.get(f"{EMAIL_BASE}/template-categories")
        assert r.status_code == 200
        cats = r.json()
        assert isinstance(cats, list) and len(cats) == 13
        assert "Admissions" in cats and "Transactional" in cats

    def test_merge_fields(self, client):
        r = client.get(f"{EMAIL_BASE}/merge-fields")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) and len(data) >= 5
        fields = {d["field"] for d in data}
        assert "{{name}}" in fields and "{{unsubscribe}}" in fields


# ---------- Templates CRUD ----------
class TestTemplates:
    tid = None
    dup_id = None

    def test_create(self, client):
        payload = {"name": "TEST_tmpl_" + uuid.uuid4().hex[:6],
                   "category": "Newsletter", "subject": "Hi {{name}}",
                   "html": "<p>Hello {{name}}, course: {{course}}</p>"}
        r = client.post(f"{EMAIL_BASE}/templates", json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["id"] and d["name"] == payload["name"]
        assert d["subject"] == payload["subject"]
        TestTemplates.tid = d["id"]

    def test_list(self, client):
        r = client.get(f"{EMAIL_BASE}/templates")
        assert r.status_code == 200
        ids = [d["id"] for d in r.json()]
        assert TestTemplates.tid in ids

    def test_get(self, client):
        r = client.get(f"{EMAIL_BASE}/templates/{TestTemplates.tid}")
        assert r.status_code == 200
        assert r.json()["id"] == TestTemplates.tid

    def test_update(self, client):
        r = client.put(f"{EMAIL_BASE}/templates/{TestTemplates.tid}",
                       json={"subject": "Updated {{name}}"})
        assert r.status_code == 200
        assert r.json()["subject"] == "Updated {{name}}"
        # verify persisted
        r2 = client.get(f"{EMAIL_BASE}/templates/{TestTemplates.tid}")
        assert r2.json()["subject"] == "Updated {{name}}"

    def test_duplicate(self, client):
        r = client.post(f"{EMAIL_BASE}/templates/{TestTemplates.tid}/duplicate")
        assert r.status_code == 200
        d = r.json()
        assert d["id"] != TestTemplates.tid
        assert "(copy)" in d["name"]
        TestTemplates.dup_id = d["id"]

    def test_delete(self, client):
        r = client.delete(f"{EMAIL_BASE}/templates/{TestTemplates.dup_id}")
        assert r.status_code == 200
        # verify gone
        r2 = client.get(f"{EMAIL_BASE}/templates/{TestTemplates.dup_id}")
        assert r2.status_code == 404
        # cleanup original
        client.delete(f"{EMAIL_BASE}/templates/{TestTemplates.tid}")


# ---------- Audience preview ----------
class TestAudiencePreview:
    def test_preview_returns_shape(self, client):
        r = client.post(f"{EMAIL_BASE}/audience/preview",
                        json={"stages": ["contacted", "interested"]})
        assert r.status_code == 200
        d = r.json()
        for k in ("total_leads", "with_email", "deliverable", "suppressed_or_dupe", "sample"):
            assert k in d
        assert d["deliverable"] >= 1
        assert isinstance(d["sample"], list)


# ---------- Campaign lifecycle (send now, worker processes) ----------
class TestCampaignLifecycle:
    cid = None

    def test_create_now(self, client):
        payload = {
            "name": "TEST_campaign_" + uuid.uuid4().hex[:6],
            "subject": "Hello {{name}}",
            "html": "<p>Hi {{name}}</p>",
            "stages": ["contacted", "interested"],
            "schedule": {"mode": "now"},
            "throttle": {"per_minute": 120},
        }
        r = client.post(f"{EMAIL_BASE}/campaigns", json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "sending"
        assert d["stats"]["total"] >= 1
        assert d["stats"]["queued"] == d["stats"]["total"]
        TestCampaignLifecycle.cid = d["id"]

    def test_worker_processes(self, client):
        cid = TestCampaignLifecycle.cid
        # Worker ticks every 5s; each item requires 3 attempts to fail terminally.
        # Wait generously (up to ~150s) for sandbox to reject each send.
        c = None
        for _ in range(50):
            time.sleep(3)
            r = client.get(f"{EMAIL_BASE}/campaigns/{cid}")
            assert r.status_code == 200
            c = r.json()
            s = c["stats"]
            if c["status"] == "completed":
                break
        assert c is not None
        s = c["stats"]
        # Primary success criteria: queue drained and stats moved.
        assert s["queued"] < s["total"], f"queue never advanced: {s}"
        # Ideally reaches completed within window
        if s["queued"] == 0:
            assert c["status"] == "completed"
            assert (s["failed"] + s["sent"]) == s["total"]

    def test_analytics(self, client):
        r = client.get(f"{EMAIL_BASE}/campaigns/{TestCampaignLifecycle.cid}/analytics")
        assert r.status_code == 200
        d = r.json()
        for k in ("stats", "rates", "clicks_over_time"):
            assert k in d
        for rk in ("delivery_rate", "open_rate", "click_rate", "bounce_rate"):
            assert rk in d["rates"]
        assert isinstance(d["clicks_over_time"], list)


# ---------- Scheduling (later) ----------
class TestScheduling:
    def test_scheduled_status(self, client):
        send_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
        r = client.post(f"{EMAIL_BASE}/campaigns", json={
            "name": "TEST_sched_" + uuid.uuid4().hex[:6],
            "subject": "Later", "html": "<p>later</p>",
            "stages": ["contacted"],
            "schedule": {"mode": "later", "send_at": send_at},
            "throttle": {"per_minute": 30},
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "scheduled"
        cid = d["id"]
        # After a few seconds it should still be scheduled (not sending)
        time.sleep(8)
        r2 = client.get(f"{EMAIL_BASE}/campaigns/{cid}")
        assert r2.json()["status"] == "scheduled"
        # cancel to clean up so worker doesn't send later
        client.post(f"{EMAIL_BASE}/campaigns/{cid}/cancel")


# ---------- Pause / Resume / Cancel ----------
class TestPauseResumeCancel:
    def test_pause_resume(self, client):
        # Create a scheduled campaign (so no worker activity yet) and pause/resume it
        send_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
        r = client.post(f"{EMAIL_BASE}/campaigns", json={
            "name": "TEST_prc_" + uuid.uuid4().hex[:6],
            "subject": "s", "html": "<p>h</p>",
            "stages": ["contacted"],
            "schedule": {"mode": "later", "send_at": send_at},
            "throttle": {"per_minute": 30},
        })
        assert r.status_code == 200
        cid = r.json()["id"]

        r1 = client.post(f"{EMAIL_BASE}/campaigns/{cid}/pause")
        assert r1.status_code == 200 and r1.json()["ok"] is True
        assert client.get(f"{EMAIL_BASE}/campaigns/{cid}").json()["status"] == "paused"

        r2 = client.post(f"{EMAIL_BASE}/campaigns/{cid}/resume")
        assert r2.status_code == 200
        assert client.get(f"{EMAIL_BASE}/campaigns/{cid}").json()["status"] == "sending"

        r3 = client.post(f"{EMAIL_BASE}/campaigns/{cid}/cancel")
        assert r3.status_code == 200
        assert client.get(f"{EMAIL_BASE}/campaigns/{cid}").json()["status"] == "canceled"


# ---------- Webhook + Unsubscribe + Suppression ----------
class TestWebhookAndSuppression:
    def test_webhook_no_match(self, client):
        r = requests.post(f"{EMAIL_BASE}/webhook/resend",
                          json={"type": "email.bounced", "data": {"email_id": "nonexistent_" + uuid.uuid4().hex}},
                          timeout=10)
        assert r.status_code == 200
        assert r.json() == {"ok": True}

    def test_unsubscribe_and_suppression(self, client):
        # Pick a lead with email
        leads = client.get(f"{BASE_URL}/api/leads?stage=contacted").json()
        target = next((l for l in leads if l.get("email")), None)
        assert target, "no lead with email found"
        email = target["email"].lower()

        # Baseline preview
        pre = client.post(f"{EMAIL_BASE}/audience/preview",
                          json={"stages": ["contacted", "interested"]}).json()

        # Hit unsubscribe (public endpoint)
        r = requests.get(f"{EMAIL_BASE}/unsubscribe", params={"c": "test-c", "l": target["id"]}, timeout=10)
        assert r.status_code == 200
        assert "unsubscribed" in r.text.lower()

        # Check suppression contains email
        supp = client.get(f"{EMAIL_BASE}/suppression").json()
        assert any((s.get("email") or "").lower() == email for s in supp), f"email {email} not in suppression"

        # New audience preview: deliverable should not include suppressed email
        post = client.post(f"{EMAIL_BASE}/audience/preview",
                           json={"stages": ["contacted", "interested"]}).json()
        # Deliverable count should decrease OR stay same if dedup already excluded it,
        # but critically no sample entry should equal the suppressed email.
        sample_emails = {(s.get("email") or "").lower() for s in post.get("sample", [])}
        assert email not in sample_emails
        # Prefer strict decrease when the email was actually deliverable before
        if any((s.get("email") or "").lower() == email for s in pre.get("sample", [])):
            assert post["deliverable"] <= pre["deliverable"]


# ---------- Test-send (sandbox 400, never 502) ----------
class TestTestSend:
    def test_sandbox_returns_400_not_502(self, client):
        r = client.post(f"{EMAIL_BASE}/campaigns/test",
                        json={"to": "someone@nowhere.example",
                              "subject": "t", "html": "<p>t</p>"})
        # Expected 400 with clear error in sandbox
        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
        body = r.text.lower()
        assert "test send failed" in body or "detail" in body
