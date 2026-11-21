
from langchain.tools import tool

from database.queries import (
    get_order_shipments,
    get_shipment_by_tracking_number,
)


@tool
def get_shipments_for_order(order_id: int):
    """Get all shipments associated with a specific order."""
    return get_order_shipments(order_id)


@tool
def track_shipment(tracking_number: str):
    """Find shipment details and current delivery status using a tracking number."""
    return get_shipment_by_tracking_number(tracking_number)
