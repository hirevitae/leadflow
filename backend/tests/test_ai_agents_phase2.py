"""Phase 2 AI Agent Studio: QA, unknowns, prompt versioning, per-agent analytics, QA review."""
import os
import pytest
import requests
import uuid
from pathlib import Path

def _load_frontend_env():
    p = Path("/app/frontend/.env")
    if p.exists():
        for line in p.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    return None

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _load_frontend_env()).rstrip("/")
ADMIN = {"email": "admin@leadflow.com", "password": "admin123"}
EXISTING_AGENT_ID = "afde6062-d2f1-4e08-80cf-4bf9fc136f19"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    r = sess.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200, r.text
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        sess.headers.update({"Authorization": f"Bearer {tok}"})
    return sess


@pytest.fixture(scope="module")
def agent_id(s):
    # Verify existing agent
    r = s.get(f"{BASE_URL}/api/agents/{EXISTING_AGENT_ID}", timeout=10)
    if r.status_code == 200:
        return EXISTING_AGENT_ID
    # else create one
    body = {"name": f"TEST_Phase2_{uuid.uuid4().hex[:6]}", "category": "sales",
            "personality": "friendly", "industry": "edtech", "primary_goal": "help",
            "system_prompt": "You are helpful.", "fallback_message": "I do not know."}
    r = s.post(f"{BASE_URL}/api/agents", json=body, timeout=10)
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


# -------- read endpoints shape --------
def test_get_qa(s, agent_id):
    r = s.get(f"{BASE_URL}/api/agents/{agent_id}/qa", timeout=10)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_unknowns(s, agent_id):
    r = s.get(f"{BASE_URL}/api/agents/{agent_id}/unknowns", timeout=10)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_prompt_versions(s, agent_id):
    r = s.get(f"{BASE_URL}/api/agents/{agent_id}/prompt-versions", timeout=10)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_calls(s, agent_id):
    r = s.get(f"{BASE_URL}/api/agents/{agent_id}/calls", timeout=10)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_analytics(s, agent_id):
    r = s.get(f"{BASE_URL}/api/agents/{agent_id}/analytics", timeout=10)
    assert r.status_code == 200
    d = r.json()
    for k in ("chats", "calls", "knowledge_docs", "unknown_questions",
             "avg_confidence", "grounded_rate", "outcomes", "top_questions"):
        assert k in d, f"missing analytics field {k}"
    assert isinstance(d["top_questions"], list)
    assert isinstance(d["outcomes"], dict)


# -------- QA add + appears in listings --------
def test_add_qa_and_appears(s, agent_id):
    q = f"TEST_Q_{uuid.uuid4().hex[:6]} what is the phase-2 fee?"
    a = "The phase-2 fee is INR 12345."
    r = s.post(f"{BASE_URL}/api/agents/{agent_id}/qa", json={"question": q, "answer": a}, timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    # appears in /qa
    qa = s.get(f"{BASE_URL}/api/agents/{agent_id}/qa", timeout=10).json()
    assert any(q[:30] in (d.get("title") or "") or a in (d.get("content") or "") for d in qa)
    # appears in /knowledge
    kn = s.get(f"{BASE_URL}/api/agents/{agent_id}/knowledge", timeout=10).json()
    assert any(d.get("type") == "qa" for d in kn)


def test_add_qa_validation(s, agent_id):
    r = s.post(f"{BASE_URL}/api/agents/{agent_id}/qa", json={"question": "", "answer": ""}, timeout=10)
    assert r.status_code == 400


# -------- Prompt versioning + rollback --------
def test_prompt_version_and_rollback(s, agent_id):
    # get current agent
    current = s.get(f"{BASE_URL}/api/agents/{agent_id}", timeout=10).json()
    orig_prompt = current.get("system_prompt") or ""
    versions_before = s.get(f"{BASE_URL}/api/agents/{agent_id}/prompt-versions", timeout=10).json()
    n_before = len(versions_before)

    # PUT with modified prompt
    payload = {k: current.get(k) for k in ("name", "category", "personality", "industry", "primary_goal",
                                            "system_prompt", "fallback_message", "voice",
                                            "temperature", "max_tokens")}
    payload = {k: v for k, v in payload.items() if v is not None}
    new_prompt = f"{orig_prompt}\n\n# TEST_MOD {uuid.uuid4().hex[:6]}"
    payload["system_prompt"] = new_prompt
    r = s.put(f"{BASE_URL}/api/agents/{agent_id}", json=payload, timeout=10)
    assert r.status_code == 200, r.text
    assert r.json().get("system_prompt") == new_prompt

    # new version created
    versions_after = s.get(f"{BASE_URL}/api/agents/{agent_id}/prompt-versions", timeout=10).json()
    assert len(versions_after) == n_before + 1
    # newest version stores the *previous* prompt (orig_prompt)
    latest = versions_after[0]
    assert latest.get("system_prompt") == orig_prompt

    # Rollback using that version id
    r = s.post(f"{BASE_URL}/api/agents/{agent_id}/prompt-versions/rollback",
               json={"version_id": latest["id"]}, timeout=10)
    assert r.status_code == 200, r.text
    assert r.json().get("system_prompt") == orig_prompt

    # verify agent restored
    restored = s.get(f"{BASE_URL}/api/agents/{agent_id}", timeout=10).json()
    assert restored.get("system_prompt") == orig_prompt


# -------- Unknown recording via chat, resolve, dismiss (fresh agent so KB doesn't shadow) --------
@pytest.fixture(scope="module")
def unk_agent(s):
    body = {"name": f"TEST_UNK_{uuid.uuid4().hex[:6]}", "category": "sales",
            "personality": "friendly", "industry": "edtech", "primary_goal": "help",
            "system_prompt": "You are helpful.", "fallback_message": "I do not know."}
    r = s.post(f"{BASE_URL}/api/agents", json=body, timeout=10)
    assert r.status_code in (200, 201)
    aid = r.json()["id"]
    yield aid
    s.delete(f"{BASE_URL}/api/agents/{aid}")


def test_unknowns_flow(s, unk_agent):
    off_topic = f"TEST_UNK_{uuid.uuid4().hex[:6]} what color is the sky on Mars today?"
    r = s.post(f"{BASE_URL}/api/agents/{unk_agent}/chat",
               json={"message": off_topic}, timeout=45)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("grounded") is False, f"expected not-grounded on empty-KB agent: {body}"

    unk = s.get(f"{BASE_URL}/api/agents/{unk_agent}/unknowns", timeout=10).json()
    match = [u for u in unk if off_topic.lower() in (u.get("question") or "")]
    assert match, f"unknown not recorded; sample={unk[:2]}"

    q = match[0]["question"]
    r = s.post(f"{BASE_URL}/api/agents/{unk_agent}/unknowns/resolve",
               json={"question": q, "answer": "The Mars sky is reddish/butterscotch."}, timeout=10)
    assert r.status_code == 200, r.text
    unk2 = s.get(f"{BASE_URL}/api/agents/{unk_agent}/unknowns", timeout=10).json()
    assert not any(q == (u.get("question") or "") for u in unk2)
    qa = s.get(f"{BASE_URL}/api/agents/{unk_agent}/qa", timeout=10).json()
    assert any("Mars" in (d.get("content") or "") or "mars" in (d.get("title") or "").lower() for d in qa)


def test_unknowns_dismiss(s):
    # Use a fresh agent to avoid retrieve() matching prior QA docs
    body = {"name": f"TEST_DIS_{uuid.uuid4().hex[:6]}", "category": "sales",
            "personality": "friendly", "industry": "edtech", "primary_goal": "help",
            "system_prompt": "You are helpful.", "fallback_message": "I do not know."}
    r = s.post(f"{BASE_URL}/api/agents", json=body, timeout=10)
    aid = r.json()["id"]
    try:
        off = f"TEST_DISMISS_{uuid.uuid4().hex[:6]} how many moons does jupiter have?"
        r = s.post(f"{BASE_URL}/api/agents/{aid}/chat", json={"message": off}, timeout=45)
        assert r.status_code == 200
        assert r.json().get("grounded") is False
        unk = s.get(f"{BASE_URL}/api/agents/{aid}/unknowns", timeout=10).json()
        match = [u for u in unk if off.lower() in (u.get("question") or "")]
        assert match, "unknown not recorded"
        q = match[0]["question"]
        r = s.delete(f"{BASE_URL}/api/agents/{aid}/unknowns", params={"question": q}, timeout=10)
        assert r.status_code == 200, r.text
        unk2 = s.get(f"{BASE_URL}/api/agents/{aid}/unknowns", timeout=10).json()
        assert not any(q == (u.get("question") or "") for u in unk2)
    finally:
        s.delete(f"{BASE_URL}/api/agents/{aid}")


# -------- QA Call review --------
def test_call_review(s, agent_id):
    calls = s.get(f"{BASE_URL}/api/agents/{agent_id}/calls", timeout=10).json()
    if not calls:
        pytest.skip("No calls exist for agent — cannot test review")
    call_id = calls[0]["id"]
    r = s.post(f"{BASE_URL}/api/agents/{agent_id}/calls/{call_id}/review",
               json={"rating": 4, "flagged": True, "note": "TEST_review_note"}, timeout=10)
    assert r.status_code == 200, r.text
    calls2 = s.get(f"{BASE_URL}/api/agents/{agent_id}/calls", timeout=10).json()
    target = next((c for c in calls2 if c["id"] == call_id), None)
    assert target is not None
    assert target.get("qa_reviewed") is True
    assert target.get("qa_rating") == 4
    assert target.get("qa_flagged") is True


def test_call_review_not_found(s, agent_id):
    r = s.post(f"{BASE_URL}/api/agents/{agent_id}/calls/does-not-exist/review",
               json={"rating": 3}, timeout=10)
    assert r.status_code == 404
