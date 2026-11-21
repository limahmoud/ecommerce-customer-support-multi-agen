
import os

from dotenv import load_dotenv

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

from langgraph.graph import StateGraph, START, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition

from tools.shipping_tools import (
    get_shipments_for_order,
    track_shipment,
)


# 1. Load environment variables
load_dotenv()

if not os.getenv("GOOGLE_API_KEY"):
    raise ValueError("GOOGLE_API_KEY is missing from .env")


# 2. Define Shipping Agent tools
shipping_tools = [
    get_shipments_for_order,
    track_shipment,
]


# 3. Initialize Gemini
llm = ChatGoogleGenerativeAI(
    model="gemini-3.8-flash",
    temperature=0,
)


# 4. Bind tools to the LLM
llm_with_tools = llm.bind_tools(shipping_tools)


# 5. Shipping Agent node
def shipping_agent_node(state: MessagesState):

    response = llm_with_tools.invoke(
        state["messages"]
    )

    return {
        "messages": [response]
    }


# 6. Build LangGraph workflow
builder = StateGraph(MessagesState)

builder.add_node(
    "shipping_agent",
    shipping_agent_node
)

builder.add_node(
    "tools",
    ToolNode(shipping_tools)
)

builder.add_edge(
    START,
    "shipping_agent"
)

builder.add_conditional_edges(
    "shipping_agent",
    tools_condition
)

builder.add_edge(
    "tools",
    "shipping_agent"
)


# 7. Compile agent
shipping_agent = builder.compile()


# 8. Test Shipping Agent
if __name__ == "__main__":

    print("Starting Shipping Agent...", flush=True)

    question = (
        "Track shipment with tracking number TRK-SEED-1001"
    )

    print("Sending question to Gemini...", flush=True)

    result = shipping_agent.invoke({
        "messages": [
            HumanMessage(content=question)
        ]
    })

    print("\n========== SHIPPING AGENT RESPONSE ==========\n")

    print(result["messages"][-1].content)

    print("\nShipping Agent Finished!", flush=True)
