from typing import Annotated

from langchain.tools import tool
from langgraph.prebuilt import InjectedState

from database.queries import (
    get_order_shipments,
    get_shipment_by_tracking_number,
)


@tool
def get_shipments_for_order(
    order_id: int,
    customer_id: Annotated[int, InjectedState("customer_id")],
):
    """Get shipments only for an order belonging to the authenticated customer."""
    return get_order_shipments(order_id, customer_id)


@tool
def track_shipment(
    tracking_number: str,
    customer_id: Annotated[int, InjectedState("customer_id")],
):
    """Track a shipment only if it belongs to the authenticated customer."""
    return get_shipment_by_tracking_number(tracking_number, customer_id)