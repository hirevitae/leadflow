"""Phase 3 — Voice calling backend tests.
Twilio not connected in env; verify 400s, TwiML shape, handoff/end-detection, callbacks, and audio routes."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

LEAD_ID = "c4bab7bf-663a-48ba-b50c-d86a9635ce2f"
AGENT_ID = "afde6062-d2f1-4e08-80cf-4bf9fc136f19"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": "admin@leadflow.com", "password": "admin123"}, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    return body.get("access_token") or body.get("token")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------------- initiate voice call (auth) ----------------
def test_voice_call_returns_400_when_twilio_not_configured(admin_headers):
    r = requests.post(f"{API}/leads/{LEAD_ID}/voice-call",
                      json={"language": "english", "agent_id": AGENT_ID},
                      headers=admin_headers, timeout=15)
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"
    body = r.json()
    detail = body.get("detail", "")
    assert "twilio" in detail.lower() and ("not configured" in detail.lower() or "configure" in detail.lower()), detail


def test_voice_call_404_when_lead_missing(admin_headers):
    r = requests.post(f"{API}/leads/does-not-exist/voice-call",
                      json={"language": "english"}, headers=admin_headers, timeout=10)
    assert r.status_code == 404


# ---------------- TwiML entry (public webhook) ----------------
def test_twiml_entry_returns_valid_twiml():
    r = requests.post(f"{API}/voice/twiml/entry?cid=anything", timeout=15)
    assert r.status_code == 200, r.text
    xml = r.text
    assert "<Response>" in xml
    assert '<Gather' in xml and 'input="speech"' in xml
    # greeting via <Say> (no ElevenLabs configured)
    assert "<Say" in xml or "<Play>" in xml


# ---------------- TwiML turn: normal AI reply ----------------
def test_twiml_turn_speech_gets_ai_reply():
    r = requests.post(f"{API}/voice/twiml/turn?cid=test",
                      data={"SpeechResult": "how much does the course cost"}, timeout=45)
    assert r.status_code == 200, r.text
    xml = r.text
    assert "<Response>" in xml
    assert "<Say" in xml or "<Play>" in xml
    assert "<Gather" in xml  # next turn prompt
    assert "<Hangup" not in xml


# ---------------- TwiML turn: end-of-conversation ----------------
def test_twiml_turn_end_detected():
    r = requests.post(f"{API}/voice/twiml/turn?cid=test-end",
                      data={"SpeechResult": "no thanks goodbye"}, timeout=45)
    assert r.status_code == 200, r.text
    xml = r.text
    assert "<Hangup" in xml


# ---------------- TwiML turn: silent re-prompt ----------------
def test_twiml_turn_silent_reprompts():
    r = requests.post(f"{API}/voice/twiml/turn?cid=test-silent&silent=1", timeout=15)
    assert r.status_code == 200, r.text
    xml = r.text
    assert "<Gather" in xml
    assert "<Hangup" not in xml


# ---------------- status callback ----------------
def test_voice_status_callback_204():
    r = requests.post(f"{API}/voice/status?cid=nonexistent",
                      data={"CallStatus": "completed"}, timeout=10)
    assert r.status_code == 204


# ---------------- recording callback ----------------
def test_voice_recording_callback_204():
    r = requests.post(f"{API}/voice/recording?cid=nonexistent",
                      data={"RecordingUrl": "http://x", "RecordingSid": "RE1"}, timeout=10)
    assert r.status_code == 204


# ---------------- audio 404s ----------------
def test_voice_audio_404():
    r = requests.get(f"{API}/voice/audio/does-not-exist", timeout=10)
    assert r.status_code == 404


def test_voice_recording_proxy_404(admin_headers):
    r = requests.get(f"{API}/voice/calls/does-not-exist/recording",
                     headers=admin_headers, timeout=10)
    assert r.status_code == 404


# ---------------- integrations schema: twilio has handoff_number ----------------
def test_twilio_integration_has_handoff_number(admin_headers):
    r = requests.get(f"{API}/admin/integrations", headers=admin_headers, timeout=10)
    assert r.status_code == 200, r.text
    data = r.json()
    # find twilio provider
    provs = data if isinstance(data, list) else data.get("providers", [])
    twilio = next((p for p in provs if p.get("provider") == "twilio" or p.get("id") == "twilio"
                   or p.get("name") == "twilio" or p.get("key") == "twilio"), None)
    assert twilio, f"twilio provider not found in {data}"
    fields = twilio.get("fields", [])
    field_keys = [f.get("key") for f in fields]
    assert "handoff_number" in field_keys, f"handoff_number missing; got {field_keys}"
