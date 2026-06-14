"""
order_tools.py — Order management tools backed by PostgreSQL
-------------------------------------------------------------
Tools:
  get_order_status   — look up an order by ID
  cancel_order       — cancel a confirmed order
"""

import logging
from typing import Any

from google.adk.tools import ToolContext

from services.db import execute, query_one

log = logging.getLogger(__name__)


def get_order_status(
    order_id: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """
    Look up an order by ID and return its current status.
    Saves current_order_id and customer_name to session state so
    follow-up questions don't need to repeat the order reference.

    Args:
        order_id: The order reference, e.g. "ORD-001".

    Returns:
        A dict with order details, or an error dict if not found.
    """
    if not order_id or not order_id.strip():
        return {"found": False, "error": "Order ID cannot be empty."}

    oid = order_id.strip().upper()
    try:
        row = query_one(
            """
            SELECT o.order_id, o.customer_name, o.customer_email,
                   o.quantity, o.total_amount, o.status, o.placed_at,
                   p.name AS product_name, p.product_id
            FROM orders o
            LEFT JOIN products p ON o.product_id = p.product_id
            WHERE o.order_id = %s
            """,
            (oid,),
        )
    except Exception as exc:
        log.error("DB error in get_order_status: %s", exc)
        return {"found": False, "error": "Order lookup is temporarily unavailable. Please try again shortly."}

    if row is None:
        return {
            "found": False,
            "order_id": oid,
            "error": f"No order found for '{oid}'. Please check the reference and try again.",
        }

    # Persist order context for this session
    tool_context.state["current_order_id"] = oid
    tool_context.state["customer_name"] = row["customer_name"]

    return {
        "found": True,
        "order_id": row["order_id"],
        "customer_name": row["customer_name"],
        "customer_email": row["customer_email"],
        "product_name": row["product_name"],
        "quantity": row["quantity"],
        "total_amount": float(row["total_amount"]),
        "status": row["status"],
        "placed_at": str(row["placed_at"]),
    }


def cancel_order(
    order_id: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """
    Cancel a confirmed or processing order.
    If order_id is "current" or empty, uses the ID saved in session state.
    Rejects already-cancelled or delivered orders with a clear message.

    Args:
        order_id: The order reference, or "current" to use the session value.

    Returns:
        A dict indicating success or the reason cancellation failed.
    """
    # Resolve "current" shorthand from session state
    if not order_id or order_id.strip().lower() in ("", "current"):
        order_id = tool_context.state.get("current_order_id", "")

    if not order_id:
        return {
            "cancelled": False,
            "error": "No order ID provided or found in this session. Please specify an order reference.",
        }

    oid = order_id.strip().upper()
    try:
        row = query_one(
            "SELECT status, customer_name FROM orders WHERE order_id = %s", (oid,)
        )
    except Exception as exc:
        log.error("DB error in cancel_order lookup: %s", exc)
        return {"cancelled": False, "error": "Cancellation service is temporarily unavailable. Please try again shortly."}

    if row is None:
        return {"cancelled": False, "order_id": oid, "error": f"Order '{oid}' not found."}

    status = row["status"].lower()

    if status == "cancelled":
        return {
            "cancelled": False,
            "order_id": oid,
            "error": f"Order '{oid}' is already cancelled. No changes were made.",
        }

    if status in ("delivered", "refunded"):
        return {
            "cancelled": False,
            "order_id": oid,
            "error": f"Order '{oid}' has already been {status} and cannot be cancelled.",
        }

    if status == "shipped":
        return {
            "cancelled": False,
            "order_id": oid,
            "error": f"Order '{oid}' has already been shipped and cannot be cancelled. Please contact support for a return.",
        }

    try:
        execute("UPDATE orders SET status = 'cancelled', updated_at = NOW() WHERE order_id = %s", (oid,))
    except Exception as exc:
        log.error("DB error updating order: %s", exc)
        return {"cancelled": False, "error": "Cancellation could not be saved. Please try again."}

    tool_context.state["current_order_id"] = oid
    return {
        "cancelled": True,
        "order_id": oid,
        "customer_name": row["customer_name"],
        "message": f"Order {oid} for {row['customer_name']} has been successfully cancelled.",
    }