from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
import os

from src.core.agent import decide_policy, generate_reply

USE_OLLAMA = os.getenv("USE_OLLAMA_POLISH", "1") == "1"
MAX_WORDS  = int(os.getenv("MAX_WORDS", "180"))
if USE_OLLAMA:
    from src.core.llm import polish_reply

app = FastAPI()

class Ticket(BaseModel):
    subject: Optional[str] = None
    body: str
    anrede: Optional[str] = None

class Voucher(BaseModel):
    code: Optional[str] = None
    status: Optional[str] = None
    issue_date: Optional[str] = None

class SuggestReq(BaseModel):
    ticket: Ticket
    voucher: Optional[Voucher] = None

@app.get("/")
def root():
    return {"message": "AI Agent Framework is running 🚀"}

@app.post("/suggest")
def suggest(req: SuggestReq):
    v = req.voucher or Voucher()
    text = f"{req.ticket.subject or ''} {req.ticket.body}"
    policy = decide_policy(v.status, v.issue_date, text)

    # rules-first draft
    draft = generate_reply(policy, req.ticket.anrede)

    def forbidden(s: str) -> bool:
        s = s.lower()
        return any(k in s for k in ["erstattung", "barauszahlung", "teil-auszahlung", "teilauszahlung"])

    # style polish (optional)
    if USE_OLLAMA:
        decision_text = f"{policy['code']}: {policy['template_de']}"
        reply = polish_reply(decision_text, draft, text).strip()
    else:
        reply = draft

    flags = {
        "forbidden": forbidden(reply),
        "too_long": len(reply.split()) > MAX_WORDS,
        "contains_sie": (" sie " in (" " + reply.lower() + " ")),
    }
    needs_human = flags["forbidden"] or flags["too_long"]

    return {"policy": policy["code"], "reply": reply, "flags": flags, "needs_human": needs_human}
