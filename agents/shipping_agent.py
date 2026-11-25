from agents.error_handling import invoke_llm_safely, TOOL_ERROR_MESSAGE

import os

from agents.llm_factory import create_chat_model
from langchain_core.messages import SystemMessage

from langgraph.graph import StateGraph, START
from graph.state import SupportState
from langgraph.prebuilt import ToolNode, tools_condition

from tools.shipping_tools import (
    get_shipments_for_order,
    track_shipment,
)


# 1. Tools
shipping_tools = [
    get_shipments_for_order,
    track_shipment,
]


# 2. LLM
llm = create_chat_model()

llm_with_tools = llm.bind_tools(shipping_tools)


# 3. System Prompt
shipping_system_message = SystemMessage(
    content="""
    You are a Shipping Support Agent.

    You handle:
    - Shipments
    - Tracking numbers
    - Delivery status
    - Estimated delivery dates

    Rules:
    1. Always use tools to retrieve shipment information.
    2. Never invent tracking numbers or order IDs.
    3. Use exact IDs from conversation history.
    4. Use get_shipments_for_order when shipments for an order are requested.
    5. Use track_shipment when a tracking number is provided.
    6. If required information is missing, ask for it.
    7. Never invent delivery dates or shipment statuses.
    8. Wait for actual tool results before answering.
    9. Answer clearly and concisely.

    Conversation:
    Resolve references such as:
    - my shipment
    - that shipment
    - its tracking status
    - the previous order

    Use previous messages to identify the relevant order ID
    or tracking number.
    """
)


# 4. Agent Node
def shipping_agent_node(state: SupportState):

    messages = [
        shipping_system_message,
        *state["messages"]
    ]

    response = invoke_llm_safely(llm_with_tools, messages)

    # print("\n[SHIPPING AGENT DEBUG]")
    # print("Tool calls:", response.tool_calls)
    # print("Content:", response.content)

    return {"messages": [response]}


# 5. Build Graph
builder = StateGraph(SupportState)

builder.add_node("shipping_agent", shipping_agent_node)
builder.add_node("tools", ToolNode(shipping_tools, handle_tool_errors=TOOL_ERROR_MESSAGE))

builder.add_edge(START, "shipping_agent")

builder.add_conditional_edges(
    "shipping_agent",
    tools_condition
)

builder.add_edge("tools", "shipping_agent")


# 6. Compile
shipping_agent = builder.compile()
