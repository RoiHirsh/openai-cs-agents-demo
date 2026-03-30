#!/usr/bin/env python3
"""
fetch_feedback.py — Pull all corrections + full conversations from Supabase.
Run from anywhere:

    python tools/fetch_feedback.py

Reads SUPABASE_URL and SUPABASE_SERVICE_KEY from agent/.env automatically.
No extra packages needed beyond the standard `requests` library.
"""

import os
import sys
import requests
from pathlib import Path

# ---------------------------------------------------------------------------
# Load agent/.env
# ---------------------------------------------------------------------------

env_path = Path(__file__).parent.parent / "agent" / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in agent/.env")
    sys.exit(1)

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


def sb_get(table: str, params: dict = None) -> list:
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    r = requests.get(url, headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Fetch data
# ---------------------------------------------------------------------------

def fetch_corrections() -> list:
    data = sb_get("corrections", {"order": "created_at.asc", "select": "*"})
    return [c for c in data if c.get("feedback_type") == "correction"]


def fetch_threads(thread_ids: list) -> dict:
    ids_filter = f"({','.join(thread_ids)})"
    data = sb_get("threads", {
        "select": "thread_id,phone_number,input_items",
        "thread_id": f"in.{ids_filter}",
    })
    return {t["thread_id"]: t for t in data}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_messages(input_items: list) -> list:
    messages = []
    for idx, item in enumerate(input_items or []):
        role = item.get("role")
        if role not in ("user", "assistant"):
            continue
        content = item.get("content")
        if isinstance(content, list):
            parts = [p.get("text", "") if isinstance(p, dict) else str(p) for p in content]
            content = " ".join(parts).strip()
        if not isinstance(content, str) or not content.strip():
            continue
        messages.append({"index": idx, "role": role, "content": content.strip()})
    return messages


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Fetching corrections from Supabase...")
    corrections = fetch_corrections()

    if not corrections:
        print("No corrections found.")
        return

    thread_ids = list({c["thread_id"] for c in corrections})
    print(f"Found {len(corrections)} correction(s) across {len(thread_ids)} conversation(s).\n")

    print("Fetching conversations...")
    thread_map = fetch_threads(thread_ids)

    print("=" * 70)

    for i, corr in enumerate(corrections, 1):
        tid = corr["thread_id"]
        thread = thread_map.get(tid, {})
        phone = thread.get("phone_number", "unknown")
        messages = extract_messages(thread.get("input_items") or [])
        flagged_index = corr.get("message_index", -1)

        # 4 messages before and after the flagged one
        window = [m for m in messages if abs(m["index"] - flagged_index) <= 4]

        print(f"\n--- CORRECTION {i} of {len(corrections)} ---")
        print(f"Phone:    {phone}")
        print(f"Thread:   {tid[:12]}...")
        print(f"Note:     {corr.get('note') or '(no note)'}")
        print(f"Original: {corr.get('original_message', '')[:300]}")
        if corr.get("corrected_message"):
            print(f"Correct:  {corr['corrected_message'][:300]}")

        if window:
            print("\nConversation context:")
            for m in window:
                marker = "  <<<< FLAGGED" if m["index"] == flagged_index else ""
                role_label = "USER" if m["role"] == "user" else " BOT"
                print(f"  [{role_label}] {m['content'][:400]}{marker}")

        print()

    print("=" * 70)
    print(f"\nDone. Paste this output into the chat for analysis.")


if __name__ == "__main__":
    main()
