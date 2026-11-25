from typing import Annotated

from langchain.tools import tool
from langgraph.prebuilt import InjectedState

from database.queries import (
    get_customer_by_id,
    get_customer_tickets,
)


@tool
def get_my_profile(
    customer_id: Annotated[int, InjectedState("customer_id")],
):
    """Get the profile of the currently authenticated customer only.

    The customer_id is injected from the authenticated application state.
    Never accept a customer ID or email supplied by the user.
    """
    return get_customer_by_id(customer_id)


@tool
def get_customer_support_tickets(
    customer_id: Annotated[int, InjectedState("customer_id")],
):
    """Get support tickets belonging only to the currently authenticated customer."""
    return get_customer_tickets(customer_id)