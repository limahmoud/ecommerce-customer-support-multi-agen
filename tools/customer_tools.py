
from langchain.tools import tool

from database.queries import (
    get_customer_by_id,
    get_customer_by_email,
    get_customer_tickets,
)


@tool
def find_customer_by_id(customer_id: int):
    """Find a customer using their unique customer ID."""
    return get_customer_by_id(customer_id)


@tool
def find_customer_by_email(email: str):
    """Find a customer using their email address."""
    return get_customer_by_email(email)


@tool
def get_customer_support_tickets(customer_id: int):
    """Get all support tickets belonging to a specific customer."""
    return get_customer_tickets(customer_id)
