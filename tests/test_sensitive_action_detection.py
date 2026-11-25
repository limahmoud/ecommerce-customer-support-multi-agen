import pytest

from langchain_core.messages import HumanMessage, AIMessage

from agents.supervisor_agent import detect_sensitive_action


def get_state(question, previous_messages=None):
    messages = previous_messages or []
    messages = [*messages, HumanMessage(content=question)]

    return {"messages": messages}


@pytest.mark.parametrize(
    "question",
    [
        "Show my return status",
        "What is my return status for order 1?",
        "Show return details for order 1",
        "What is my refund status?",
        "Has my refund been processed?",
        "What is the cancellation policy?",
    ],
)
def test_status_questions_do_not_trigger_approval(question):

    result = detect_sensitive_action(get_state(question))

    assert result is None


@pytest.mark.parametrize(
    "question, expected_action, expected_id",
    [
        ("Please cancel order 1", "cancel_order", 1),
        ("I want to return order 2", "create_return", 2),
        ("I want a refund for return 3", "refund", 3),
    ],
)
def test_explicit_sensitive_actions_trigger_approval(
    question,
    expected_action,
    expected_id,
):

    result = detect_sensitive_action(get_state(question))

    assert isinstance(result, AIMessage)
    assert len(result.tool_calls) == 1

    tool_call = result.tool_calls[0]

    assert tool_call["name"] == "request_sensitive_action"
    assert tool_call["args"]["action"] == expected_action

    if expected_action == "refund":
        assert tool_call["args"]["return_id"] == expected_id
    else:
        assert tool_call["args"]["order_id"] == expected_id


def test_cancel_without_order_id_asks_customer():

    result = detect_sensitive_action(
        get_state("I want to cancel my order")
    )

    assert isinstance(result, AIMessage)
    assert not result.tool_calls
    assert "order ID" in result.content


def test_refund_without_return_id_asks_customer():

    result = detect_sensitive_action(
        get_state("I want a refund")
    )

    assert isinstance(result, AIMessage)
    assert not result.tool_calls
    assert "return ID" in result.content


def test_sensitive_action_uses_previous_order_id():

    previous = [
        HumanMessage(content="Show me order 5 details"),
        AIMessage(content="Order details retrieved"),
    ]

    result = detect_sensitive_action(
        get_state("Please cancel it", previous)
    )

    assert isinstance(result, AIMessage)
    assert result.tool_calls[0]["args"]["order_id"] == 5