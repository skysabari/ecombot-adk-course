import re

def get_order_status(order_id: str):
    if not re.fullmatch(r"ORD-\d{3}", order_id):
        return {"error": "Invalid order ID format."}
    MOCK_ORDERS = {
        "ORD-001": {"order_id": "ORD-001", "status": "Shipped", "eta": "5 Jun 2026", "carrier": "BlueDart"},
        "ORD-002": {"order_id": "ORD-002", "status": "Processing", "eta": "7 Jun 2026", "carrier": "DTDC"},
        "ORD-003": {"order_id": "ORD-003", "status": "Delivered", "eta": "Already delivered", "carrier": "FedEx"},
    }
    if MOCK_ORDERS.get(order_id):
        return MOCK_ORDERS[order_id]
    else:
        return {"error": f"Order {order_id} not found."}
