from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from src.core.agent import decide_policy, generate_reply

app = FastAPI()

class Ticket(BaseModel):
    subject: Optional[str] = None
    body: str
    anrede: Optional[str] = None

class Voucher(BaseModel):
    code: Optional[str] = None
    status: Optional[str] = None        # e.g. "expired", "active"
    issue_date: Optional[str] = None    # "YYYY-MM-DD"

class SuggestReq(BaseModel):
    ticket: Ticket
    voucher: Optional[Voucher] = None

@app.get("/")
def root():
    return {"message": "AI Agent Framework is running 🚀"}

@app.post("/suggest")
def suggest(req: SuggestReq):
    v = req.voucher or Voucher()
    policy = decide_policy(v.status, v.issue_date, (req.ticket.subject or "") + " " + req.ticket.body)
    reply = generate_reply(policy, req.ticket.anrede)
    flags = {
        "forbidden": any(x in reply.lower() for x in ["erstattung", "barauszahlung", "teilauszahlung"]),
        "too_long": len(reply.split()) > 180,
        "contains_sie": (" sie " in (" " + reply.lower() + " ")),
    }
    needs_human = flags["forbidden"] or flags["too_long"]
    return {
        "policy": policy["code"],
        "reply": reply,
        "flags": flags,
        "needs_human": needs_human
    }

