# src/app.py
from __future__ import annotations
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict
import os, httpx

from src.adapters.yovite_core import YoviteCoreAdapter
from src.core.agent import decide_policy, generate_reply

# ---- Helpers / Config parsing
def _get_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None: 
        return default
    return v.strip() in ("1", "true", "TRUE", "yes", "YES")

def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default

# ---- Config
USE_OLLAMA = _get_bool("USE_OLLAMA_POLISH", True)
MAX_WORDS  = _get_int("MAX_WORDS", 180)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
API_KEY    = os.getenv("API_KEY")  # optional: set to require X-API-Key
GEN_MODEL  = os.getenv("GEN_MODEL")  # nur für health info

# ---- Optional LLM polish
if USE_OLLAMA:
    from src.core.llm import polish_reply

# ---- External adapters
core = YoviteCoreAdapter()

# ---- FastAPI app
app = FastAPI(title="Yovite AI Orchestrator", version="0.2.1")

# ---- Models
class Ticket(BaseModel):
    subject: Optional[str] = None
    body: str
    anrede: Optional[str] = None
    lang: Optional[str] = "de"

class Voucher(BaseModel):
    code: Optional[str] = None
    status: Optional[str] = None
    issue_date: Optional[str] = None

class Context(BaseModel):
    role_guess: Optional[str] = None
    order_id: Optional[str] = None
    email_from: Optional[str] = None
    voucher_code: Optional[str] = None
    pin: Optional[str] = None

class SuggestReq(BaseModel):
    ticket: Ticket
    voucher: Optional[Voucher] = None
    context: Optional[Context] = None

# ---- Health
@app.get("/")
def root():
    return {"message": "AI Agent Framework is running 🚀"}

@app.get("/health")
def health():
    return {"ok": True, "model_polish_enabled": USE_OLLAMA}

@app.get("/health/ollama")
def health_ollama():
    try:
        with httpx.Client(timeout=3) as c:
            v = c.get(f"{OLLAMA_URL}/api/version").json()
        return {"ok": True, "ollama": v, "gen_model": GEN_MODEL}
    except Exception as e:
        return {"ok": False, "error": str(e), "gen_model": GEN_MODEL}

# ---- Forbidden / Guardrails
FORBIDDEN_KEYS = ["erstattung", "barauszahlung", "teil-auszahlung", "teilauszahlung"]
# Nur bei Policies, die echte Rückabwicklungen/Payments anstoßen könnten
ALLOW_PAYOUT_POLICIES = {"REFUND_ALLOWED_14D"}

def forbidden(text: str, policy_code: str) -> bool:
    if policy_code not in ALLOW_PAYOUT_POLICIES:
        return False
    low = f" {text.lower()} "
    return any(k in low for k in FORBIDDEN_KEYS)

# ---- Main endpoint
@app.post("/suggest")
def suggest(req: SuggestReq, x_api_key: Optional[str] = Header(default=None)):
    # optional API key gate
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    ticket = req.ticket
    v_in   = req.voucher or Voucher()
    ctx    = req.context or Context()

    # ----- Enrichment from Yovite-Core (read-only)
    order: Dict = {}
    voucher_core: Dict = {}

    if ctx.order_id or ctx.email_from:
        try:
            order = core.get_order(order_id=ctx.order_id, email=ctx.email_from) or {}
        except Exception:
            order = {}

    voucher_code = ctx.voucher_code or v_in.code
    if voucher_code:
        try:
            voucher_core = core.get_voucher(code=voucher_code, pin=ctx.pin) or {}
        except Exception:
            voucher_core = {}

    # ----- Inputs für Policy Engine
    status     = v_in.status or voucher_core.get("status")
    issue_date = v_in.issue_date or voucher_core.get("issue_date")
    text       = f"{ticket.subject or ''} {ticket.body}".strip()

    policy = decide_policy(
        status=status,
        issue_date=issue_date,
        text=text,
        order=order,
        voucher=voucher_core,
    )

    # rules-first draft
    draft = generate_reply(policy, ticket.anrede)

    # LLM style polish (nie Policy überschreiben)
    if USE_OLLAMA:
        decision_text = f"{policy['code']}: {policy['template_de']}"
        reply = polish_reply(decision_text, draft, text).strip()
    else:
        reply = draft

    flags = {
        "forbidden": forbidden(reply, policy["code"]),
        "too_long": len(reply.split()) > MAX_WORDS,
        "contains_sie": (" sie " in (" " + reply.lower() + " ")),
    }
    needs_human = flags["forbidden"] or flags["too_long"]

    # PII-arme Insights
    insights = {
        "order": {k: order.get(k) for k in ["order_id", "payment_status", "refund_status"] if k in order},
        "voucher": {k: voucher_core.get(k) for k in ["voucher_code", "status", "valid_until"] if k in voucher_core},
        "used_inputs": {"status": status, "issue_date": issue_date}
    }

    return {
        "intent": policy.get("intent"),
        "policy": policy["code"],
        "reply": reply,
        "flags": flags,
        "needs_human": needs_human,
        "insights": insights
    }