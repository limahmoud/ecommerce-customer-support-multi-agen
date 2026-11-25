from typing import TypedDict
from langgraph.graph import MessagesState


class SupportState(MessagesState):
    """
    Shared state for the customer support multi-agent system.

    customer_id must come from the authenticated API user,
    never from an LLM-generated tool argument.
    """

    customer_id: int
