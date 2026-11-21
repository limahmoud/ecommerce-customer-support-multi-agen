
from langchain.tools import tool

from database.queries import (
    get_order_returns,
    get_return_by_id,
)


@tool
def get_returns_for_order(order_id: int):
    """Get all return requests associated with a specific order."""
    return get_order_returns(order_id)


@tool
def get_return_information(return_id: int):
    """Get details of a specific return request, including its status and refund status."""
    return get_return_by_id(return_id)
