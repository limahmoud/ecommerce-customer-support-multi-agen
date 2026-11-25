from langchain_core.messages import AIMessage

from agents.error_handling import (
    invoke_llm_safely,
    SAFE_ERROR_MESSAGE,
)


class FakeLLM:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    def invoke(self, messages):
        if self.error:
            raise self.error

        return self.response


def test_llm_failure_returns_safe_message():
    llm = FakeLLM(error=RuntimeError("Ollama connection refused"))

    result = invoke_llm_safely(llm, [])

    assert isinstance(result, AIMessage)
    assert result.content == SAFE_ERROR_MESSAGE


def test_invalid_llm_response_returns_safe_message():
    llm = FakeLLM(response=None)

    result = invoke_llm_safely(llm, [])

    assert isinstance(result, AIMessage)
    assert result.content == SAFE_ERROR_MESSAGE


def test_unexpected_response_type_returns_safe_message():
    llm = FakeLLM(response={"unexpected": "response"})

    result = invoke_llm_safely(llm, [])

    assert isinstance(result, AIMessage)
    assert result.content == SAFE_ERROR_MESSAGE


def test_valid_llm_response_is_preserved():
    expected = AIMessage(content="Your order is confirmed.")
    llm = FakeLLM(response=expected)

    result = invoke_llm_safely(llm, [])

    assert result is expected
    assert result.content == "Your order is confirmed."


import pytest

from langchain_core.messages import AIMessage, HumanMessage

import agents.customer_agent as customer_module
import agents.order_agent as order_module
import agents.shipping_agent as shipping_module
import agents.returns_agent as returns_module
import agents.supervisor_agent as supervisor_module


class FailingLLM:
    def invoke(self, messages):
        raise RuntimeError("Ollama connection refused")


@pytest.mark.parametrize(
    "module,node_name",
    [
        (customer_module, "customer_agent_node"),
        (order_module, "order_agent_node"),
        (shipping_module, "shipping_agent_node"),
        (returns_module, "returns_agent_node"),
        (supervisor_module, "supervisor_node"),
    ],
)
def test_agent_nodes_handle_llm_failure(
    monkeypatch,
    module,
    node_name,
):
    monkeypatch.setattr(
        module,
        "llm_with_tools",
        FailingLLM(),
    )

    # Prevent supervisor sensitive-action detection
    # from interfering with this LLM failure test.
    if module is supervisor_module:
        monkeypatch.setattr(
            module,
            "detect_sensitive_action",
            lambda state: None,
        )

    node = getattr(module, node_name)

    result = node({
        "messages": [
            HumanMessage(content="I need help with my order.")
        ],
        "customer_id": 1,
    })

    assert isinstance(result["messages"][0], AIMessage)
    assert result["messages"][0].content == SAFE_ERROR_MESSAGE


from langchain.tools import tool
from langchain_core.messages import ToolMessage
from langgraph.prebuilt import ToolNode

from agents.error_handling import TOOL_ERROR_MESSAGE



def invoke_tool_node_in_graph(tool_node, call_id):
    from langgraph.graph import END, START, MessagesState, StateGraph

    builder = StateGraph(MessagesState)
    builder.add_node("tools", tool_node)
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)

    graph = builder.compile()

    return graph.invoke({
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "failing_tool",
                        "args": {},
                        "id": call_id,
                        "type": "tool_call",
                    }
                ],
            )
        ]
    })


def test_tool_failure_is_handled_safely():

    @tool
    def failing_tool():
        """A tool that simulates a database failure."""
        raise RuntimeError("Database connection password failure")

    tool_node = ToolNode(
        [failing_tool],
        handle_tool_errors=TOOL_ERROR_MESSAGE,
    )

    result = invoke_tool_node_in_graph(
        tool_node,
        "call-failure-1",
    )

    tool_message = result["messages"][-1]

    assert isinstance(tool_message, ToolMessage)
    assert tool_message.content == TOOL_ERROR_MESSAGE
    assert "password" not in tool_message.content


def test_tool_failure_does_not_expose_database_error():

    @tool
    def failing_tool():
        """Simulate a database error."""
        raise RuntimeError("SQL password=secret123")

    tool_node = ToolNode(
        [failing_tool],
        handle_tool_errors=TOOL_ERROR_MESSAGE,
    )

    result = invoke_tool_node_in_graph(
        tool_node,
        "call-failure-2",
    )

    content = result["messages"][-1].content

    assert "secret123" not in content
    assert "SQL" not in content
    assert content == TOOL_ERROR_MESSAGE





class SequenceLLM:
    """Return predefined responses in sequence."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)

        if not self.responses:
            raise AssertionError("Unexpected additional LLM invocation")

        return self.responses.pop(0)


def make_tool_call(name, args, call_id):
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": name,
                "args": args,
                "id": call_id,
                "type": "tool_call",
            }
        ],
    )


def test_supervisor_recovers_after_specialist_failure(monkeypatch):

    import agents.supervisor_agent as supervisor_module

    def failing_specialist(state):
        raise RuntimeError("Specialist Agent unavailable")

    monkeypatch.setattr(
        supervisor_module.order_agent,
        "invoke",
        failing_specialist,
    )

    fake_supervisor_llm = SequenceLLM([
        make_tool_call(
            "ask_order_agent",
            {"question": "Show me order 1"},
            "specialist-failure-1",
        ),
        AIMessage(
            content="I'm sorry, I couldn't retrieve your order details right now."
        ),
    ])

    monkeypatch.setattr(
        supervisor_module,
        "llm_with_tools",
        fake_supervisor_llm,
    )

    graph = supervisor_module.builder.compile()

    result = graph.invoke({
        "messages": [
            HumanMessage(content="Show me order 1")
        ],
        "customer_id": 1,
    })

    assert result["messages"][-1].content == (
        "I'm sorry, I couldn't retrieve your order details right now."
    )

    assert len(fake_supervisor_llm.calls) == 2

    tool_messages = [
        message
        for message in fake_supervisor_llm.calls[1]
        if isinstance(message, ToolMessage)
    ]

    assert tool_messages
    assert TOOL_ERROR_MESSAGE in tool_messages[-1].content


def test_supervisor_recovers_after_specialist_tool_failure(monkeypatch):

    import agents.supervisor_agent as supervisor_module
    import agents.order_agent as order_module
    import tools.order_tools as order_tools_module

    def failing_database_query(*args, **kwargs):
        raise RuntimeError("Database connection failed")

    monkeypatch.setattr(
        order_tools_module,
        "get_order_details",
        failing_database_query,
    )

    fake_order_llm = SequenceLLM([
        make_tool_call(
            "get_order_information",
            {"order_id": 1},
            "database-failure-1",
        ),
        AIMessage(
            content="I couldn't retrieve the order details right now."
        ),
    ])

    monkeypatch.setattr(
        order_module,
        "llm_with_tools",
        fake_order_llm,
    )

    fake_supervisor_llm = SequenceLLM([
        make_tool_call(
            "ask_order_agent",
            {"question": "Show me order 1"},
            "specialist-tool-failure-1",
        ),
        AIMessage(
            content="I'm sorry, the order information is temporarily unavailable."
        ),
    ])

    monkeypatch.setattr(
        supervisor_module,
        "llm_with_tools",
        fake_supervisor_llm,
    )

    graph = supervisor_module.builder.compile()

    result = graph.invoke({
        "messages": [
            HumanMessage(content="Show me order 1")
        ],
        "customer_id": 1,
    })

    assert result["messages"][-1].content == (
        "I'm sorry, the order information is temporarily unavailable."
    )

    assert len(fake_order_llm.calls) == 2
    assert len(fake_supervisor_llm.calls) == 2
