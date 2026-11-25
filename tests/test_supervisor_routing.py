
import uuid

import pytest

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres import PostgresSaver

from api.api import DB_URI
from agents.supervisor_agent import build_supervisor


def get_called_tools(messages):
    """Extract tool names called by the Supervisor."""

    called_tools = []

    for message in messages:
        for tool_call in getattr(message, "tool_calls", []):
            called_tools.append(tool_call["name"])

    return called_tools


@pytest.mark.integration
def test_supervisor_routes_order_and_shipping():

    conversation_id = f"pytest-routing-{uuid.uuid4()}"

    config = {
        "configurable": {
            "thread_id": conversation_id
        }
    }

    with PostgresSaver.from_conn_string(DB_URI) as checkpointer:

        checkpointer.setup()

        supervisor = build_supervisor(checkpointer)

        # 1. Ask about Order 1
        first_result = supervisor.invoke(
            {
                "messages": [
                    HumanMessage(
                        content="Show me the details of order 1"
                    )
                ],
                "customer_id": 1,
            },
            config=config,
        )

        assert not first_result.get("__interrupt__"), (
            "Unexpected interrupt during order lookup"
        )

        first_tools = get_called_tools(first_result["messages"])

        print("\nOrder Agent tool calls:", first_tools)

        assert "ask_order_agent" in first_tools, (
            "Supervisor did not call Order Agent"
        )

        # 2. Ask about shipment using conversation context
        second_result = supervisor.invoke(
            {
                "messages": [
                    HumanMessage(
                        content="What is its shipment status?"
                    )
                ],
                "customer_id": 1,
            },
            config=config,
        )

        assert not second_result.get("__interrupt__"), (
            "Unexpected interrupt during shipping lookup"
        )

        
        print("\n========== SECOND REQUEST DEBUG ==========")

        for index, message in enumerate(second_result["messages"]):
            print(f"\nMessage {index}")
            print("Type:", type(message).__name__)
            print("Content:", getattr(message, "content", None))
            print("Tool calls:", getattr(message, "tool_calls", []))

        second_tools = get_called_tools(second_result["messages"])

        print("\nSecond request tool calls:", second_tools)

        print("\n========== RESTORED CONVERSATION ==========")

        final_state = supervisor.get_state(config)

        for message in final_state.values["messages"]:
            print(
                type(message).__name__,
                ":",
                getattr(message, "content", "")
            )

        print("\n==========================================")



        assert "ask_shipping_agent" in second_tools, (
        "Supervisor did not call Shipping Agent"
          )

        # 3. Verify that the conversation contains both questions
        final_state = supervisor.get_state(config)

        final_messages = final_state.values["messages"]

        user_questions = [
            message.content
            for message in final_messages
            if isinstance(message, HumanMessage)
        ]

        assert any(
            "order 1" in question.lower()
            for question in user_questions
        )

        assert any(
            "shipment status" in question.lower()
            for question in user_questions
        )

        print("\nFinal response:")
        print(second_result["messages"][-1].content)
