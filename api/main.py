"""The API: how other systems talk to the Digital Success OS.

Synthetic data, fictional company.

Run with:  uv run python run.py api      (http://localhost:8000/docs lists the endpoints)

    GET  /health               is the service up, which mode is it in, how fresh is the data
    POST /events               product telemetry; each event is validated on the way in
    POST /mailbox/inbound      a reply that landed in the shared mailbox; classified and routed
    POST /cta/{id}/resolve     a person closes a task; the outcome goes back to the journey
    GET  /export/crm           account health, scores and signals, for the CRM
    GET  /export/cs-platform   company scorecards and open tasks, for a CS platform
    POST /assistant/ask        Claude answers a question about the data (used by the voice)
    GET  /assistant/voice-status, POST /assistant/voice-token, POST /assistant/voice-end
                               short-lived voice sessions, within the voice budget (ADR 0028)

Writing endpoints need the X-API-Token header when the API_TOKEN environment variable
is set (it always is when hosted). Every request is logged as one JSON line.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agents import assistant, mailbox, voice
from agents.classify import classify_replies
from agents.ledger import VoiceLedger
from agents.llm import get_llm
from api.exports import crm_export, cs_platform_export
from common.config import load_yaml
from common.logs import get_logger
from common.paths import DATA_DIR
from common.settings import load_settings
from common.store import open_store
from common.today import warehouse_today
from common.warehouse import open_warehouse
from engine.catalog import load_catalog
from engine.context import load_day, records
from engine.handoff import resolve_cta
from ingest.schemas import validate_event

app = FastAPI(
    title="Digital Success OS API",
    description="Synthetic data, fictional company (Lumen Labs / Relay).",
    version="1.0",
)
log = get_logger("api")


def app_origins() -> list[str]:
    """The web addresses of the app, whose pages may call the API from a browser."""
    origins = list(load_yaml("assistant.yaml")["app_origins"])
    if os.environ.get("DSO_APP_ORIGIN"):
        origins.append(os.environ["DSO_APP_ORIGIN"])
    return origins


# The "Ask the data" page calls the assistant's endpoints from the visitor's browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=app_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def data_dir() -> Path:
    """Where the data lives (DSO_DATA_DIR lets tests and containers point elsewhere)."""
    return Path(os.environ.get("DSO_DATA_DIR", DATA_DIR))


def require_token(x_api_token: str | None = Header(default=None)) -> None:
    """Writing endpoints are protected whenever API_TOKEN is set."""
    expected = os.environ.get("API_TOKEN")
    if expected and x_api_token != expected:
        raise HTTPException(status_code=401, detail="Missing or wrong X-API-Token header.")


@app.middleware("http")
async def log_request(request: Request, call_next):
    started = time.time()
    response = await call_next(request)
    fields = {
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "ms": int((time.time() - started) * 1000),
    }
    log.info("request", extra={"fields": fields})
    return response


# --- health ----------------------------------------------------------------------------------


@app.get("/health")
def health() -> dict:
    """Up or not, and enough context to know what you are looking at."""
    settings = load_settings()
    status = {
        "status": "ok",
        "data": "Synthetic data, fictional company",
        "environment": settings.env,
        "llm_mode": get_llm().mode,
        "warehouse": "ok",
        "operational_store": "ok",
    }
    try:
        status["data_as_of"] = warehouse_today(data_dir()).isoformat()
    except Exception as error:  # a missing warehouse is a state to report, not a crash
        status.update(status="degraded", warehouse=f"unavailable: {type(error).__name__}")
    try:
        store = open_store(data_dir())
        store.one("SELECT count(*) AS n FROM ctas")
        status["operational_store"] = f"ok ({store.engine.url.get_backend_name()})"
    except Exception as error:
        status.update(status="degraded", operational_store=f"unavailable: {type(error).__name__}")
    return status


# --- telemetry in ------------------------------------------------------------------------------


@app.post("/events", dependencies=[Depends(require_token)])
def receive_events(events: list[dict]) -> dict:
    """Validate each event. Good ones land for the next pipeline run; bad ones are
    kept with the reason they were rejected. Nothing is silently dropped."""
    accepted, rejected = [], []
    for event in events:
        line = json.dumps(event)
        parsed, reason, detail = validate_event(line)
        if parsed is None:
            rejected.append({"event": event, "reason": reason, "detail": detail})
        else:
            accepted.append(line)

    stamp = f"{int(time.time() * 1000)}"
    if accepted:
        folder = data_dir() / "landing" / "events"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"api-{stamp}.jsonl").write_text("\n".join(accepted) + "\n", encoding="utf-8")
    if rejected:
        folder = data_dir() / "dead_letter" / "api"
        folder.mkdir(parents=True, exist_ok=True)
        lines = "\n".join(json.dumps(item) for item in rejected)
        (folder / f"api-{stamp}.jsonl").write_text(lines + "\n", encoding="utf-8")
    reasons: dict[str, int] = {}
    for item in rejected:
        reasons[item["reason"]] = reasons.get(item["reason"], 0) + 1
    return {"accepted": len(accepted), "rejected": len(rejected), "rejected_by_reason": reasons}


# --- the shared mailbox ------------------------------------------------------------------------


class InboundReply(BaseModel):
    from_email: str
    subject: str
    body: str


@app.post("/mailbox/inbound", dependencies=[Depends(require_token)])
def receive_reply(reply: InboundReply) -> dict:
    """Classify one reply and route it, exactly as the daily triage does."""
    warehouse = open_warehouse(data_dir())
    sender = reply.from_email.strip().lower().replace("'", "")
    found = records(
        warehouse.query(
            f"SELECT account_id, contact_id FROM gold.dim_contact WHERE lower(email) = '{sender}'"
        )
    )
    warehouse.close()
    if not found:
        raise HTTPException(status_code=404, detail="No contact with that email address.")

    store = open_store(data_dir())
    ctx = load_day(data_dir(), store, load_catalog())
    message_id = store.next_id("mailbox_triage", "API")
    result = classify_replies([{"id": message_id, "subject": reply.subject, "body": reply.body}])
    verdict = result.get(message_id)
    if verdict is None:
        raise HTTPException(status_code=503, detail="The classifier is unavailable; try later.")
    message = {
        "message_id": message_id,
        "account_id": found[0]["account_id"],
        "addressed_contact_id": found[0]["contact_id"],
        "subject": reply.subject,
        "body": reply.body,
        "received_date": ctx.day,
    }
    action, cta_id = mailbox.route(ctx, message, verdict)
    store.insert(
        "mailbox_triage",
        {
            "message_id": message_id,
            "processed_on": ctx.day,
            "account_id": message["account_id"],
            "contact_id": message["addressed_contact_id"],
            "intent": verdict["intent"],
            "sentiment": verdict["sentiment"],
            "confidence": verdict["confidence"],
            "action": action,
            "cta_id": cta_id,
            "details": "{}",
        },
    )
    return {
        "message_id": message_id,
        "account_id": message["account_id"],
        "intent": verdict["intent"],
        "sentiment": verdict["sentiment"],
        "confidence": verdict["confidence"],
        "action": action,
        "cta_id": cta_id,
        "classified_by": get_llm().mode,
    }


# --- the return signal ----------------------------------------------------------------------------


class Resolution(BaseModel):
    outcome: str
    notes: str = ""
    resolved_by: str = "api"


@app.post("/cta/{cta_id}/resolve", dependencies=[Depends(require_token)])
def resolve(cta_id: str, resolution: Resolution) -> dict:
    """Close a task with an outcome. The outcome decides what the journey does next."""
    try:
        result = resolve_cta(
            open_store(data_dir()),
            load_catalog(),
            cta_id,
            resolution.outcome,
            warehouse_today(data_dir()),
            notes=resolution.notes,
            resolved_by=resolution.resolved_by,
            export_eval_case=True,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {"cta_id": cta_id, "outcome": resolution.outcome, **result}


# --- exports --------------------------------------------------------------------------------


@app.get("/export/crm")
def export_crm() -> list[dict]:
    """One row per account: health, scores, lifecycle stage, signals, open tasks."""
    return crm_export(data_dir())


@app.get("/export/cs-platform")
def export_cs_platform() -> dict:
    """Company scorecards, people and open tasks, in the shape a CS platform imports."""
    return cs_platform_export(data_dir())


# --- the "Ask the data" assistant (ADR 0028) --------------------------------------------------
# The app's page calls these from the visitor's browser, so they are open to the app's own
# web addresses (CORS, above) and need no token. Both are limited by a spending budget.


class Question(BaseModel):
    # The same limit as the page's own box: each question may be sent to a paid model.
    question: str = Field(max_length=400)


class VoiceEnd(BaseModel):
    session_id: str
    seconds: float


@app.post("/assistant/ask")
def assistant_ask(question: Question) -> dict:
    """Claude answers one question about the data or the program (used by the voice)."""
    if not question.question.strip():
        raise HTTPException(status_code=400, detail="The question is empty.")
    return assistant.ask(question.question, data_dir()).to_dict()


@app.get("/assistant/voice-status")
def assistant_voice_status() -> dict:
    """Whether the voice can be used now, and why not when it cannot."""
    current = voice.status(VoiceLedger(open_store(data_dir())))
    return {
        "enabled": current.enabled,
        "reason": current.reason,
        "budget_usd": current.budget_usd,
        "spent_usd": round(current.spent_usd, 4),
        **{key: voice.config()[key] for key in ("idle_minutes", "max_minutes")},
    }


@app.post("/assistant/voice-token")
def assistant_voice_token() -> dict:
    """A short-lived key for one voice session. The real key never leaves this server."""
    try:
        return voice.start_session(VoiceLedger(open_store(data_dir())))
    except voice.VoiceUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post("/assistant/voice-end")
async def assistant_voice_end(request: Request) -> dict:
    """The page reports how long a session lasted, so its reserved cost can shrink.

    The page sends this as it closes, with the browser's "beacon", which can only send
    plain text. So the body is read as text and checked here.
    """
    try:
        end = VoiceEnd.model_validate_json(await request.body())
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Expected session_id and seconds.") from error
    done = voice.finish_session(VoiceLedger(open_store(data_dir())), end.session_id, end.seconds)
    return {"recorded": done}
