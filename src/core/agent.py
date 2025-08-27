# src/core/agent.py
from __future__ import annotations
import re
from datetime import datetime, date
from typing import Optional, Dict
from pathlib import Path

# Python 3.11+: tomllib ist in der Stdlib; bei 3.10 -> tomli installieren und import anpassen
try:
    import tomllib as tomli  # type: ignore
except Exception:  # pragma: no cover
    import tomli  # type: ignore

REFUND_DAYS_DEFAULT = 14
TEMPLATES_PATH = Path("clients/yovite/policies/templates.de.toml")

# =========================
# Helpers / Normalization
# =========================
def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    return None

def _days_since(d: Optional[date]) -> Optional[int]:
    if not d:
        return None
    return (date.today() - d).days

def _normalize(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()

# =========================
# Intent Heuristics
# =========================
CANCEL_PATTERNS = [
    r"\bstorno\b",
    r"\bstornieren\b",
    r"\brücktritt\b",
    r"\bwiderruf\b",
    r"\bbestellung\s*(?:stornieren|widerrufen)\b",
]
REDEEM_PATTERNS = [
    r"\beinlöse", r"\beinlösen", r"\beinloes", r"\beinlösung",
    r"\bgutschein\s*einlösen", r"\bcode\b", r"\bpin\b"
]

def infer_intent(subject: str, body: str, ctx: Dict) -> str:
    s = _normalize(subject)
    b = _normalize(body)
    text = f"{s} {b}"
    if any(re.search(p, text) for p in CANCEL_PATTERNS):
        return "CANCEL"
    if ctx.get("voucher_code") or any(re.search(p, text) for p in REDEEM_PATTERNS):
        return "REDEEM_HELP"
    return "GENERAL"

# =========================
# Policy Decision
# =========================
def decide_policy(
    status: Optional[str],
    issue_date: Optional[str],
    text: str,
    order: Optional[Dict] = None,
    voucher: Optional[Dict] = None,
    cfg: Optional[Dict] = None,
) -> Dict:
    """
    Returns:
      {
        "code": "...",
        "template_de": "...",
        "intent": "CANCEL|REDEEM_HELP|GENERAL",
        "meta": {...}
      }
    """
    cfg = cfg or {}
    refund_days = int(cfg.get("refund_days", REFUND_DAYS_DEFAULT))

    # subject separat übergeben wäre sauberer; für jetzt ist 'text' = subject + body
    subject = ""
    body = text
    ctx = {
        "order_id": (order or {}).get("order_id"),
        "voucher_code": (voucher or {}).get("voucher_code"),
    }
    intent = infer_intent(subject, body, ctx)

    # Normalize core data
    order_created = _parse_date((order or {}).get("created_at"))
    days = _days_since(order_created) if order_created else None
    payment_status = (order or {}).get("payment_status", "").upper()  # PAID/...
    v_status = ((voucher or {}).get("status") or (status or "")).upper() or None
    v_type = (voucher or {}).get("type", "")

    # ---- CANCEL
    if intent == "CANCEL":
        if payment_status == "PAID":
            if v_status in ("REDEEMED", "PARTIALLY_REDEEMED"):
                return {
                    "code": "REFUND_DENIED_REDEEMED",
                    "template_de": "refund_denied_redeemed",
                    "intent": intent,
                    "meta": {"voucher_status": v_status},
                }
            if days is not None and days <= refund_days:
                return {
                    "code": "REFUND_ALLOWED_14D",
                    "template_de": "refund_allowed",
                    "intent": intent,
                    "meta": {"days_since_purchase": days},
                }
            return {
                "code": "REFUND_DENIED_TIMEOUT",
                "template_de": "refund_timeout",
                "intent": intent,
                "meta": {"days_since_purchase": days},
            }
        else:
            return {
                "code": "CANCEL_NO_PAYMENT",
                "template_de": "cancel_no_payment",
                "intent": intent,
                "meta": {"payment_status": payment_status or "UNKNOWN"},
            }

    # ---- REDEEM_HELP
    if intent == "REDEEM_HELP":
        if v_type.lower() == "universal" or not v_type:
            return {
                "code": "INSTRUCT_REDEEM_ONLINE",
                "template_de": "redeem_online",
                "intent": intent,
                "meta": {"voucher_type": v_type or "universal"},
            }
        return {
            "code": "INSTRUCT_REDEEM_RESTAURANT",
            "template_de": "redeem_restaurant",
            "intent": intent,
            "meta": {"voucher_type": v_type},
        }

    # ---- GENERAL / Fallbacks
    if v_status == "EXPIRED":
        return {
            "code": "EXPIRED_NOT_REDEEMABLE",
            "template_de": "expired",
            "intent": "GENERAL",
            "meta": {},
        }

    return {
        "code": "INFO_GENERIC",
        "template_de": "info_generic",
        "intent": "GENERAL",
        "meta": {},
    }

# =========================
# Templating
# =========================
_TEMPLATE_CACHE: Optional[Dict] = None

def _load_templates() -> Dict:
    """Load templates from TOML if present, else fallback to safe defaults."""
    global _TEMPLATE_CACHE
    if _TEMPLATE_CACHE is not None:
        return _TEMPLATE_CACHE

    if TEMPLATES_PATH.exists():
        with TEMPLATES_PATH.open("rb") as f:
            data = tomli.load(f) or {}
        # flache Struktur: {name: {text: "..."}}
        _TEMPLATE_CACHE = data
        return _TEMPLATE_CACHE

    # --- Fallback: sichere, payout-freie Texte (keine Trigger-Wörter)
    _TEMPLATE_CACHE = {
        "refund_allowed": {
            "text": (
                "{anrede},\n\n"
                "Ihre Bestellung liegt innerhalb der 14-Tage-Frist und der Gutschein wurde nicht genutzt. "
                "Wir leiten die Rückabwicklung über die ursprünglich verwendete Zahlungsart ein und informieren Sie nach Abschluss.\n\n"
                "Freundliche Grüße\nYovite Support"
            )
        },
        "refund_denied_redeemed": {
            "text": (
                "{anrede},\n\n"
                "der Gutschein wurde bereits (teilweise) genutzt. Eine Rückabwicklung ist daher nicht möglich. "
                "Gern prüfen wir Kulanzgründe – teilen Sie uns den Anlass mit.\n\n"
                "Freundliche Grüße\nYovite Support"
            )
        },
        "refund_timeout": {
            "text": (
                "{anrede},\n\n"
                "die 14-Tage-Frist ist abgelaufen, daher können wir die Bestellung nicht rückabwickeln. "
                "Gern prüfen wir Kulanzgründe.\n\n"
                "Freundliche Grüße\nYovite Support"
            )
        },
        "cancel_no_payment": {
            "text": (
                "{anrede},\n\n"
                "zu dieser Bestellung liegt keine bestätigte Zahlung vor; eine Stornierung ist nicht erforderlich.\n\n"
                "Freundliche Grüße\nYovite Support"
            )
        },
        "redeem_online": {
            "text": (
                "{anrede},\n\n"
                "Universalgutscheine müssen vor dem Restaurantbesuch online aktiviert werden. "
                "Anschließend erhalten Sie Ihren persönlichen Einlösecode (Gutschein-Nr. + PIN).\n\n"
                "Freundliche Grüße\nYovite Support"
            )
        },
        "redeem_restaurant": {
            "text": (
                "{anrede},\n\n"
                "bitte reservieren Sie direkt beim Restaurant und bringen Sie den Gutschein mit. "
                "Bei Fragen helfen wir gern weiter.\n\n"
                "Freundliche Grüße\nYovite Support"
            )
        },
        "expired": {
            "text": (
                "{anrede},\n\n"
                "Gutscheine sind bis zum 31. Dezember des dritten Jahres nach Ausstellungsdatum gültig. "
                "Nach Ablauf ist eine Einlösung nicht mehr möglich.\n\n"
                "Freundliche Grüße\nYovite Support"
            )
        },
        "info_generic": {
            "text": (
                "{anrede},\n\n"
                "vielen Dank für Ihre Nachricht. Bitte senden Sie uns Bestellnummer oder Gutschein-Nr. und PIN, "
                "damit wir schnell helfen können.\n\n"
                "Freundliche Grüße\nYovite Support"
            )
        },
    }
    return _TEMPLATE_CACHE

def generate_reply(policy: Dict, anrede: Optional[str]) -> str:
    tpl_name = policy.get("template_de") or "info_generic"
    T = _load_templates()
    rec = (T.get(tpl_name) or {})
    text = rec.get("text")
    if not text:
        # Fallback falls Template-Name fehlt
        text = "{anrede},\n\nvielen Dank für Ihre Nachricht.\n\nFreundliche Grüße\nYovite Support"
    return text.format(anrede=anrede or "Guten Tag")