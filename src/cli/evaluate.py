import json, sys, csv, re, time
from pathlib import Path
import httpx

API = "http://127.0.0.1:8000/suggest"
MAX_WORDS = 180

FORBIDDEN_PATTERNS = [
    r"\berstattung\b",
    r"\bbarauszahlung\b",
    r"\bteil-?auszahlung\b",
    r"\bgeld\s*zurück\b",
]

def contains_forbidden(text: str) -> bool:
    t = text.lower()
    return any(re.search(p, t) for p in FORBIDDEN_PATTERNS)

def contains_sie(text: str) -> bool:
    return " sie " in (" " + text.lower() + " ")

def word_count(text: str) -> int:
    return len(text.split())

def evaluate_case(case, client: httpx.Client):
    payload = case["input"]
    name = case.get("name", f"id-{case.get('id')}")
    expected = case.get("expect_policy")
    try:
        r = client.post(API, json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return {
            "name": name, "ok": False, "reason": f"HTTP error: {e}",
            "policy": None, "reply_words": None, "forbidden": None, "contains_sie": None, "needs_human": None
        }

    policy = data.get("policy")
    reply = data.get("reply", "")
    flags = data.get("flags", {})
    needs_human = data.get("needs_human", None)

    # Checks
    policy_ok = (expected is None) or (policy == expected)
    words = word_count(reply)
    length_ok = words <= MAX_WORDS
    forbidden_ok = not contains_forbidden(reply)
    sie_ok = contains_sie(reply)

    ok = policy_ok and length_ok and forbidden_ok and sie_ok and (needs_human is False)

    reason = []
    if not policy_ok: reason.append(f"policy expected {expected} got {policy}")
    if not length_ok: reason.append(f"too long ({words} words)")
    if not forbidden_ok: reason.append("forbidden phrase")
    if not sie_ok: reason.append("no Sie-form")
    if needs_human: reason.append("needs_human true")
    return {
        "name": name, "ok": ok, "reason": "; ".join(reason) if reason else "",
        "policy": policy, "reply_words": words, "forbidden": (not forbidden_ok),
        "contains_sie": sie_ok, "needs_human": needs_human
    }

def main():
    tests_path = Path("clients/yovite/eval/test_tickets.jsonl")
    if not tests_path.exists():
        print(f"Test file not found: {tests_path}", file=sys.stderr)
        sys.exit(1)

    results = []
    with open(tests_path, "r", encoding="utf-8") as f, httpx.Client() as client:
        for line in f:
            line = line.strip()
            if not line: continue
            case = json.loads(line)
            res = evaluate_case(case, client)
            results.append(res)
            status = "✅" if res["ok"] else "❌"
            print(f"{status} {res['name']}: {res['reason']}")

    # write CSV report
    out = Path("clients/yovite/eval/report.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["name","ok","reason","policy","reply_words","forbidden","contains_sie","needs_human"])
        w.writeheader()
        for r in results:
            w.writerow(r)

    passed = sum(1 for r in results if r["ok"])
    total = len(results)
    print("\n==== SUMMARY ====")
    print(f"Passed: {passed}/{total} ({(passed/total*100):.1f}%)")
    print(f"Report: {out}")

if __name__ == "__main__":
    main()
