
import uuid

import pytest

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command

import agents.supervisor_agent as supervisor_module
from api.api import DB_URI
from agents.supervisor_agent import build_supervisor


@pytest.mark.integration
def test_human_approval_and_resume(monkeypatch):

    conversation_id = f"pytest-approval-{uuid.uuid4()}"

    config = {
        "configurable": {
            "thread_id": conversation_id
        }
    }

    executed_operations = []

    # Mock the database operation to avoid modifying real data.
    def fake_update_order_status(**kwargs):
        executed_operations.append(kwargs)
        return "Order status updated successfully"

    monkeypatch.setattr(
        supervisor_module,
        "update_order_status",
        fake_update_order_status,
    )

    with PostgresSaver.from_conn_string(DB_URI) as checkpointer:

        checkpointer.setup()
        supervisor = build_supervisor(checkpointer)

        # 1. Request cancellation.
        result = supervisor.invoke(
            {
                "messages": [
                    HumanMessage(content="I want to cancel order 1")
                ]
            },
            config=config,
        )

        interrupts = result.get("__interrupt__", [])

        assert interrupts, "Expected an approval interrupt"

        approval_data = interrupts[0].value

        assert approval_data["action"] == "cancel_order"
        assert approval_data["order_id"] == 1

        # No operation should execute before approval.
        assert executed_operations == []

        # 2. Approve the action.
        resumed_result = supervisor.invoke(
            Command(
                resume={
                    "approved": True,
                    "reason": "Approved by customer"
                }
            ),
            config=config,
        )

        # 3. Verify graph resumed.
        assert not resumed_result.get("__interrupt__", [])

        # 4. Verify database operation was called after approval.
        assert len(executed_operations) == 1

        assert executed_operations[0] == {
            "order_id": 1,
            "new_status": "cancelled",
            "actor_role": "support_agent",
        }

        final_response = str(
            resumed_result["messages"][-1].content
        )

        assert "successfully" in final_response.lower()


@pytest.mark.integration
def test_human_rejection(monkeypatch):

    conversation_id = f"pytest-rejection-{uuid.uuid4()}"

    config = {
        "configurable": {
            "thread_id": conversation_id
        }
    }

    executed_operations = []

    def fake_update_order_status(**kwargs):
        executed_operations.append(kwargs)
        return "Order status updated successfully"

    monkeypatch.setattr(
        supervisor_module,
        "update_order_status",
        fake_update_order_status,
    )

    with PostgresSaver.from_conn_string(DB_URI) as checkpointer:

        checkpointer.setup()
        supervisor = build_supervisor(checkpointer)

        # 1. Request cancellation.
        result = supervisor.invoke(
            {
                "messages": [
                    HumanMessage(content="I want to cancel order 1")
                ]
            },
            config=config,
        )

        interrupts = result.get("__interrupt__", [])

        assert interrupts, "Expected approval interrupt"

        # No operation before decision.
        assert executed_operations == []

        # 2. Reject the action.
        resumed_result = supervisor.invoke(
            Command(
                resume={
                    "approved": False,
                    "reason": "Customer cancellation was rejected"
                }
            ),
            config=config,
        )

        # 3. Verify graph resumed.
        assert not resumed_result.get("__interrupt__", [])

        final_response = str(
            resumed_result["messages"][-1].content
        )

        # 4. Verify operation was never executed.
        assert executed_operations == []

        assert "rejected" in final_response.lower()
