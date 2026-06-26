"""
Backend tests for LeadFlow CRM P1 features + Settings page.
Covers: team mgmt, RBAC, round-robin, lead assign, bulk dedup, tasks/followups,
email channel, integrations status, config (content/templates/team), bulk outreach.
"""
import os
import io
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@leadflow.com"
ADMIN_PASSWORD = "admin123"
COUNSELLOR_EMAIL = "counsellor1@leadflow.com"
COUNSELLOR_PASSWORD = "test123"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    return r


@pytest.fixture(scope="session")
def admin_token():
    r = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def admin_h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def counsellor_setup(admin_h):
    """Create counsellor if not exists and return its id+token."""
    # find or create
    r = requests.get(f"{API}/users", headers=admin_h, timeout=30)
    assert r.status_code == 200, r.text
    users = r.json()
    cid = None
    for u in users:
        if u["email"] == COUNSELLOR_EMAIL:
            cid = u["id"]
            break
    if not cid:
        r = requests.post(f"{API}/users", headers=admin_h, json={
            "email": COUNSELLOR_EMAIL, "password": COUNSELLOR_PASSWORD,
            "name": "Counsellor One", "role": "counsellor"
        }, timeout=30)
        assert r.status_code in (200, 201), r.text
        cid = r.json()["id"]
    # login
    rl = _login(COUNSELLOR_EMAIL, COUNSELLOR_PASSWORD)
    assert rl.status_code == 200, rl.text
    return {"id": cid, "token": rl.json()["token"], "h": {"Authorization": f"Bearer {rl.json()['token']}"}}


# ==================== Auth + RBAC =====================
class TestAuthAndRBAC:
    def test_admin_login(self, admin_token):
        assert isinstance(admin_token, str) and len(admin_token) > 10

    def test_admin_me_is_admin(self, admin_h):
        r = requests.get(f"{API}/auth/me", headers=admin_h, timeout=30)
        assert r.status_code == 200
        assert r.json()["role"] == "admin"

    def test_counsellor_cannot_list_users(self, counsellor_setup):
        r = requests.get(f"{API}/users", headers=counsellor_setup["h"], timeout=30)
        assert r.status_code == 403

    def test_admin_lists_users(self, admin_h):
        r = requests.get(f"{API}/users", headers=admin_h, timeout=30)
        assert r.status_code == 200
        emails = [u["email"] for u in r.json()]
        assert ADMIN_EMAIL in emails


# ==================== Team Management =====================
class TestTeamMgmt:
    def test_admin_cannot_delete_self(self, admin_h):
        me = requests.get(f"{API}/auth/me", headers=admin_h, timeout=30).json()
        r = requests.delete(f"{API}/users/{me['id']}", headers=admin_h, timeout=30)
        assert r.status_code == 400, r.text

    def test_create_and_delete_user(self, admin_h):
        email = f"TEST_temp_{int(time.time())}@leadflow.com"
        r = requests.post(f"{API}/users", headers=admin_h, json={
            "email": email, "password": "test123", "name": "Temp User", "role": "counsellor"
        }, timeout=30)
        assert r.status_code in (200, 201), r.text
        uid = r.json()["id"]
        rd = requests.delete(f"{API}/users/{uid}", headers=admin_h, timeout=30)
        assert rd.status_code in (200, 204)
        # verify removed
        users = requests.get(f"{API}/users", headers=admin_h, timeout=30).json()
        assert uid not in [u["id"] for u in users]


# ==================== Role-based leads =====================
class TestLeadsRBAC:
    def test_admin_sees_all(self, admin_h):
        r = requests.get(f"{API}/leads", headers=admin_h, timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_counsellor_sees_only_own(self, admin_h, counsellor_setup):
        r = requests.get(f"{API}/leads", headers=counsellor_setup["h"], timeout=30)
        assert r.status_code == 200
        leads = r.json()
        for l in leads:
            assert l.get("owner_id") == counsellor_setup["id"], \
                f"counsellor saw lead not owned by them: {l}"


# ==================== Round-robin =====================
class TestRoundRobin:
    def test_round_robin_rotates(self, admin_h, counsellor_setup):
        # enable
        r = requests.put(f"{API}/config/team", headers=admin_h,
                         json={"round_robin": True}, timeout=30)
        assert r.status_code == 200
        try:
            owners = []
            for i in range(3):
                r = requests.post(f"{API}/leads", headers=admin_h, json={
                    "name": f"TEST_RR_{int(time.time())}_{i}",
                    "phone": f"+9199{int(time.time())%10000:04d}{i:02d}",
                    "source": "test"
                }, timeout=30)
                assert r.status_code in (200, 201), r.text
                owners.append(r.json().get("owner_id"))
            assert counsellor_setup["id"] in owners, f"counsellor never got assigned: {owners}"
        finally:
            requests.put(f"{API}/config/team", headers=admin_h,
                         json={"round_robin": False}, timeout=30)


# ==================== Lead Assign =====================
class TestLeadAssign:
    def test_assign_lead(self, admin_h, counsellor_setup):
        r = requests.post(f"{API}/leads", headers=admin_h, json={
            "name": "TEST_AssignLead", "phone": f"+9188{int(time.time())%100000:05d}", "source": "test"
        }, timeout=30)
        assert r.status_code in (200, 201)
        lid = r.json()["id"]
        ra = requests.post(f"{API}/leads/{lid}/assign", headers=admin_h,
                          json={"owner_id": counsellor_setup["id"]}, timeout=30)
        assert ra.status_code == 200, ra.text
        # verify
        rl = requests.get(f"{API}/leads/{lid}", headers=admin_h, timeout=30)
        assert rl.json()["owner_id"] == counsellor_setup["id"]
        assert rl.json().get("owner_name")
        # activity logged
        ract = requests.get(f"{API}/leads/{lid}/activities", headers=admin_h, timeout=30)
        assert any(a.get("kind") == "assigned" for a in ract.json())


# ==================== Bulk import dedup =====================
class TestBulkImportDedup:
    def test_dedup_on_import(self, admin_h):
        # create one
        ts = int(time.time())
        phone = f"+9177{ts%100000:05d}"
        dup_phone = f"+9188{ts%100000:05d}"
        r = requests.post(f"{API}/leads", headers=admin_h, json={
            "name": "TEST_DedupSeed", "phone": phone, "source": "test"
        }, timeout=30)
        assert r.status_code in (200, 201)
        # CSV with: dup1 = existing-in-DB ; dup2/dup3 = in-file duplicate of each other
        csv = (
            "name,phone,email,source\n"
            f"TEST_dup1,{phone},a@x.com,csv\n"
            f"TEST_dup2,{dup_phone},b@x.com,csv\n"
            f"TEST_dup3,{dup_phone},c@x.com,csv\n"
        )
        files = {"file": ("import.csv", io.BytesIO(csv.encode()), "text/csv")}
        rr = requests.post(f"{API}/leads/bulk-import", headers=admin_h, files=files, timeout=60)
        assert rr.status_code == 200, rr.text
        data = rr.json()
        assert "duplicates" in data, f"response missing 'duplicates': {data}"
        assert data["duplicates"] >= 2, f"expected >=2 dups, got {data['duplicates']}: {data}"


# ==================== Followup Tasks =====================
class TestTasks:
    def test_task_crud_and_overdue(self, admin_h, counsellor_setup):
        # need a lead
        r = requests.post(f"{API}/leads", headers=admin_h, json={
            "name": "TEST_TaskLead", "phone": f"+9166{int(time.time())%100000:05d}", "source": "test"
        }, timeout=30)
        lid = r.json()["id"]
        # past due
        past = "2020-01-01T10:00:00Z"
        rt = requests.post(f"{API}/tasks", headers=admin_h, json={
            "lead_id": lid, "title": "TEST_followup", "due_date": past
        }, timeout=30)
        assert rt.status_code in (200, 201), rt.text
        task = rt.json()
        assert task.get("lead_name") or "lead_name" in task
        tid = task["id"]
        # list shows it
        rl = requests.get(f"{API}/tasks", headers=admin_h, timeout=30)
        assert rl.status_code == 200
        assert any(t["id"] == tid for t in rl.json())
        # mark done
        rp = requests.patch(f"{API}/tasks/{tid}", headers=admin_h, json={"done": True}, timeout=30)
        assert rp.status_code == 200
        assert rp.json().get("done") is True

    def test_counsellor_sees_own_tasks_only(self, counsellor_setup):
        r = requests.get(f"{API}/tasks", headers=counsellor_setup["h"], timeout=30)
        assert r.status_code == 200
        for t in r.json():
            # counsellor should only see tasks they own/created
            assert t.get("owner_id") == counsellor_setup["id"] or \
                   t.get("created_by") == counsellor_setup["id"] or \
                   t.get("user_id") == counsellor_setup["id"], f"unexpected task: {t}"


# ==================== Email channel =====================
class TestEmail:
    def test_email_not_configured(self, admin_h):
        # ensure there's a lead WITH email
        r = requests.post(f"{API}/leads", headers=admin_h, json={
            "name": "TEST_EmailLead", "phone": f"+9155{int(time.time())%100000:05d}",
            "email": "testtarget@x.com", "source": "test"
        }, timeout=30)
        assert r.status_code in (200, 201), r.text
        lid = r.json()["id"]
        rs = requests.post(f"{API}/leads/{lid}/email", headers=admin_h,
                           json={"subject": "s", "body": "b"}, timeout=30)
        assert rs.status_code == 400, rs.text
        body = rs.text.lower()
        assert "not configured" in body or ("resend" in body) or ("email" in body and "config" in body), \
            f"unexpected error message: {rs.text}"

    def test_list_emails_empty(self, admin_h):
        r = requests.get(f"{API}/leads", headers=admin_h, timeout=30)
        if not r.json():
            pytest.skip("no leads")
        lid = r.json()[0]["id"]
        rs = requests.get(f"{API}/leads/{lid}/emails", headers=admin_h, timeout=30)
        assert rs.status_code == 200
        assert isinstance(rs.json(), list)


# ==================== Integrations status =====================
class TestIntegrations:
    def test_status_shape(self, admin_h):
        r = requests.get(f"{API}/integrations/status", headers=admin_h, timeout=30)
        assert r.status_code == 200
        d = r.json()
        # required keys (booleans)
        for k in ["meta_verify", "llm", "whatsapp", "facebook", "instagram", "email"]:
            assert k in d, f"missing key {k}"
            assert isinstance(d[k], bool), f"{k} not bool"
        # per request: meta_verify and llm should be Configured
        assert d["meta_verify"] is True
        assert d["llm"] is True
        # email not configured
        assert d["email"] is False


# ==================== Config: content / templates / team =====================
class TestConfig:
    def test_content_config_roundtrip(self, admin_h):
        r = requests.get(f"{API}/config/content", headers=admin_h, timeout=30)
        assert r.status_code == 200
        orig = r.json()
        kw_field = "search_keywords" if "search_keywords" in orig else "keywords"
        new_kw = list(orig.get(kw_field, []))
        new_kw.append(f"TEST_kw_{int(time.time())}")
        payload = {
            kw_field: new_kw,
            "interval_hours": (orig.get("interval_hours") or 6) + 1,
            "enabled": True,
            "auto_publish": False,
            "search_sources": orig.get("search_sources", ["news"]),
        }
        rp = requests.put(f"{API}/config/content", headers=admin_h, json=payload, timeout=30)
        assert rp.status_code == 200, rp.text
        # reload
        rr = requests.get(f"{API}/config/content", headers=admin_h, timeout=30)
        cfg = rr.json()
        assert payload[kw_field][-1] in cfg[kw_field]
        assert cfg["interval_hours"] == payload["interval_hours"]

    def test_templates_config_roundtrip(self, admin_h):
        r = requests.get(f"{API}/config/templates", headers=admin_h, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "whatsapp_templates" in d and "call_scripts" in d
        custom = list(d["whatsapp_templates"])
        marker = f"TEST_TPL_{int(time.time())}"
        custom.append({"id": "test_tpl", "name": marker, "body": "hello {{name}}"})
        rp = requests.put(f"{API}/config/templates", headers=admin_h,
                          json={"whatsapp_templates": custom, "call_scripts": d["call_scripts"]},
                          timeout=30)
        assert rp.status_code == 200, rp.text
        # whatsapp/templates endpoint reflects saved
        rt = requests.get(f"{API}/whatsapp/templates", headers=admin_h, timeout=30)
        assert rt.status_code == 200
        names = [t.get("name") for t in rt.json()]
        assert marker in names, f"saved template not in /whatsapp/templates: {names}"

    def test_team_config_roundtrip(self, admin_h):
        r = requests.get(f"{API}/config/team", headers=admin_h, timeout=30)
        assert r.status_code == 200
        assert "round_robin" in r.json()


# ==================== Bulk outreach =====================
class TestBulkOutreach:
    def test_bulk_whatsapp(self, admin_h):
        r = requests.post(f"{API}/bulk/whatsapp", headers=admin_h,
                          json={"stage": "new", "template_id": "intro_en"}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "sent" in d

    def test_bulk_calls(self, admin_h):
        r = requests.post(f"{API}/bulk/calls", headers=admin_h,
                          json={"stage": "new", "language": "english"}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "called" in d
