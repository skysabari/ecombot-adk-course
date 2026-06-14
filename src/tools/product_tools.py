"""
product_tools.py — Product catalogue tools backed by PostgreSQL
---------------------------------------------------------------
Tools:
  get_product_details  — look up a product by ID
  check_stock          — check if a product is in stock
"""

import logging
from typing import Any

from google.adk.tools import ToolContext

from services.db import query_one, query_all

log = logging.getLogger(__name__)


def get_product_details(
    product_id: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """
    Look up a product by ID and return its details.
    Saves current_product_id to session state for follow-up questions.

    Args:
        product_id: The product reference, e.g. "PRD-101".

    Returns:
        A dict with product details, or an error dict if not found.
    """
    if not product_id or not product_id.strip():
        return {"found": False, "error": "Product ID cannot be empty."}

    pid = product_id.strip().upper()
    try:
        row = query_one(
            "SELECT * FROM products WHERE product_id = %s",
            (pid,),
        )
    except Exception as exc:
        log.error("DB error in get_product_details: %s", exc)
        return {"found": False, "error": "Product lookup is temporarily unavailable. Please try again shortly."}

    if row is None:
        return {
            "found": False,
            "product_id": pid,
            "error": f"No product found for '{pid}'. Please check the reference and try again.",
        }

    if not row["is_active"]:
        return {
            "found": True,
            "product_id": pid,
            "active": False,
            "error": f"Product '{pid}' has been discontinued and is no longer available.",
        }

    # Persist product context for this session
    tool_context.state["current_product_id"] = pid

    return {
        "found": True,
        "active": True,
        "product_id": row["product_id"],
        "name": row["name"],
        "description": row["description"],
        "price": float(row["price"]),
        "stock_qty": row["stock_qty"],
        "in_stock": row["stock_qty"] > 0,
    }


def check_stock(
    product_id: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """
    Check whether a product is currently in stock.
    Use this when the customer asks about availability before ordering.

    Args:
        product_id: The product reference, e.g. "PRD-101".

    Returns:
        A dict with stock availability, or an error dict if not found.
    """
    if not product_id or not product_id.strip():
        return {"found": False, "error": "Product ID cannot be empty."}

    pid = product_id.strip().upper()
    try:
        row = query_one(
            "SELECT product_id, name, stock_qty, is_active FROM products WHERE product_id = %s",
            (pid,),
        )
    except Exception as exc:
        log.error("DB error in check_stock: %s", exc)
        return {"found": False, "error": "Stock check is temporarily unavailable. Please try again shortly."}

    if row is None:
        return {
            "found": False,
            "product_id": pid,
            "error": f"Product '{pid}' not found.",
        }

    if not row["is_active"]:
        return {
            "found": True,
            "product_id": pid,
            "name": row["name"],
            "in_stock": False,
            "message": f"'{row['name']}' has been discontinued and is no longer available.",
        }

    in_stock = row["stock_qty"] > 0
    return {
        "found": True,
        "product_id": pid,
        "name": row["name"],
        "in_stock": in_stock,
        "stock_qty": row["stock_qty"],
        "message": (
            f"'{row['name']}' is in stock ({row['stock_qty']} units available)."
            if in_stock
            else f"'{row['name']}' is currently out of stock."
        ),
    }