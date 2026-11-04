import asyncio
import json
import secrets
import uuid
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from time import monotonic

import httpx
import jwt
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from filelock import FileLock
from pydantic import BaseModel, Field

from app.storage import Store, data_dir
from app.openai_login import Login, AppError, DIRECT
from app.inference import ChatRequest, build_graph, infer
from app.voice import LocalVoice
from app.mcp_connectors import ConnectorError, call_tool as mcp_call_tool, list_tools as mcp_list_tools, validate_endpoint

STATIC = Path(__file__).parent / "static"
ORIGIN = "http://127.0.0.1:8000"


class ModelChoice(BaseModel):
    model: str = Field(min_length=1, max_length=150)


class Speech(BaseModel):
    text: str = Field(min_length=1, max_length=12000)


class MCPConnectorInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    url: str = Field(min_length=8, max_length=1000)
    token: str | None = Field(default=None, max_length=4000)


class MCPToolCall(BaseModel):
    connector_id: str = Field(min_length=1, max_length=64)
    tool: str = Field(min_length=1, max_length=200)
    arguments: dict = Field(default_factory=dict)
    confirm: bool = False


def create_app(root=None, client=None):
    @asynccontextmanager
    async def lifespan(app):
        folder = Path(root) if root else data_dir()
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        # One process per credential store prevents rotating-refresh-token races.
        with FileLock(str(folder / "runtime.lock"), timeout=0):
            app.state.login = Login(Store(folder), client)
            app.state.voice = LocalVoice(folder)
            app.state.graph = build_graph(app.state.login)
            app.state.recent = deque()
            app.state.tts_lock = asyncio.Lock()
            yield
            if client is None:
                await app.state.login.client.aclose()

    app = FastAPI(title="Jarvis-2", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.middleware("http")
    async def protect(request, call_next):
        # Local-only service. Exact Host validation also blocks DNS rebinding.
        if request.headers.get("host") != "127.0.0.1:8000":
            return JSONResponse({"detail": "Jarvis lokal unter http://127.0.0.1:8000 öffnen."}, status_code=403)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if request.headers.get("origin") != ORIGIN or request.headers.get("x-jarvis-request") != "chat":
                return JSONResponse({"detail": "Bitte die lokale Jarvis-Oberfläche verwenden."}, status_code=403)
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 150000:
                    return JSONResponse({"detail": "Anfrage zu groß."}, status_code=413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers.update({"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff", "Content-Security-Policy":
            "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; media-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
        return response

    @app.exception_handler(AppError)
    async def app_error(request, exc):
        return JSONResponse(dict(detail=exc.message, code=exc.code, request_id=exc.request_id), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation(request, exc):
        return JSONResponse({"detail": "Ungültige Eingabe oder Verlauf zu lang."}, status_code=422)

    @app.exception_handler(httpx.HTTPError)
    async def network(request, exc):
        return JSONResponse({"detail": "Verbindung zu OpenAI nicht möglich. Anmeldung bleibt gespeichert."}, status_code=503)

    @app.exception_handler(jwt.PyJWTError)
    async def token_invalid(request, exc):
        return JSONResponse({"detail": "Anmeldung konnte nicht verifiziert werden. Bitte erneut anmelden."}, status_code=401)

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/health")
    async def health():
        login = app.state.login
        a = login.store.active()
        return dict(status="ok", configured=bool(a and a.get("access_token") and DIRECT in a.get("scopes", [])),
            voice_configured=app.state.voice.ready(), active=login.store.data["active"],
            accounts=[dict(id=k, label=v["email"] + " · " + k[-8:]) for k, v in login.store.data["accounts"].items()] +
                     [dict(id=k, label="Anmeldung fortsetzen · " + k[-8:]) for k in login.store.data.get("registrations", {})],
            tested_models=[m for k, m in login.tested if k == login.store.data["active"]],
            paused=login.store.data["active"] in login.paused)

    @app.post("/auth/start")
    async def start(payload: dict):
        browser = secrets.token_urlsafe(32)
        url = app.state.login.begin(browser, payload.get("account") or None, bool(payload.get("consent")))
        response = JSONResponse({"url": url})
        response.set_cookie("jarvis_oauth", browser, httponly=True, samesite="lax", max_age=600)
        return response

    @app.get("/auth/callback")
    async def callback(request: Request):
        try:
            await app.state.login.callback(dict(request.query_params), request.cookies.get("jarvis_oauth"))
        except AppError as exc:
            if exc.code != "invalid_grant":
                raise
            response = RedirectResponse("/?login=invalid_grant", status_code=303)
            response.delete_cookie("jarvis_oauth")
            return response
        response = RedirectResponse("/", status_code=303)
        response.delete_cookie("jarvis_oauth")
        return response

    @app.post("/auth/logout")
    async def logout():
        confirmed = await app.state.login.logout()
        return {"message": "Abgemeldet." if confirmed else "Lokal abgemeldet. Remote-Widerruf nicht bestätigt; bitte App zusätzlich in ChatGPT-Einstellungen trennen."}

    @app.post("/api/retry")
    async def retry():
        app.state.login.paused.discard(app.state.login.store.data["active"])
        return {"ok": True}

    @app.get("/api/mcp/connectors")
    async def mcp_connectors():
        from app.mcp_connectors import public_connector
        return {"connectors": [public_connector(item) for item in app.state.login.store.data.get("mcp_connectors", [])]}

    @app.post("/api/mcp/connectors")
    async def mcp_add_connector(payload: MCPConnectorInput):
        try:
            validate_endpoint(payload.url)
        except ConnectorError as exc:
            raise AppError(str(exc), 400) from None
        entries = app.state.login.store.data.setdefault("mcp_connectors", [])
        if len(entries) >= 20:
            raise AppError("Maximal 20 MCP-Verbindungen speichern.", 400)
        if any(item["url"] == payload.url for item in entries):
            raise AppError("Diese MCP-Adresse ist bereits eingetragen.", 409)
        item = {"id": uuid.uuid4().hex, "name": payload.name.strip(), "url": payload.url,
                "token": payload.token, "enabled": True}
        entries.append(item)
        app.state.login.store.save()
        return {"connector": {"id": item["id"], "name": item["name"], "url": item["url"],
                               "has_token": bool(item.get("token")), "enabled": True}}

    @app.delete("/api/mcp/connectors/{connector_id}")
    async def mcp_remove_connector(connector_id: str):
        entries = app.state.login.store.data.setdefault("mcp_connectors", [])
        remaining = [item for item in entries if item["id"] != connector_id]
        if len(remaining) == len(entries):
            raise AppError("MCP-Verbindung nicht gefunden.", 404)
        app.state.login.store.data["mcp_connectors"] = remaining
        app.state.login.store.save()
        return {"ok": True}

    @app.get("/api/mcp/connectors/{connector_id}/tools")
    async def mcp_connector_tools(connector_id: str):
        item = next((entry for entry in app.state.login.store.data.get("mcp_connectors", [])
                     if entry["id"] == connector_id), None)
        if not item:
            raise AppError("MCP-Verbindung nicht gefunden.", 404)
        try:
            return {"tools": await mcp_list_tools(item)}
        except Exception:
            raise AppError("MCP-Server nicht erreichbar oder MCP-Antwort ungültig. Adresse und Zugang prüfen.", 502) from None

    @app.post("/api/mcp/call")
    async def mcp_invoke(payload: MCPToolCall):
        if not payload.confirm:
            raise AppError("Werkzeugaufruf braucht deine ausdrückliche Freigabe.", 400)
        item = next((entry for entry in app.state.login.store.data.get("mcp_connectors", [])
                     if entry["id"] == payload.connector_id), None)
        if not item:
            raise AppError("MCP-Verbindung nicht gefunden.", 404)
        tools = await mcp_list_tools(item)
        advertised = next((tool for tool in tools if tool["name"] == payload.tool), None)
        if not advertised:
            raise AppError("Dieses Werkzeug wird vom MCP-Server nicht angeboten.", 404)
        try:
            result = await mcp_call_tool(item, payload.tool, payload.arguments)
        except Exception:
            raise AppError("MCP-Werkzeug fehlgeschlagen. Serverstatus und Eingaben prüfen.", 502) from None
        return {"tool": payload.tool, "description": advertised["description"], **result}

    @app.get("/api/models")
    async def models():
        async with app.state.login.lock:
            return {"models": await app.state.login.models()}

    def rate_limit():
        now = monotonic()
        recent = app.state.recent
        while recent and now - recent[0] > 60:
            recent.popleft()
        if len(recent) >= 10:
            raise AppError("Bitte kurz warten: maximal zehn Anfragen pro Minute.", 429)
        recent.append(now)

    async def model_allowed(model):
        if model not in {m["slug"] for m in await app.state.login.models()}:
            raise AppError("Dieses Modell ist in deinem aktuellen Kontokatalog nicht verfügbar.", 400)

    @app.post("/api/test")
    async def test(payload: ModelChoice):
        async with app.state.login.lock:
            rate_limit()
            await model_allowed(payload.model)
            reply = await infer(app.state.login, payload.model, [{"role": "user", "content": "Antworte genau: Jarvis ist online."}])
            app.state.login.tested.add((app.state.login.store.data["active"], payload.model))
            return dict(reply=reply, model=payload.model)

    @app.post("/api/chat")
    async def chat(payload: ChatRequest):
        async with app.state.login.lock:
            rate_limit()
            if (app.state.login.store.data["active"], payload.model) not in app.state.login.tested:
                raise AppError("Bitte zuerst die Testantwort mit diesem Modell erfolgreich erzeugen.", 409)
            await model_allowed(payload.model)
            result = await app.state.graph.ainvoke(dict(model=payload.model,
                messages=[m.model_dump() for m in payload.messages], research=payload.research))
            return {k: result.get(k) for k in ("reply", "model", "sources", "research_notice")}

    @app.post("/api/chat/stream")
    async def chat_stream(payload: ChatRequest):
        async def events():
            async with app.state.login.lock:
                task = None
                try:
                    rate_limit()
                    if (app.state.login.store.data["active"], payload.model) not in app.state.login.tested:
                        raise AppError("Bitte zuerst die Testantwort mit diesem Modell erfolgreich erzeugen.", 409)
                    await model_allowed(payload.model)
                    queue = asyncio.Queue()
                    result_task = asyncio.create_task(app.state.graph.ainvoke(dict(
                        model=payload.model, messages=[m.model_dump() for m in payload.messages],
                        research=payload.research, on_delta=lambda part: queue.put_nowait(part))))
                    task = result_task
                    while not task.done() or not queue.empty():
                        if not queue.empty():
                            yield "data: " + json.dumps({"type": "delta", "text": queue.get_nowait()}, ensure_ascii=False) + "\n\n"
                        elif not task.done():
                            try:
                                part = await asyncio.wait_for(queue.get(), timeout=0.2)
                                yield "data: " + json.dumps({"type": "delta", "text": part}, ensure_ascii=False) + "\n\n"
                            except asyncio.TimeoutError:
                                continue
                    result = task.result()
                    yield "data: " + json.dumps({"type": "done", **{k: result.get(k) for k in ("reply", "model", "sources", "research_notice")}}, ensure_ascii=False) + "\n\n"
                except AppError as exc:
                    yield "data: " + json.dumps({"type": "error", "detail": exc.message, "code": exc.code}, ensure_ascii=False) + "\n\n"
                except asyncio.CancelledError:
                    if task:
                        task.cancel()
                    raise
                except Exception:
                    yield "data: " + json.dumps({"type": "error", "detail": "Die Antwort konnte nicht abgeschlossen werden."}, ensure_ascii=False) + "\n\n"
        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/api/tts")
    async def tts(payload: Speech):
        if not payload.text.strip():
            raise AppError("Vorlesetext fehlt.", 422)
        if app.state.tts_lock.locked():
            raise AppError("Piper erzeugt gerade Sprache. Bitte kurz warten.", 429)
        async with app.state.tts_lock:
            try:
                wav = await asyncio.to_thread(app.state.voice.synthesize, payload.text)
            except AppError:
                raise
            except Exception:
                raise AppError("Piper konnte die Stimme nicht erzeugen. Installation und Modell prüfen.", 503) from None
        return Response(wav, media_type="audio/wav")

    return app


app = create_app()

