
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.api import app


class FakeSupervisor:
    """Mock Supervisor بدل تشغيل Ollama والـ Agents."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def invoke(self, input_data, config=None):
        self.calls.append({
            "input": input_data,
            "config": config,
        })

        return self.responses.pop(0)


@pytest.fixture
def client():
    return TestClient(app)


def test_api_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_home_endpoint(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_chat_completed(client):
    fake = FakeSupervisor([
        {
            "messages": [
                SimpleNamespace(content="Customer information retrieved")
            ]
        }
    ])

    app.state.supervisor_agent = fake

    response = client.post(
        "/chat",
        json={"question": "Show customer 1"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert "Customer information" in response.json()["answer"]


def test_conversation_memory_thread_id(client):
    fake = FakeSupervisor([
        {
            "messages": [
                SimpleNamespace(content="Order 1 details")
            ]
        },
        {
            "messages": [
                SimpleNamespace(content="Shipment for order 1")
            ]
        },
    ])

    app.state.supervisor_agent = fake

    conversation_id = "pytest-memory-001"

    first = client.post(
        "/chat",
        json={
            "question": "Show order 1",
            "conversation_id": conversation_id,
        },
    )

    second = client.post(
        "/chat",
        json={
            "question": "What is its shipment status?",
            "conversation_id": conversation_id,
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200

    first_thread = fake.calls[0]["config"]["configurable"]["thread_id"]
    second_thread = fake.calls[1]["config"]["configurable"]["thread_id"]

    assert first_thread == second_thread == conversation_id


def test_human_approval_interrupt(client):
    approval_data = {
        "action": "cancel_order",
        "order_id": 1,
        "details": "Cancel order 1",
    }

    fake = FakeSupervisor([
        {
            "__interrupt__": [
                SimpleNamespace(value=approval_data)
            ]
        }
    ])

    app.state.supervisor_agent = fake

    response = client.post(
        "/chat",
        json={
            "question": "Cancel order 1",
            "conversation_id": "pytest-approval-001",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "approval_required"
    assert response.json()["approval_request"]["action"] == "cancel_order"


def test_resume_after_approval(client):
    fake = FakeSupervisor([
        {
            "messages": [
                SimpleNamespace(content="Approval received")
            ]
        }
    ])

    app.state.supervisor_agent = fake

    response = client.post(
        "/approval",
        json={
            "conversation_id": "pytest-approval-001",
            "approved": True,
            "reason": "Approved by customer",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"

    command = fake.calls[0]["input"]

    assert command.resume["approved"] is True
    assert command.resume["reason"] == "Approved by customer"
