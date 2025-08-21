# src/core/llm.py
import os, httpx
from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
GEN_MODEL  = os.getenv("GEN_MODEL", "llama3.1")
MAX_WORDS  = int(os.getenv("MAX_WORDS", "180"))

POLISH_SYSTEM = (
    "Du überarbeitest deutsche Support-E-Mails (Sie-Form). "
    "Ändere keine inhaltlichen Entscheidungen, keine neuen Zusagen. "
    f"Formuliere freundlich, klar, maximal {MAX_WORDS} Wörter. "
    "Keine Erstattung/Bar-/Teilauszahlung versprechen."
)

def _prompt(decision_text: str, draft: str, user_message: str) -> str:
    return (
        f"System:\n{POLISH_SYSTEM}\n\n"
        "Bindende Policy-Entscheidung (nicht ändern):\n"
        f"{decision_text}\n\n"
        "Kundenanfrage:\n"
        f"{user_message}\n\n"
        "Entwurf (nur sprachlich verbessern, Inhalt unverändert lassen):\n"
        f"{draft}\n\n"
        "Aufgabe:\n"
        f"- Formuliere den Entwurf natürlich und höflich um.\n"
        f"- Sie-Form; keine Erstattung/Bar-/Teilauszahlung zusagen.\n"
        f"- Maximal {MAX_WORDS} Wörter.\n"
        f"- Antworte nur mit dem finalen Text."
    )

def ollama_generate(prompt: str, temperature: float = 0.2) -> str:
    with httpx.Client(timeout=90) as c:
        r = c.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": GEN_MODEL,
                "prompt": prompt,
                "options": {"temperature": temperature},
                "stream": False,  # non-streaming → single JSON
            },
        )
        r.raise_for_status()
        data = r.json()
        return (data.get("response") or "").strip()

def polish_reply(decision_text: str, draft: str, user_message: str) -> str:
    return ollama_generate(_prompt(decision_text, draft, user_message), temperature=0.2)