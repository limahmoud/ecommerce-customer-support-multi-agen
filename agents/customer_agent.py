
import os

from dotenv import load_dotenv
from typing import Annotated

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage

from langgraph.graph import StateGraph, START, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition

from tools.customer_tools import (
    find_customer_by_id,
    find_customer_by_email,
    get_customer_support_tickets,
)

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")

if not OLLAMA_MODEL or not OLLAMA_BASE_URL:
    raise ValueError("OLLAMA_MODEL or OLLAMA_BASE_URL is missing from .env")


# 1. Tools
customer_tools = [
    find_customer_by_id,
    find_customer_by_email,
    get_customer_support_tickets,
]


# 2. LLM
llm = ChatOllama(
    model=OLLAMA_MODEL,
    base_url=OLLAMA_BASE_URL,
    temperature=0,
)

llm_with_tools = llm.bind_tools(customer_tools)


# 3. System Prompt
customer_system_message = SystemMessage(
    content="""
    You are a Customer Support Agent.

    You handle:
    - Customer information
    - Customer IDs
    - Customer email addresses
    - Customer support tickets

    Rules:
    1. Use tools to retrieve customer information.
    2. Never invent customer IDs or email addresses.
    3. Use exact IDs and emails from the conversation history.
    4. If required information is missing, ask the customer.
    5. Use get_customer_by_id when a customer ID is provided.
    6. Use find_customer_by_email when an email is provided.
    7. Use get_customer_support_tickets when tickets are requested.
    8. Never invent database results.
    9. Wait for actual tool results before answering.
    10. Answer clearly and concisely.

    Conversation:
    Use previous messages to understand follow-up questions.
    Do not ask for information already provided.
    """
)


# 4. Agent Node
def customer_agent_node(state: MessagesState):

    messages = [
        customer_system_message,
        *state["messages"]
    ]

    response = llm_with_tools.invoke(messages)

    # print("\n[CUSTOMER AGENT DEBUG]")
    # print("Tool calls:", response.tool_calls)
    # print("Content:", response.content)

    return {"messages": [response]}


# 5. Build Graph
builder = StateGraph(MessagesState)

builder.add_node("customer_agent", customer_agent_node)
builder.add_node("tools", ToolNode(customer_tools))

builder.add_edge(START, "customer_agent")

builder.add_conditional_edges(
    "customer_agent",
    tools_condition
)

builder.add_edge("tools", "customer_agent")


# 6. Compile
customer_agent = builder.compile()
