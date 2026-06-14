"""
session_service.py — Session service factory for ecombot
---------------------------------------------------------
Supports three backends selected via SESSION_BACKEND env var:

    SESSION_BACKEND=memory    — InMemorySessionService  (default, no persistence)
    SESSION_BACKEND=redis     — RedisSessionService     (survives restarts, no SQL)
    SESSION_BACKEND=database  — DatabaseSessionService  (PostgreSQL, full durability)

Examples:
    SESSION_BACKEND=memory   python3 agents/support_agent.py   ← dev/testing
    SESSION_BACKEND=redis    python3 agents/support_agent.py   ← session persistence
    SESSION_BACKEND=database python3 agents/support_agent.py   ← full persistence

Session state keys stored in working memory:
    current_order_id       — last order the customer asked about
    current_customer_name  — customer name from last order lookup
    current_product_id     — last product the customer asked about
    last_intent            — last detected intent (order_status, cancel, product_info)
    last_lookup_key        — raw ID the customer last provided
"""

import logging
import os
import uuid

import redis as redis_lib
from dotenv import load_dotenv
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService, InMemorySessionService

load_dotenv()

log = logging.getLogger(__name__)

APP_NAME = os.getenv("APP_NAME", "ecombot")

# ---------------------------------------------------------------------------
# Redis connection (used for working memory + session ref storage)
# ---------------------------------------------------------------------------

def _get_redis_client():
    return redis_lib.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        password=os.getenv("REDIS_PASSWORD", "redis_secret"),
        decode_responses=True,
    )


def save_session_ref(user_id: str, session_id: str) -> None:
    """
    Persist the session reference in Redis so the app can reconnect
    to the same session after a process restart.
    """
    try:
        r = _get_redis_client()
        ttl = int(os.getenv("REDIS_SESSION_TTL", 3600))
        r.setex(f"session_ref:{user_id}", ttl, session_id)
        log.info("Session ref saved to Redis: %s → %s", user_id, session_id)
    except Exception as exc:
        log.warning("Could not save session ref to Redis: %s", exc)


def load_session_ref(user_id: str) -> str | None:
    """
    Retrieve a previously saved session ID from Redis for this user.
    Returns None if not found or Redis is unavailable.
    """
    try:
        r = _get_redis_client()
        session_id = r.get(f"session_ref:{user_id}")
        if session_id:
            log.info("Session ref loaded from Redis: %s → %s", user_id, session_id)
        return session_id
    except Exception as exc:
        log.warning("Could not load session ref from Redis: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Session service factory
# ---------------------------------------------------------------------------

def get_session_service():
    """
    Return the active session service based on SESSION_BACKEND env var.

    memory   — InMemorySessionService: lost on restart, good for dev.
    redis    — RedisSessionService via adk-extra-services: fast, survives
               restarts as long as Redis is running.
    database — DatabaseSessionService: PostgreSQL via asyncpg, fully durable.
               Falls back to memory if DB is unreachable.
    """
    backend = os.getenv("SESSION_BACKEND", "memory").lower()

    if backend == "memory":
        log.info("Session backend: InMemory (no persistence)")
        return InMemorySessionService()

    if backend == "redis":
        try:
            from adk_extra_services.sessions import RedisSessionService
            redis_url = (
                f"redis://:{os.getenv('REDIS_PASSWORD', 'redis_secret')}"
                f"@{os.getenv('REDIS_HOST', 'localhost')}"
                f":{os.getenv('REDIS_PORT', 6379)}"
            )
            svc = RedisSessionService(redis_url=redis_url)
            log.info(
                "Session backend: Redis (%s:%s)",
                os.getenv("REDIS_HOST", "localhost"),
                os.getenv("REDIS_PORT", 6379),
            )
            return svc
        except Exception as exc:
            log.error("Redis session service unavailable: %s", exc)
            raise RuntimeError(
                "Cannot connect to Redis. Start it with: docker compose up -d redis\n"
                f"Detail: {exc}"
            ) from exc

    if backend == "database":
        try:
            pg_url = (
                f"postgresql+asyncpg://{os.getenv('PG_USER', 'ecombot')}"
                f":{os.getenv('PG_PASSWORD', 'pg_secret')}"
                f"@{os.getenv('PG_HOST', 'localhost')}"
                f":{os.getenv('PG_PORT', 5432)}"
                f"/{os.getenv('PG_DB', 'ecombot')}"
            )
            svc = DatabaseSessionService(db_url=pg_url)
            log.info(
                "Session backend: PostgreSQL (%s/%s)",
                os.getenv("PG_HOST", "localhost"),
                os.getenv("PG_DB", "ecombot"),
            )
            return svc
        except Exception as exc:
            log.error("PostgreSQL session service unavailable: %s", exc)
            raise RuntimeError(
                "Cannot connect to PostgreSQL. Start it with: docker compose up -d postgres\n"
                f"Detail: {exc}"
            ) from exc

    log.warning("Unknown SESSION_BACKEND '%s', falling back to InMemory.", backend)
    return InMemorySessionService()


# ---------------------------------------------------------------------------
# Runner factory
# ---------------------------------------------------------------------------

async def make_runner(
    agent,
    user_id: str | None = None,
    session_id: str | None = None,
) -> tuple[Runner, str, str]:
    """
    Wrap an agent in a Runner with a session.

    - If user_id is None, a new one is generated.
    - If session_id is None, checks Redis for an existing session ref
      for this user. Creates a fresh session if none found.
    - If session_id is provided, reconnects to that session directly.

    Returns (runner, user_id, session_id).
    """
    session_service = get_session_service()
    runner = Runner(agent=agent, app_name=APP_NAME, session_service=session_service)

    if user_id is None:
        user_id = f"user-{uuid.uuid4().hex[:6]}"

    # Try to restore session from Redis if no session_id was passed
    if session_id is None:
        session_id = load_session_ref(user_id)

    if session_id is None:
        # No previous session — create fresh
        session_id = f"session-{uuid.uuid4().hex[:8]}"
        await session_service.create_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
        log.info("Created new session: %s / %s", user_id, session_id)
    else:
        # Reconnect to existing session
        existing = await session_service.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
        if existing is None:
            await session_service.create_session(
                app_name=APP_NAME, user_id=user_id, session_id=session_id
            )
            log.info("Session not found — created fresh: %s", session_id)
        else:
            log.info("Reconnected to existing session: %s", session_id)

    # Always persist the session ref so next restart can find it
    save_session_ref(user_id, session_id)

    return runner, user_id, session_id