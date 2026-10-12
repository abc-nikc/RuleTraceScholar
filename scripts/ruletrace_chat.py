#!/usr/bin/env python3
"""Minimal command-line client for a running RuleTrace Scholar instance.

Uses only the Python standard library so it can be called from terminals,
automation scripts, IDE tasks, or another agent without installing an SDK.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def read_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=15) as response:
        return json.load(response)


def stream_chat(
    base_url: str,
    question: str,
    session_id: str | None,
    paper_ids: list[str],
    deep: bool,
) -> int:
    payload = json.dumps(
        {
            "query": question,
            "session_id": session_id,
            "paper_ids": paper_ids,
            "thinking": deep,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )

    last_answer = ""
    active_session = session_id
    citation_count = 0
    with urllib.request.urlopen(request, timeout=3600) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            raw_event = line[5:].strip()
            if not raw_event or raw_event == "[DONE]":
                continue
            event = json.loads(raw_event)
            event_type = event.get("type")
            data = event.get("data")
            if event_type == "session_id":
                active_session = data
            elif event_type == "status":
                print(f"\n[{data}]", file=sys.stderr)
            elif event_type == "answer":
                answer = str(data or "")
                delta = answer[len(last_answer):] if answer.startswith(last_answer) else answer
                print(delta, end="", flush=True)
                last_answer = answer
            elif event_type == "citations":
                citation_count = len(data or [])
            elif event_type == "error":
                print(f"\nError: {data}", file=sys.stderr)
                return 1

    print(f"\n\nSession: {active_session or '-'} | Citations: {citation_count}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Ask the RuleTrace Scholar agent from a terminal.")
    parser.add_argument("question", nargs="?", help="Question to ask; prompts interactively when omitted.")
    parser.add_argument("--base-url", default="http://127.0.0.1:5173", help="Running RuleTrace Scholar URL.")
    parser.add_argument("--session", help="Continue an existing session id.")
    parser.add_argument("--paper-id", action="append", default=[], help="Limit retrieval to a paper id; repeatable.")
    parser.add_argument("--deep", action="store_true", help="Enable hidden deep reasoning and semantic evidence audit.")
    args = parser.parse_args()

    question = (args.question or input("Question: ")).strip()
    if not question:
        parser.error("question cannot be empty")
    base_url = args.base_url.rstrip("/")

    try:
        settings = read_json(f"{base_url}/api/settings")
        model = settings.get("model_status", {})
        print(
            f"Model: {model.get('provider', 'unknown')} / {model.get('model', 'unknown')}"
            f" | Mode: {'deep' if args.deep else 'fast'}",
            file=sys.stderr,
        )
        return stream_chat(base_url, question, args.session, args.paper_id, args.deep)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}: {detail}", file=sys.stderr)
    except urllib.error.URLError as exc:
        print(f"Cannot connect to {base_url}: {exc.reason}", file=sys.stderr)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Client error: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
