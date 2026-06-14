"""
db.py — PostgreSQL connection pool + query helpers
---------------------------------------------------
Uses psycopg2 ThreadedConnectionPool so connections are reused
across tool calls instead of opening a new one every query.

Helpers:
  execute    — INSERT / UPDATE / DELETE
  query_one  — SELECT returning one row as a dict
  query_all  — SELECT returning all rows as a list of dicts
"""

import logging
import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
import psycopg2.pool
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connection pool (created once at import time)
# ---------------------------------------------------------------------------

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Return the pool, creating it on first call."""
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=5,
            host=os.getenv("PG_HOST", "localhost"),
            port=int(os.getenv("PG_PORT", 5432)),
            dbname=os.getenv("PG_DB", "ecombot"),
            user=os.getenv("PG_USER", "ecombot"),
            password=os.getenv("PG_PASSWORD", "pg_secret"),
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
        log.info("PostgreSQL connection pool created.")
    return _pool


@contextmanager
def _get_connection():
    """Borrow a connection from the pool, return it when done."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def execute(sql: str, params: tuple = ()) -> None:
    """
    Run an INSERT, UPDATE, or DELETE statement.
    Commits automatically; rolls back on error.
    """
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()
    except Exception as exc:
        log.error("execute() failed — sql: %s | params: %s | error: %s", sql, params, exc)
        raise


def query_one(sql: str, params: tuple = ()):
    """
    Run a SELECT and return the first row as a dict, or None if not found.
    """
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchone()
    except Exception as exc:
        log.error("query_one() failed — sql: %s | params: %s | error: %s", sql, params, exc)
        raise


def query_all(sql: str, params: tuple = ()) -> list:
    """
    Run a SELECT and return all rows as a list of dicts.
    Returns an empty list if no rows found.
    """
    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall() or []
    except Exception as exc:
        log.error("query_all() failed — sql: %s | params: %s | error: %s", sql, params, exc)
        raise


# ---------------------------------------------------------------------------
# Repository helpers (stretch goal — SQL stays out of agent/tool code)
# ---------------------------------------------------------------------------

class OrderRepository:
    @staticmethod
    def find_by_id(order_id: str):
        return query_one(
            """
            SELECT o.order_id, o.customer_name, o.customer_email,
                   o.quantity, o.total_amount, o.status, o.placed_at,
                   p.name AS product_name, p.product_id
            FROM orders o
            LEFT JOIN products p ON o.product_id = p.product_id
            WHERE o.order_id = %s
            """,
            (order_id,),
        )

    @staticmethod
    def cancel(order_id: str) -> None:
        execute(
            "UPDATE orders SET status = 'cancelled', updated_at = NOW() WHERE order_id = %s",
            (order_id,),
        )


class ProductRepository:
    @staticmethod
    def find_by_id(product_id: str):
        return query_one(
            "SELECT * FROM products WHERE product_id = %s",
            (product_id,),
        )

    @staticmethod
    def get_stock(product_id: str):
        return query_one(
            "SELECT product_id, name, stock_qty, is_active FROM products WHERE product_id = %s",
            (product_id,),
        )