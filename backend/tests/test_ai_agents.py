"""Phase 1 — AI Agent Studio tests: agent CRUD, knowledge base, RAG chat playground,
and lead AI-call integration (scripted fallback + grounded LLM call)."""
import os
import io
import time
import uuid
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]).rstrip("/")
ADMIN = {"email": "admin@leadflow.com", "password": "admin123"}
COUNSELLOR = {"email": "counsellor1@leadflow.com", "password": "test123"}


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def admin_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, r.text
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


@pytest.fixture(scope="module")
def counsellor_client(admin_client):
    # ensure counsellor exists
    admin_client.post(f"{BASE_URL}/api/users",
                      json={"email": COUNSELLOR["email"], "password": COUNSELLOR["password"],
                            "name": "Counsellor One", "role": "counsellor"}, timeout=20)
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json=COUNSELLOR, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"Counsellor login failed: {r.status_code} {r.text}")
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


@pytest.fixture(scope="module")
def created_agents():
    ids = []
    yield ids
    # cleanup
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=30)
    if r.status_code == 200:
        s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        for aid in ids:
            try:
                s.delete(f"{BASE_URL}/api/agents/{aid}", timeout=15)
            except Exception:
                pass


# ---------- Meta ----------
def test_agents_meta(admin_client):
    r = admin_client.get(f"{BASE_URL}/api/agents/meta", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert "personalities" in d and "categories" in d
    assert "professional" in d["personalities"]
    assert "Admission Counsellor" in d["categories"]


# ---------- Agent CRUD ----------
def test_create_list_get_update_agent(admin_client, created_agents):
    payload = {"name": "TEST_Agent_" + uuid.uuid4().hex[:6],
               "description": "test", "category": "Admission Counsellor",
               "personality": "friendly", "language": "english",
               "goal": "help admissions", "temperature": 0.5}
    r = admin_client.post(f"{BASE_URL}/api/agents", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["name"] == payload["name"]
    assert "id" in a
    aid = a["id"]
    created_agents.append(aid)

    # list
    r = admin_client.get(f"{BASE_URL}/api/agents", timeout=15)
    assert r.status_code == 200
    lst = r.json()
    assert any(x["id"] == aid for x in lst)
    assert all("knowledge_count" in x for x in lst)

    # get
    r = admin_client.get(f"{BASE_URL}/api/agents/{aid}", timeout=15)
    assert r.status_code == 200
    assert r.json()["id"] == aid

    # update
    upd = {**payload, "goal": "updated goal", "personality": "consultative"}
    r = admin_client.put(f"{BASE_URL}/api/agents/{aid}", json=upd, timeout=15)
    assert r.status_code == 200
    assert r.json()["goal"] == "updated goal"
    assert r.json()["personality"] == "consultative"


def test_role_scoping(admin_client, counsellor_client, created_agents):
    # counsellor creates own agent
    payload = {"name": "TEST_Cnsl_" + uuid.uuid4().hex[:6], "category": "Custom",
               "personality": "professional", "language": "english"}
    r = counsellor_client.post(f"{BASE_URL}/api/agents", json=payload, timeout=15)
    assert r.status_code == 200
    caid = r.json()["id"]
    created_agents.append(caid)

    # counsellor list only own
    r = counsellor_client.get(f"{BASE_URL}/api/agents", timeout=15)
    assert r.status_code == 200
    ids = [x["id"] for x in r.json()]
    assert caid in ids
    # admin's earlier agents should NOT appear for counsellor
    r_admin = admin_client.get(f"{BASE_URL}/api/agents", timeout=15).json()
    admin_only = [x["id"] for x in r_admin if x["owner_id"] != r.json()[0]["owner_id"]]
    for oid in admin_only:
        assert oid not in ids, f"counsellor should not see admin agent {oid}"


def test_agent_404(admin_client):
    r = admin_client.get(f"{BASE_URL}/api/agents/nonexistent-xyz", timeout=15)
    assert r.status_code == 404


# ---------- Knowledge Base ----------
@pytest.fixture(scope="module")
def trained_agent(admin_client, created_agents):
    payload = {"name": "TEST_KB_Agent_" + uuid.uuid4().hex[:6],
               "category": "Admission Counsellor", "personality": "friendly",
               "language": "english", "goal": "answer fee & demo queries",
               "fallback": "Sorry, I don't have that information right now."}
    r = admin_client.post(f"{BASE_URL}/api/agents", json=payload, timeout=15)
    assert r.status_code == 200
    aid = r.json()["id"]
    created_agents.append(aid)

    # add text knowledge
    r = admin_client.post(f"{BASE_URL}/api/agents/{aid}/knowledge/text",
                          json={"title": "Fees & Demo",
                                "content": "The course fee is INR 25000. A free demo class is available every Saturday at 10am. Batch duration is 3 months."},
                          timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] and d["chunks"] >= 1 and d["chars"] > 0

    # add file knowledge
    text = b"Refund policy: full refund within 7 days. Certificate provided on completion."
    files = {"file": ("policy.txt", io.BytesIO(text), "text/plain")}
    # requests session with only auth header (no content-type override for multipart)
    hdr = {"Authorization": admin_client.headers["Authorization"]}
    r = requests.post(f"{BASE_URL}/api/agents/{aid}/knowledge/upload", files=files, headers=hdr, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["ok"] and r.json()["chunks"] >= 1

    return aid


def test_knowledge_list_and_delete(admin_client, trained_agent):
    r = admin_client.get(f"{BASE_URL}/api/agents/{trained_agent}/knowledge", timeout=15)
    assert r.status_code == 200
    docs = r.json()
    assert len(docs) >= 2
    for d in docs:
        assert "chunks" in d and "chars" in d and "title" in d

    # delete one (the uploaded file) and verify
    target = next((d for d in docs if d.get("type") == "file"), docs[-1])
    r = admin_client.delete(f"{BASE_URL}/api/agents/{trained_agent}/knowledge/{target['id']}", timeout=15)
    assert r.status_code == 200
    r = admin_client.get(f"{BASE_URL}/api/agents/{trained_agent}/knowledge", timeout=15)
    remaining_ids = [d["id"] for d in r.json()]
    assert target["id"] not in remaining_ids


# ---------- RAG Chat Playground ----------
def test_chat_grounded_answer(admin_client, trained_agent):
    r = admin_client.post(f"{BASE_URL}/api/agents/{trained_agent}/chat",
                          json={"message": "what is the fee and is there a demo?"}, timeout=90)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["grounded"] is True
    assert isinstance(d["confidence"], (int, float))
    assert d["confidence"] > 0
    assert isinstance(d["sources"], list) and len(d["sources"]) >= 1
    assert any("Fees" in s.get("title", "") or "Demo" in s.get("title", "") for s in d["sources"])
    reply = d["reply"].lower()
    # must mention core facts
    assert "25000" in reply or "25,000" in reply
    assert "demo" in reply
    assert "saturday" in reply


def test_chat_off_topic_fallback(admin_client, trained_agent):
    r = admin_client.post(f"{BASE_URL}/api/agents/{trained_agent}/chat",
                          json={"message": "who won the FIFA world cup in 1998?"}, timeout=90)
    assert r.status_code == 200, r.text
    d = r.json()
    reply = d["reply"].lower()
    # should decline / use fallback rather than invent an answer
    assert ("sorry" in reply or "don't have" in reply or "not sure" in reply
            or "connect" in reply or "information" in reply or "unable" in reply
            or "cannot" in reply), f"Expected fallback-ish reply, got: {d['reply']}"


# ---------- Lead call — scripted fallback ----------
@pytest.fixture(scope="module")
def test_lead(admin_client):
    r = admin_client.post(f"{BASE_URL}/api/leads",
                          json={"name": "TEST_AILead_" + uuid.uuid4().hex[:5],
                                "phone": "+919999900000", "email": "ailead@test.com",
                                "course": "Data Science", "source": "manual"}, timeout=15)
    assert r.status_code in (200, 201), r.text
    lid = r.json()["id"]
    yield lid
    try:
        admin_client.delete(f"{BASE_URL}/api/leads/{lid}", timeout=15)
    except Exception:
        pass


def test_lead_call_without_agent_is_mock(admin_client, test_lead):
    r = admin_client.post(f"{BASE_URL}/api/leads/{test_lead}/calls",
                          json={"language": "english"}, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "completed (mock)"
    assert isinstance(d["transcript"], list) and len(d["transcript"]) >= 2
    assert "agent_id" not in d or not d.get("agent_id")


def test_lead_call_with_agent_is_real(admin_client, test_lead, trained_agent):
    r = admin_client.post(f"{BASE_URL}/api/leads/{test_lead}/calls",
                          json={"language": "english", "agent_id": trained_agent}, timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "completed", f"expected real completed, got {d.get('status')}"
    assert d.get("agent_id") == trained_agent
    assert d.get("agent_name")
    assert isinstance(d.get("transcript"), list) and len(d["transcript"]) >= 2
    assert d.get("outcome") in ("interested", "not_interested", "callback", "enrolled")
    assert isinstance(d.get("sources"), list)
    # transcript should reference knowledge facts (fee 25000 OR demo/saturday)
    joined = " ".join(t.get("text", "") for t in d["transcript"]).lower()
    assert ("25000" in joined or "25,000" in joined or "demo" in joined
            or "saturday" in joined), f"transcript missing knowledge facts: {joined[:300]}"
    # confirm NOT the old canned scripted mock text
    assert "completed (mock)" not in d["status"]


def test_lead_stage_may_advance(admin_client, test_lead):
    r = admin_client.get(f"{BASE_URL}/api/leads/{test_lead}", timeout=15)
    assert r.status_code == 200
    lead = r.json()
    # after agent call, stage should be at least 'interested' OR interest_score set
    assert lead.get("stage") in ("interested", "qualified", "enrolled") or lead.get("interest_score") is not None
