
from langchain.tools import tool

from database.queries import (
    get_customer_orders,
    get_order_details,
    get_order_items,
)


@tool
def get_orders_for_customer(customer_id: int):
    """Get all orders belonging to a specific customer, including their items."""
    return get_customer_orders(customer_id)


@tool
def get_order_information(order_id: int):
    """Get complete details of an order, including customer, items, shipments, and returns."""
    return get_order_details(order_id)


@tool
def get_products_in_order(order_id: int):
    """Get the products, quantities, unit prices, and subtotals inside an order."""
    return get_order_items(order_id)
