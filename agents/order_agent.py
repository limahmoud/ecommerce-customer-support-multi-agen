
import os

from dotenv import load_dotenv

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

from langgraph.graph import StateGraph, START, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition

from tools.order_tools import (
    get_orders_for_customer,
    get_order_information,
    get_products_in_order,
)


# 1. Load environment variables
load_dotenv()

if not os.getenv("GOOGLE_API_KEY"):
    raise ValueError("GOOGLE_API_KEY is missing from .env")


# 2. Define Order Agent tools
order_tools = [
    get_orders_for_customer,
    get_order_information,
    get_products_in_order,
]


# 3. Initialize Gemini
llm = ChatGoogleGenerativeAI(
    model="gemini-3.8-flash",
    temperature=0,
)


# 4. Bind tools to the LLM
llm_with_tools = llm.bind_tools(order_tools)


# 5. Agent node
def order_agent_node(state: MessagesState):
    response = llm_with_tools.invoke(state["messages"])

    return {
        "messages": [response]
    }


# 6. Build LangGraph workflow
builder = StateGraph(MessagesState)

builder.add_node("order_agent", order_agent_node)

builder.add_node(
    "tools",
    ToolNode(order_tools)
)

builder.add_edge(START, "order_agent")

builder.add_conditional_edges(
    "order_agent",
    tools_condition
)

builder.add_edge("tools", "order_agent")


# 7. Compile the agent
order_agent = builder.compile()


# 8. Run a simple test
if __name__ == "__main__":

    question = "Show me the details of order number 1."

    result = order_agent.invoke({
        "messages": [
            HumanMessage(content=question)
        ]
    })

    print("\n========== ORDER AGENT RESPONSE ==========\n")

    last_message = result["messages"][-1]

    print(last_message.content)
