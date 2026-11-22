
import os

from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage

from langgraph.graph import StateGraph, START, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition

from tools.returns_tools import (
    get_returns_for_order,
    get_return_information,
)

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")

if not OLLAMA_MODEL or not OLLAMA_BASE_URL:
    raise ValueError("OLLAMA_MODEL or OLLAMA_BASE_URL is missing from .env")


# 1. Tools
returns_tools = [
    get_returns_for_order,
    get_return_information,
]


# 2. LLM
llm = ChatOllama(
    model=OLLAMA_MODEL,
    base_url=OLLAMA_BASE_URL,
    temperature=0,
)

llm_with_tools = llm.bind_tools(returns_tools)


# 3. System Prompt
returns_system_message = SystemMessage(
    content="""
    You are a Returns Support Agent.

    You handle:
    - Product returns
    - Return IDs
    - Return status
    - Return information

    Rules:
    1. Always use tools to retrieve return information.
    2. Never invent return IDs or order IDs.
    3. Use exact IDs from conversation history.
    4. Use get_returns_for_order when returns for an order are requested.
    5. Use get_return_information when a return ID is provided.
    6. If required information is missing, ask for it.
    7. Never invent return statuses or refund information.
    8. Wait for actual tool results before answering.
    9. Answer clearly and concisely.

    Conversation:
    Resolve references such as:
    - that return
    - my return
    - this order
    - the previous return

    Use previous messages to identify the relevant order ID
    or return ID.
    """
)


# 4. Agent Node
def returns_agent_node(state: MessagesState):

    messages = [
        returns_system_message,
        *state["messages"]
    ]

    response = llm_with_tools.invoke(messages)

    # print("\n[RETURNS AGENT DEBUG]")
    # print("Tool calls:", response.tool_calls)
    # print("Content:", response.content)

    return {"messages": [response]}


# 5. Build Graph
builder = StateGraph(MessagesState)

builder.add_node("returns_agent", returns_agent_node)
builder.add_node("tools", ToolNode(returns_tools))

builder.add_edge(START, "returns_agent")

builder.add_conditional_edges(
    "returns_agent",
    tools_condition
)

builder.add_edge("tools", "returns_agent")


# 6. Compile
returns_agent = builder.compile()
