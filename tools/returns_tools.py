from typing import Annotated

from langchain.tools import tool
from langgraph.prebuilt import InjectedState

from database.queries import (
    get_order_returns,
    get_return_by_id,
)


@tool
def get_returns_for_order(
    order_id: int,
    customer_id: Annotated[int, InjectedState("customer_id")],
):
    """Get returns only for an order belonging to the authenticated customer."""
    return get_order_returns(order_id, customer_id)


@tool
def get_return_information(
    return_id: int,
    customer_id: Annotated[int, InjectedState("customer_id")],
):
    """Get return information only if it belongs to the authenticated customer."""
    return get_return_by_id(return_id, customer_id)