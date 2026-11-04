import json
import time
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.main import create_app
from app.openai_login import AUTH, SCOPES

HEADERS = {"Origin": "http://127.0.0.1:8000", "X-Jarvis-Request": "chat"}


class OpenAIStub:
    def __init__(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.nonce = ""
        self.scope = SCOPES
        self.end = "response.completed"
        self.error = None
        self.subject = "test-subject"
        self.audience = "oaiapp_test"
        self.refreshes = 0
        self.responses = 0
        self.bodies = []
        self.reject_code = False

    def __call__(self, r):
        if r.url.path.endswith("jwks.json"):
            key = jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key(), as_dict=True)
            key.update(kid="test-key", alg="RS256", use="sig")
            return httpx.Response(200, json={"keys": [key]})
        if r.url.path.endswith("oauth/token"):
            if self.reject_code:
                return httpx.Response(400, json={"error": "invalid_grant"})
            form = parse_qs(r.content.decode())
            assert form["client_id"] == ["oaiapp_test"]
            assert "client_secret" not in form
            if form["grant_type"] == ["refresh_token"]:
                self.refreshes += 1
            else:
                assert form["redirect_uri"] == ["http://127.0.0.1:8000/auth/callback"]
                assert len(form["code_verifier"][0]) >= 43
            token = jwt.encode(dict(iss=AUTH, aud=self.audience, sub=self.subject,
                exp=time.time()+3600, nonce=self.nonce, email="test@example.invalid"), self.key,
                algorithm="RS256", headers={"kid": "test-key"})
            return httpx.Response(200, json=dict(id_token=token, access_token="test-access",
                refresh_token="test-refresh-"+str(self.refreshes), expires_in=3600,
                token_type="Bearer", scope=self.scope))
        if r.url.path == "/v1/models":
            assert r.headers["authorization"] == "Bearer test-access"
            return httpx.Response(200, json={"models": [
                dict(slug="gpt-6.1-sol", display_name="GPT-6.1 Sol", visibility="list"),
                dict(slug="hidden", display_name="Hidden", visibility="hidden")]})
        if r.url.path == "/v1/responses":
            self.responses += 1
            body = json.loads(r.content)
            self.bodies.append(body)
            assert body["store"] is False and body["stream"] is True
            assert set(body) == {"model", "input", "store", "stream", "instructions"}
            events = [{"type": "response.output_text.delta", "delta": "Jarvis ist online."}]
            if self.end:
                events.append({"type": self.end, "response": {"error": {"code": self.error}}})
            return httpx.Response(200, text="".join("data: "+json.dumps(e)+"\n\n" for e in events),
                                  headers={"content-type": "text/event-stream"})
        if r.url.path.endswith("openid-configuration"):
            return httpx.Response(200, json={"revocation_endpoint": AUTH+"/revoke"})
        if r.url.path == "/revoke":
            return httpx.Response(200)
        raise AssertionError(str(r.url))


@pytest.fixture
def rig(tmp_path):
    stub = OpenAIStub()
    app = create_app(tmp_path, httpx.AsyncClient(transport=httpx.MockTransport(stub)))
    with TestClient(app, base_url="http://127.0.0.1:8000", headers=HEADERS) as c:
        yield c, app, stub


def begin(c, stub, **body):
    r = c.post("/auth/start", json=body)
    assert r.status_code == 200
    q = parse_qs(urlparse(r.json()["url"]).query)
    stub.nonce = q["nonce"][0]
    return q


def complete(c, q, **params):
    return c.get("/auth/callback", params=dict(state=q["state"][0], code="test-code",
                 client_id="oaiapp_test", **params), follow_redirects=False)


def signin(c, stub):
    q = begin(c, stub)
    assert complete(c, q).status_code == 303


def test_pkce_signin_model_test_and_chat(rig):
    c, app, stub = rig
    q = begin(c, stub)
    assert q["client_id"] == ["dynamic_agent_client"]
    assert q["code_challenge_method"] == ["S256"]
    assert q["ext_agent_host_id"][0].startswith("urn:uuid:")
    assert complete(c, q).status_code == 303
    assert complete(c, q).status_code == 400  # replay
    models = c.get("/api/models").json()["models"]
    assert len(models) == 1
    payload = {"model": "gpt-6.1-sol", "messages": [{"role": "user", "content": "Hallo"}]}
    assert c.post("/api/chat", json=payload).status_code == 409
    assert c.post("/api/test", json={"model": "gpt-6.1-sol"}).json()["reply"] == "Jarvis ist online."
    assert c.post("/api/chat", json=payload).status_code == 200
    assert "test-access" not in c.get("/health").text
    q = begin(c, stub, account="oaiapp_test")
    assert q["client_id"] == ["oaiapp_test"] and "agent_name_hint" not in q


@pytest.mark.parametrize("change", ["state", "cookie", "nonce", "audience", "denied"])
def test_invalid_authorization(rig, change):
    c, app, stub = rig
    q = begin(c, stub)
    extra = {}
    if change == "state": q["state"] = ["wrong"]
    if change == "cookie": c.cookies.clear()
    if change == "nonce": stub.nonce = "wrong"
    if change == "audience": stub.audience = "other"
    if change == "denied": extra["error"] = "access_denied"
    assert complete(c, q, **extra).status_code == 400
    assert not c.get("/health").json()["configured"]


def test_missing_scope_no_inference(rig):
    c, app, stub = rig
    stub.scope = "openid profile email"
    signin(c, stub)
    assert not c.get("/health").json()["configured"]
    assert c.post("/api/test", json={"model": "gpt-6.1-sol"}).status_code == 403
    assert stub.responses == 0
    q = begin(c, stub, account="oaiapp_test", consent=True)
    assert q["prompt"] == ["consent"]


@pytest.mark.parametrize("end", [None, "response.incomplete", "response.failed"])
def test_incomplete_or_failed_stream_never_unlocks_chat(rig, end):
    c, app, stub = rig
    signin(c, stub)
    stub.end = end
    r = c.post("/api/test", json={"model": "gpt-6.1-sol"})
    assert r.status_code == 502
    assert not app.state.login.tested


def test_quota_pauses_without_fallback(rig):
    c, app, stub = rig
    signin(c, stub)
    stub.end = "response.failed"
    stub.error = "subscription_sharing_usage_limit_exceeded"
    for _ in range(2):
        assert c.post("/api/test", json={"model": "gpt-6.1-sol"}).status_code == 429
    assert stub.responses == 1
    c.post("/api/retry")
    c.post("/api/test", json={"model": "gpt-6.1-sol"})
    assert stub.responses == 2


def test_refresh_rotation_and_logout(rig):
    c, app, stub = rig
    signin(c, stub)
    app.state.login.store.active()["expires_at"] = 0
    assert c.get("/api/models").status_code == 200
    assert stub.refreshes == 1
    assert app.state.login.store.active()["refresh_token"] == "test-refresh-1"
    assert c.post("/auth/logout").status_code == 200
    stored = app.state.login.store.data["accounts"]["oaiapp_test"]
    assert "access_token" not in stored and "id_token" not in stored
    assert "client_id" in stored


def test_unlisted_model_no_call(rig):
    c, app, stub = rig
    signin(c, stub)
    assert c.post("/api/test", json={"model": "made-up"}).status_code == 400
    assert stub.responses == 0


def test_csrf_dns_rebinding_and_missing_voice(rig):
    c, app, stub = rig
    assert c.post("/auth/start", json={}, headers={"Origin": "https://evil.invalid"}).status_code == 403
    assert c.get("/health", headers={"Host": "evil.invalid"}).status_code == 403
    assert c.post("/api/tts", json={"text": "Jarvis ist online."}).status_code == 503
    assert c.post("/api/tts", json={"text": " "}).status_code == 422
    assert "blob:" in c.get("/").headers["content-security-policy"]


def test_returning_account_mismatch_keeps_original(rig):
    c, app, stub = rig
    signin(c, stub)
    q = begin(c, stub, account="oaiapp_test")
    stub.subject = "different-subject"
    assert complete(c, q).status_code == 400
    assert app.state.login.store.active()["subject"] == "test-subject"


def test_invalid_grant_retains_registration_but_not_identity(rig):
    c, app, stub = rig
    q = begin(c, stub)
    stub.reject_code = True
    result = complete(c, q)
    assert result.status_code == 303
    assert result.headers["location"] == "/?login=invalid_grant"
    assert not app.state.login.store.data["accounts"]
    assert not c.get("/health").json()["configured"]
    assert complete(c, q).status_code == 400
    q2 = begin(c, stub, account="oaiapp_test")
    assert q2["client_id"] == ["oaiapp_test"]
    assert q2["code_challenge"] != q["code_challenge"]
    assert q2["nonce"] != q["nonce"]
    assert "agent_name_hint" not in q2
    stub.reject_code = False
    assert complete(c, q2).status_code == 303
    assert c.get("/health").json()["configured"]
    assert not app.state.login.store.data["registrations"]
