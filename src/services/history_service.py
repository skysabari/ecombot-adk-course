"""
history_service.py — Durable conversation history in PostgreSQL
----------------------------------------------------------------
Stores every conversation turn as an append-only audit trail.
Separate from ADK's own session tables — this captures a clean,
human-readable record of who said what, when, and which tools were called.

Boundary:
    Session state  = short-lived working memory (Redis + ADK session)
    History        = durable, append-only record of every turn (PostgreSQL)

Public API:
    record_turn(session_id, user_id, role, content, tool_calls)
    get_history(session_id)     → list[dict]
    print_history(session_id)   → prints formatted history to stdout
"""

import json
import logging
from datetime import datetime
from typing import Any

from services.db import execute, query_all

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def record_turn(
    session_id: str,
    user_id: str,
    role: str,
    content: str,
    tool_calls: list[dict[str, Any]] | None = None,
) -> None:
    """
    Append one conversation turn to session_history.

    Args:
        session_id:  ADK session identifier.
        user_id:     User identifier.
        role:        'user' or 'assistant'.
        content:     The text of the turn.
        tool_calls:  Optional list of tool call records (name + args + result).
    """
    try:
        execute(
            """
            INSERT INTO session_history (session_id, user_id, role, message, created_at)
            VALUES (%s, %s, %s, %s, NOW())
            """,
            (
                session_id,
                user_id,
                role,
                _build_content(content, tool_calls),
            ),
        )
    except Exception as exc:
        # History write failures are non-fatal — log and continue.
        log.warning("History write failed (non-fatal): %s", exc)


def _build_content(content: str, tool_calls: list[dict] | None) -> str:
    """
    Combine content text and tool calls into a single stored string.
    Tool calls are appended as JSON so the full turn is human-readable.
    """
    if not tool_calls:
        return content
    tools_summary = json.dumps(tool_calls, indent=2)
    return f"{content}\n\n[tool_calls]\n{tools_summary}"


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def get_history(session_id: str) -> list[dict]:
    """
    Return all turns for a session ordered oldest-first.
    Returns an empty list if the session is not found or the DB is down.
    """
    try:
        return query_all(
            """
            SELECT role, message, created_at
            FROM session_history
            WHERE session_id = %s
            ORDER BY created_at ASC
            """,
            (session_id,),
        )
    except Exception as exc:
        log.warning("History read failed: %s", exc)
        return []


def get_history_by_user(user_id: str) -> list[dict]:
    """
    Return all turns for a user across all sessions, ordered oldest-first.
    Useful for admin/debug purposes.
    """
    try:
        return query_all(
            """
            SELECT session_id, role, message, created_at
            FROM session_history
            WHERE user_id = %s
            ORDER BY created_at ASC
            """,
            (user_id,),
        )
    except Exception as exc:
        log.warning("History read by user failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Debug / admin helper
# ---------------------------------------------------------------------------

def print_history(session_id: str) -> None:
    """
    Pretty-print the full conversation history for a session.
    Use this for debugging or replaying a session after it ends.
    """
    turns = get_history(session_id)

    if not turns:
        print(f"No history found for session: {session_id}")
        return

    print(f"\n{'='*60}")
    print(f"  Session History: {session_id}")
    print(f"  Total turns: {len(turns)}")
    print(f"{'='*60}\n")

    for turn in turns:
        role = str(turn["role"]).upper()
        created_at = turn["created_at"]
        message = turn["message"]

        # Format timestamp
        if isinstance(created_at, datetime):
            ts = created_at.strftime("%Y-%m-%d %H:%M:%S")
        else:
            ts = str(created_at)

        # Role label with padding
        label = f"[{role}]"
        print(f"{label:<12} {ts}")
        print(f"{'─'*60}")
        print(message)
        print()

    print(f"{'='*60}\n")