import asyncio
import base64
import hashlib
import secrets
import time
from urllib.parse import urlencode, urlparse

import httpx
import jwt

AUTH = "https://auth.openai.com"
API = "https://api.openai.com/v1"
TOKEN = AUTH + "/api/accounts/oauth/token"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
DIRECT = "chatgpt.tokens.use.direct"
CALLBACK = "http://127.0.0.1:8000/auth/callback"


class AppError(Exception):
    def __init__(self, message, status=400, code=None, request_id=None):
        self.message, self.status, self.code, self.request_id = message, status, code, request_id


def provider_error(status, body, request_id=None):
    detail = body.get("error", {}) if isinstance(body, dict) else {}
    code = detail.get("code") if isinstance(detail, dict) else detail
    messages = {
        "invalid_grant": "OpenAI hat den Anmeldecode abgelehnt. Bitte auf der Jarvis-Startseite eine neue Anmeldung beginnen; die alte Rückleitungsseite nicht neu laden.",
        "subscription_sharing_user_not_eligible": "Dieses Konto oder dieser Workspace darf das ChatGPT-Abo hier nicht nutzen.",
        "subscription_sharing_usage_limit_exceeded": "Das Abo-Kontingent für diese Nutzung ist erreicht. Prüfe ChatGPT → Einstellungen → Usage. Es gibt keinen kostenpflichtigen API-Ersatz.",
        "subscription_sharing_usage_unavailable": "OpenAI kann das Kontingent gerade nicht prüfen. Bitte später erneut versuchen.",
        "subscription_sharing_unsupported_capability": "Das gewählte Modell oder diese Funktion wird über die Abo-Anbindung nicht unterstützt.",
        "subscription_sharing_route_not_supported": "OpenAI unterstützt diesen Abo-Zugangsweg für dein Konto derzeit nicht.",
    }
    defaults = {401: "Anmeldung oder Berechtigung ungültig. Bitte erneut anmelden.",
                403: "OpenAI erlaubt diesen Zugriff derzeit nicht. Konto, Workspace oder Region prüfen.",
                429: "Nutzungslimit erreicht. Bitte ChatGPT Usage prüfen und später erneut versuchen.",
                503: "Die Abo-Anbindung ist gerade nicht verfügbar. Bitte später erneut versuchen."}
    return AppError(messages.get(code, defaults.get(status, "OpenAI konnte die Anfrage nicht abschließen.")),
                    status if 400 <= status <= 599 else 502, code, request_id)


class Login:
    def __init__(self, store, client=None):
        self.store = store
        self.client = client or httpx.AsyncClient(timeout=60)
        self.pending = {}
        self.lock = asyncio.Lock()
        self.tested = set()
        self.paused = set()
        self._models_cache = None
        self._models_cached_at = 0.0

    def begin(self, browser, account=None, consent=False):
        now = time.time()
        self.pending = {k: v for k, v in self.pending.items() if v["expires"] > now}
        if len(self.pending) >= 20:
            raise AppError("Zu viele Anmeldeversuche. Bitte kurz warten.", 429)
        old = (self.store.data["accounts"].get(account) or
               self.store.data.get("registrations", {}).get(account)) if account else None
        if account and not old:
            raise AppError("Unbekanntes Konto.")
        state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
        client_id = old["client_id"] if old else "dynamic_agent_client"
        self.pending[state] = dict(browser=browser, nonce=nonce, verifier=verifier,
                                   client_id=client_id, account=account, expires=now + 600)
        q = dict(client_id=client_id, ext_agent_host_id=self.store.data["host"],
                 response_type="code", redirect_uri=CALLBACK, scope=SCOPES, resource=API,
                 state=state, nonce=nonce, code_challenge_method="S256",
                 code_challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode())
        if old:
            if old.get("id_token"):
                q["id_token_hint"] = old["id_token"]
        else:
            q["agent_name_hint"] = "Jarvis-2"
        if consent:
            q["prompt"] = "consent"
        return AUTH + "/api/accounts/authorize?" + urlencode(q)

    async def json_request(self, method, url, **kwargs):
        r = await self.client.request(method, url, **kwargs)
        try:
            data = r.json()
        except ValueError:
            data = {}
        if r.is_error:
            raise provider_error(r.status_code, data, r.headers.get("x-request-id"))
        return data

    async def validate(self, token, client_id, nonce=None):
        jwks = await self.json_request("GET", AUTH + "/.well-known/jwks.json")
        header = jwt.get_unverified_header(token)
        key = next((k for k in jwks["keys"] if k.get("kid") == header.get("kid")), None)
        if not key or header.get("alg") != "RS256":
            raise AppError("OpenAI-Signatur konnte nicht geprüft werden.")
        claims = jwt.decode(token, jwt.PyJWK.from_dict(key).key, algorithms=["RS256"],
                            audience=client_id, issuer=AUTH,
                            options={"require": ["exp", "iss", "aud", "sub"]})
        if nonce and not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
            raise AppError("Die Anmeldung konnte nicht verifiziert werden.")
        return claims

    async def callback(self, params, browser):
        state = params.get("state", "")
        attempt = self.pending.get(state)
        if not attempt or attempt["expires"] <= time.time() or not browser or not secrets.compare_digest(attempt["browser"], browser):
            raise AppError("Anmeldung abgelaufen oder ungültig. Bitte neu beginnen.")
        self.pending.pop(state)
        if params.get("error"):
            raise AppError("Die Anmeldung oder Abo-Freigabe wurde abgebrochen.")
        client_id = params.get("client_id", attempt["client_id"])
        if not client_id.startswith("oaiapp_") or (attempt["account"] and client_id != attempt["client_id"]):
            raise AppError("Die App-Registrierung ist unvollständig oder stimmt nicht überein.")
        if not params.get("code"):
            raise AppError("Anmeldecode fehlt.")
        async with self.lock:
            try:
                tokens = await self.json_request("POST", TOKEN, data=dict(
                    grant_type="authorization_code", client_id=client_id, code=params["code"],
                    code_verifier=attempt["verifier"], redirect_uri=CALLBACK, resource=API))
            except AppError as exc:
                if exc.code == "invalid_grant" and client_id not in self.store.data["accounts"]:
                    # Registration metadata is not authenticated account identity.
                    # Keep it separate; it grants no access until OIDC validation succeeds.
                    self.store.data.setdefault("registrations", {})[client_id] = {"client_id": client_id}
                    self.store.save()
                raise
            try:
                claims = await self.validate(tokens["id_token"], client_id, attempt["nonce"])
            except (jwt.PyJWTError, KeyError, StopIteration):
                raise AppError("Die Identität konnte nicht verifiziert werden.") from None
            old = self.store.data["accounts"].get(client_id)
            if old and old["subject"] != claims["sub"]:
                raise AppError("Das Konto stimmt nicht mit der bestehenden Registrierung überein.")
            record = dict(client_id=client_id, subject=claims["sub"], email=claims.get("email", "ChatGPT-Konto"))
            self.merge_tokens(record, tokens)
            self.store.data["accounts"][client_id] = record
            self.store.data.get("registrations", {}).pop(client_id, None)
            self.store.data["active"] = client_id
            self.store.save()
            self.tested.clear()
            self.paused.clear()

    def merge_tokens(self, record, tokens):
        if tokens.get("token_type", "").lower() != "bearer" or not tokens.get("access_token"):
            raise AppError("OpenAI hat keinen gültigen Zugriffstoken geliefert.")
        for name in ("access_token", "refresh_token", "id_token"):
            if tokens.get(name):
                record[name] = tokens[name]
        record["expires_at"] = time.time() + float(tokens["expires_in"])
        if "scope" in tokens:
            record["scopes"] = tokens["scope"].split()
        else:
            record.setdefault("scopes", [])

    async def token(self):
        # Caller holds lock throughout request; account switching cannot race refresh/inference.
        record = self.store.active()
        if not record or not record.get("access_token"):
            raise AppError("Bitte zuerst mit ChatGPT anmelden.", 401)
        if DIRECT not in record.get("scopes", []):
            raise AppError("Die Freigabe deines ChatGPT-Kontingents fehlt. Wähle Abo-Nutzung erlauben.", 403)
        if record["expires_at"] < time.time() + 60:
            if not record.get("refresh_token"):
                raise AppError("Die Anmeldung ist abgelaufen. Bitte erneut anmelden.", 401)
            try:
                tokens = await self.json_request("POST", TOKEN, data=dict(grant_type="refresh_token",
                    client_id=record["client_id"], refresh_token=record["refresh_token"], resource=API))
            except AppError as exc:
                if exc.code in {"invalid_grant", "invalid_refresh_token", "token_expired", "refresh_token_expired", "refresh_token_invalidated", "refresh_token_reused"}:
                    self.clear_tokens(record)
                    self.store.save()
                raise
            if tokens.get("id_token"):
                claims = await self.validate(tokens["id_token"], record["client_id"])
                if claims["sub"] != record["subject"]:
                    raise AppError("Kontoidentität bei Erneuerung geändert.", 401)
            self.merge_tokens(record, tokens)
            self.store.save()
        if DIRECT not in record.get("scopes", []):
            raise AppError("Abo-Freigabe fehlt. Bitte erneut freigeben.", 403)
        return record["access_token"]

    @staticmethod
    def clear_tokens(record):
        for name in ("access_token", "refresh_token", "id_token", "expires_at", "scopes"):
            record.pop(name, None)

    async def logout(self):
        async with self.lock:
            record = self.store.active()
            confirmed = True
            if record and record.get("refresh_token"):
                try:
                    cfg = await self.json_request("GET", AUTH + "/.well-known/openid-configuration")
                    url = cfg["revocation_endpoint"]
                    if urlparse(url).scheme != "https" or urlparse(url).netloc != "auth.openai.com":
                        raise ValueError("Invalid revocation endpoint")
                    r = await self.client.post(url, data=dict(token=record["refresh_token"],
                        token_type_hint="refresh_token", client_id=record["client_id"]))
                    confirmed = r.status_code == 200
                except (httpx.HTTPError, AppError, KeyError, ValueError):
                    confirmed = False
            if record:
                self.clear_tokens(record)
            self.store.data["active"] = None
            self.store.save()
            self.tested.clear()
            return confirmed

    async def models(self):
        if self._models_cache is not None and time.monotonic() - self._models_cached_at < 300:
            return self._models_cache
        token = await self.token()
        data = await self.json_request("GET", API + "/models", headers={"Authorization": "Bearer " + token})
        self._models_cache = [{"slug": m["slug"], "display_name": m["display_name"]}
                              for m in data.get("models", []) if m.get("visibility") == "list"]
        self._models_cached_at = time.monotonic()
        return self._models_cache

