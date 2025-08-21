from datetime import datetime
from typing import Optional, Dict

# super-simple rule engine for MVP
def decide_policy(voucher_status: Optional[str], issue_date: Optional[str], body: str) -> Dict:
    text = (body or "").lower()

    # rule: customer mentions expired OR voucher status is expired
    if "abgelaufen" in text or (voucher_status == "expired"):
        # optional: third-year end-of-year logic if issue_date available
        return {
            "code": "EXPIRED_NOT_REDEEMABLE",
            "template_de": (
                "Guten Tag,\n\n"
                "Ihr Gutschein ist bis zum 31. Dezember des dritten Jahres nach dem Ausstellungsdatum gültig. "
                "Nach Ablauf dieser Frist ist eine Einlösung leider nicht mehr möglich. "
                "Falls besondere Gründe vorliegen, teilen Sie uns diese bitte mit – wir prüfen gern intern.\n\n"
                "Freundliche Grüße\nYovite Support"
            )
        }

    # rule: missing code → instruct online redeem
    if "code" not in text and "pin" not in text:
        return {
            "code": "INSTRUCT_REDEEM_ONLINE",
            "template_de": (
                "Guten Tag,\n\n"
                "damit Ihr Gutschein im Restaurant akzeptiert wird, muss er vor dem Besuch online eingelöst werden. "
                "Bitte gehen Sie auf www.restaurant-gutscheine.de/einloesen und wählen Sie Ihr Restaurant aus. "
                "Sie erhalten anschließend Ihren persönlichen Einlösecode (Gutschein‑Nr. + PIN).\n\n"
                "Freundliche Grüße\nYovite Support"
            )
        }

    # fallback: ask for details once
    return {
        "code": "ASK_FOR_DETAILS_ONCE",
        "template_de": (
            "Guten Tag,\n\n"
            "damit wir Ihnen schnell weiterhelfen können, benötigen wir bitte folgende Angaben:\n"
            "• Gutschein‑Nummer und PIN\n"
            "• Ausstellungsdatum (falls bekannt)\n"
            "• Bestellsumme und Name des Bestellers\n"
            "• ggf. die E‑Mail‑Adresse, unter der der Gutschein gekauft wurde\n\n"
            "Vielen Dank vorab!\nYovite Support"
        )
    }

def generate_reply(policy: Dict, anrede: Optional[str] = None) -> str:
    # very light templating; replace {anrede} if present
    reply = policy["template_de"]
    if anrede:
        reply = reply.replace("Guten Tag,", f"Guten Tag {anrede},")
    return reply
