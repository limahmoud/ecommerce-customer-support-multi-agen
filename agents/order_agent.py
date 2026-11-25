from agents.error_handling import invoke_llm_safely, TOOL_ERROR_MESSAGE

import os

from agents.llm_factory import create_chat_model
from langchain_core.messages import SystemMessage

from langgraph.graph import StateGraph, START
from graph.state import SupportState
from langgraph.prebuilt import ToolNode, tools_condition

from tools.order_tools import (
    get_orders_for_customer,
    get_order_information,
    get_products_in_order,
)


# 1. Tools
order_tools = [
    get_orders_for_customer,
    get_order_information,
    get_products_in_order,
]


# 2. LLM
llm = create_chat_model()

llm_with_tools = llm.bind_tools(order_tools)


# 3. System Prompt
order_system_message = SystemMessage(
    content="""
    You are an Order Support Agent.

    You handle:
    - Customer orders
    - Order details
    - Products inside orders

    Rules:
    1. Always use tools to retrieve order information.
    2. Never invent order IDs or customer IDs.
    3. Use exact IDs from conversation history.
    4. If an order ID is missing, ask for it.
    5. Use get_order_information for order details.
    6. Use get_products_in_order for products inside an order.
    7. Use get_orders_for_customer for a customer's orders.
    8. Never invent database information.
    9. Wait for actual tool results before answering.
    10. Answer clearly and concisely.

    Conversation:
    Resolve references such as:
    - it
    - that order
    - this order
    - the previous order

    Use the previous messages to identify the correct order ID.
    Do not ask for an ID that is already available.
    """
)


# 4. Agent Node
def order_agent_node(state: SupportState):

    messages = [
        order_system_message,
        *state["messages"]
    ]

    response = invoke_llm_safely(llm_with_tools, messages)

    # print("\n[ORDER AGENT DEBUG]")
    # print("Tool calls:", response.tool_calls)
    # print("Content:", response.content)

    return {"messages": [response]}


# 5. Build Graph
builder = StateGraph(SupportState)

builder.add_node("order_agent", order_agent_node)
builder.add_node("tools", ToolNode(order_tools, handle_tool_errors=TOOL_ERROR_MESSAGE))

builder.add_edge(START, "order_agent")

builder.add_conditional_edges(
    "order_agent",
    tools_condition
)

builder.add_edge("tools", "order_agent")


# 6. Compile
order_agent = builder.compile()
