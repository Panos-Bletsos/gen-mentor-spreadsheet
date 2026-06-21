#!/usr/bin/env python3
"""Pretty-print agent traces from backend/logs/traces/traces_YYYY-MM-DD.jsonl.

Usage:
    python scripts/trace_viewer.py                    # browse today's traces
    python scripts/trace_viewer.py 2026-03-25         # browse a specific date
    python scripts/trace_viewer.py --trace a1b2c3d4   # inspect one trace directly
    python scripts/trace_viewer.py --follow           # live-tail today's trace file
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

TRACES_DIR = Path(__file__).parent.parent / "backend" / "logs" / "traces"

# ──────────────────────────────────────────────
# Terminal helpers (no external deps)
# ──────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
BLUE   = "\033[34m"
WHITE  = "\033[97m"

def _color(text: str, *codes: str) -> str:
    return "".join(codes) + text + RESET

def _hr(char: str = "─", width: int = 80) -> str:
    return char * width


# ──────────────────────────────────────────────
# JSONL loading
# ──────────────────────────────────────────────

def _traces_file(date_str: str) -> Path:
    return TRACES_DIR / f"traces_{date_str}.jsonl"


def _load_events(date_str: str) -> list[dict]:
    path = _traces_file(date_str)
    if not path.exists():
        return []
    events = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return events


def _group_traces(events: list[dict]) -> dict[str, dict]:
    """Group events by trace_id → {start, spans, end}."""
    traces: dict[str, dict] = defaultdict(lambda: {"start": None, "spans": [], "end": None})
    for ev in events:
        tid = ev.get("trace_id")
        if not tid:
            continue
        if ev["event"] == "trace_start":
            traces[tid]["start"] = ev
        elif ev["event"] == "span":
            traces[tid]["spans"].append(ev)
        elif ev["event"] == "trace_end":
            traces[tid]["end"] = ev
    return dict(traces)


# ──────────────────────────────────────────────
# Formatting
# ──────────────────────────────────────────────

def _tok_str(tok: dict) -> str:
    i = tok.get("input_tokens", 0)
    o = tok.get("output_tokens", 0)
    r = tok.get("reasoning_tokens", 0)
    base = f"in:{i} out:{o}"
    return f"{base} reasoning:{r}" if r else base


def _status_str(success: bool) -> str:
    if success:
        return _color("OK", GREEN, BOLD)
    return _color("FAIL", RED, BOLD)


def _print_trace_list(traces: dict[str, dict]) -> None:
    if not traces:
        print(_color("  No traces found.", DIM))
        return
    print()
    print(_color(f"  {'TRACE ID':<10}  {'TYPE':<22}  {'DUR':>6}  {'SPANS':>5}  {'TOKENS':<20}  STATUS", BOLD))
    print("  " + _hr("─", 76))
    for tid, t in traces.items():
        end = t.get("end") or {}
        start = t.get("start") or {}
        trace_type = start.get("trace_type", "?")
        dur = f"{end.get('total_duration_seconds', 0):.1f}s"
        spans = str(end.get("span_count", len(t["spans"])))
        tok = _tok_str(end.get("total_tokens", {}))
        success = end.get("success", True)
        status = _status_str(success)
        meta = start.get("metadata", {})
        topic = meta.get("topic", "")
        topic_str = f"  {_color(topic[:40], DIM)}" if topic else ""
        print(f"  {_color(tid, CYAN):<10}  {trace_type:<22}  {dur:>6}  {spans:>5}  {tok:<20}  {status}{topic_str}")
    print()


def _print_messages(messages: list[dict]) -> None:
    for msg in messages:
        role = msg.get("role", "?").upper()
        content = msg.get("content", "")
        role_color = CYAN if role == "SYSTEM" else YELLOW
        print(_color(f"[{role}]", role_color, BOLD))
        print(content)
        print()


def _print_span(span: dict, width: int = 80) -> None:
    label = span.get("step_label", span.get("agent_name", "?"))
    agent = span.get("agent_name", "")
    dur = span.get("duration_seconds", 0)
    tok = _tok_str(span.get("token_usage", {}))
    success = span.get("success", True)
    error = span.get("error")

    header = f"{label}  [{agent}]  {dur:.1f}s  {tok}  {'OK' if success else 'FAIL'}"
    border_color = GREEN if success else RED
    print(_color("┌" + "─" * (width - 2) + "┐", border_color))
    print(_color("│ ", border_color) + _color(header, BOLD) + " " * max(0, width - 4 - len(header)) + _color(" │", border_color))
    if error:
        err_line = f"  ERROR: {error}"
        print(_color("│ ", border_color) + _color(err_line, RED) + " " * max(0, width - 4 - len(err_line)) + _color(" │", border_color))
    print(_color("└" + "─" * (width - 2) + "┘", border_color))

    # Input messages
    input_msgs = span.get("input_messages", [])
    if input_msgs:
        print(_color("  INPUT PROMPT", DIM, BOLD))
        print(_color("  " + _hr("·", 76), DIM))
        _print_messages(input_msgs)

    # Thinking / reasoning summary
    thinking = span.get("thinking")
    if thinking:
        print(_color("  REASONING", DIM, BOLD))
        print(_color("  " + _hr("·", 76), DIM))
        print(_color(thinking, DIM))
        print()

    # Raw response
    raw = span.get("raw_response")
    if raw:
        print(_color("  RAW RESPONSE", DIM, BOLD))
        print(_color("  " + _hr("·", 76), DIM))
        print(raw)
        print()

    # Parsed output
    parsed = span.get("parsed_output")
    if parsed is not None:
        print(_color("  PARSED OUTPUT", DIM, BOLD))
        print(_color("  " + _hr("·", 76), DIM))
        if isinstance(parsed, (dict, list)):
            print(json.dumps(parsed, indent=2, ensure_ascii=False))
        else:
            print(parsed)
        print()

    print(_hr("─"))
    print()


def _print_trace_detail(tid: str, t: dict) -> None:
    start = t.get("start") or {}
    end = t.get("end") or {}
    spans = t.get("spans", [])

    print()
    print(_color(_hr("═"), BOLD))
    trace_type = start.get("trace_type", "?")
    dur = end.get("total_duration_seconds", "?")
    total_tok = _tok_str(end.get("total_tokens", {}))
    success = end.get("success", True)
    print(_color(f"  TRACE {tid}  [{trace_type}]  {dur}s  {total_tok}  ", BOLD) + _status_str(success))
    meta = start.get("metadata", {})
    if meta:
        for k, v in meta.items():
            print(_color(f"  {k}: ", DIM) + str(v))
    print(_color(_hr("═"), BOLD))
    print()

    if not spans:
        print(_color("  No spans recorded.", DIM))
        return

    for span in spans:
        _print_span(span)


# ──────────────────────────────────────────────
# Browse mode
# ──────────────────────────────────────────────

def _browse(date_str: str, jump_to: str | None = None) -> None:
    events = _load_events(date_str)
    traces = _group_traces(events)

    if jump_to:
        # Find partial match
        matches = [tid for tid in traces if tid.startswith(jump_to)]
        if not matches:
            print(_color(f"Trace '{jump_to}' not found in {date_str}.", RED))
            return
        _show_trace_paged(matches[0], traces[matches[0]])
        return

    print()
    print(_color(f"  Traces for {date_str}  ({len(traces)} total)", BOLD))
    _print_trace_list(traces)

    if not traces:
        return

    while True:
        try:
            choice = input("  Trace ID to inspect (or q to quit): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if choice.lower() in ("q", "quit", ""):
            break
        matches = [tid for tid in traces if tid.startswith(choice)]
        if not matches:
            print(_color(f"  Not found: {choice}", RED))
            continue
        _show_trace_paged(matches[0], traces[matches[0]])
        print()
        print(_color(f"  Traces for {date_str}  ({len(traces)} total)", BOLD))
        _print_trace_list(traces)


def _show_trace_paged(tid: str, t: dict) -> None:
    """Render trace detail and pipe through less if output is large."""
    import io
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    _print_trace_detail(tid, t)
    sys.stdout = old_stdout
    content = buf.getvalue()

    # Use less if terminal and content is long
    if sys.stdout.isatty() and content.count("\n") > 30:
        try:
            proc = subprocess.Popen(
                ["less", "-R"],
                stdin=subprocess.PIPE,
            )
            proc.communicate(input=content.encode("utf-8"))
            return
        except Exception:
            pass
    print(content)


# ──────────────────────────────────────────────
# Follow mode
# ──────────────────────────────────────────────



def _follow(date_str: str) -> None:
    path = _traces_file(date_str)
    print(_color(f"  Following {path}", DIM))
    print(_color("  (Ctrl+C to stop)\n", DIM))

    # Wait for file to exist
    while not path.exists():
        time.sleep(0.5)

    with open(path, encoding="utf-8") as f:
        # Seek to end so we only see new events
        f.seek(0, 2)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.3)
                continue
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue

            evt = ev.get("event")
            tid = ev.get("trace_id", "?")

            if evt == "trace_start":
                trace_type = ev.get("trace_type", "?")
                meta = ev.get("metadata", {})
                topic = meta.get("topic", "")
                topic_str = f"  topic: {topic}" if topic else ""
                print()
                print(_color(f"  ▶ [{tid}] {trace_type} started{topic_str}", BLUE, BOLD))

            elif evt == "span":
                print(_color(f"  [{tid}]", CYAN), end="  ")
                _print_span(ev)

            elif evt == "trace_end":
                dur = ev.get("total_duration_seconds", 0)
                tok = _tok_str(ev.get("total_tokens", {}))
                success = ev.get("success", True)
                trace_type = ev.get("trace_type", "?")
                print()
                print(_color(f"  ■ [{tid}] {trace_type} done  {dur:.1f}s  {tok}  ", BOLD) + _status_str(success))
                print()


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Pretty-print agent traces.")
    parser.add_argument("date", nargs="?", default=None, help="Date to browse (YYYY-MM-DD). Defaults to today.")
    parser.add_argument("--trace", "-t", metavar="ID", help="Jump directly to a specific trace ID.")
    parser.add_argument("--follow", "-f", action="store_true", help="Live-tail today's trace file.")
    args = parser.parse_args()

    date_str = args.date or date.today().isoformat()

    if args.follow:
        try:
            _follow(date_str)
        except KeyboardInterrupt:
            print(_color("\n  Stopped.", DIM))
    else:
        _browse(date_str, jump_to=args.trace)


if __name__ == "__main__":
    main()
