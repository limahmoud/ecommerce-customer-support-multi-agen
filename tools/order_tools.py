from typing import Annotated

from langchain.tools import tool
from langgraph.prebuilt import InjectedState

from database.queries import (
    get_customer_orders,
    get_order_details,
    get_order_items,
)


@tool
def get_orders_for_customer(
    customer_id: Annotated[int, InjectedState("customer_id")],
):
    """Get orders belonging only to the authenticated customer."""
    return get_customer_orders(customer_id)


@tool
def get_order_information(
    order_id: int,
    customer_id: Annotated[int, InjectedState("customer_id")],
):
    """Get order details only if the order belongs to the authenticated customer."""
    return get_order_details(order_id, customer_id)


@tool
def get_products_in_order(
    order_id: int,
    customer_id: Annotated[int, InjectedState("customer_id")],
):
    """Get products only from an order belonging to the authenticated customer."""
    return get_order_items(order_id, customer_id)