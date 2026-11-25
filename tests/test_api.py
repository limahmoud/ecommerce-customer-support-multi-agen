
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import api.api as api_module
from api.api import app
from security.dependencies import get_current_user
from database.db import SessionLocal
from database.models import User, AuditLog
from uuid import uuid4
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


def make_test_user(role="customer"):
    return SimpleNamespace(
        id=999,
        customer_id=1,
        email="pytest@example.com",
        role=role,
        is_active=True,
    )


def authenticate_as(role="customer"):
    user = make_test_user(role)

    app.dependency_overrides[get_current_user] = lambda: user

    return user


@pytest.fixture
def client():
    app.dependency_overrides.clear()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def mock_customer_conversation(monkeypatch, conversation_id):
    monkeypatch.setattr(
        api_module,
        "create_conversation",
        lambda **kwargs: {
            "id": conversation_id,
            "title": kwargs.get("title", "New Conversation"),
        },
    )

    monkeypatch.setattr(
        api_module,
        "update_conversation_last_message",
        lambda *args, **kwargs: True,
    )


def test_api_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_home_endpoint(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_chat_completed(client, monkeypatch):
    authenticate_as("customer")

    mock_customer_conversation(
        monkeypatch,
        "pytest-chat-001",
    )

    fake = FakeSupervisor([
        {
            "messages": [
                SimpleNamespace(
                    content="Customer information retrieved"
                )
            ]
        }
    ])

    app.state.supervisor_agent = fake

    response = client.post(
        "/chat",
        json={"question": "Show customer 1"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert "Customer information" in response.json()["answer"]


def test_conversation_memory_thread_id(client, monkeypatch):
    authenticate_as("customer")

    conversation_id = "pytest-memory-001"

    monkeypatch.setattr(
        api_module,
        "validate_conversation",
        lambda conversation_id, customer_id: {
            "id": conversation_id,
            "title": "Existing Conversation",
        },
    )

    monkeypatch.setattr(
        api_module,
        "update_conversation_last_message",
        lambda *args, **kwargs: True,
    )

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


def test_human_approval_interrupt(client, monkeypatch):
    authenticate_as("customer")

    conversation_id = "pytest-approval-001"

    monkeypatch.setattr(
        api_module,
        "validate_conversation",
        lambda conversation_id, customer_id: {
            "id": conversation_id,
            "title": "Existing Conversation",
        },
    )

    monkeypatch.setattr(
        api_module,
        "update_conversation_last_message",
        lambda *args, **kwargs: True,
    )

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
            "conversation_id": conversation_id,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "approval_required"
    assert response.json()["approval_request"]["action"] == "cancel_order"


def test_resume_after_approval(client, monkeypatch):
    authenticate_as("support_agent")

    conversation_id = "pytest-approval-001"

    monkeypatch.setattr(
        api_module,
        "get_pending_approval",
        lambda conversation_id: {
            "action": "cancel_order",
            "order_id": 1,
        },
    )

    monkeypatch.setattr(
        api_module,
        "get_conversation_owner_id",
        lambda conversation_id: 1,
    )

    monkeypatch.setattr(
        api_module,
        "update_conversation_last_message",
        lambda *args, **kwargs: True,
    )

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
            "conversation_id": conversation_id,
            "approved": True,
            "reason": "Approved by support agent",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"

    command = fake.calls[0]["input"]

    assert command.resume["approved"] is True
    assert command.resume["reason"] == "Approved by support agent"
    assert command.resume["actor_user_id"] == 999
    assert command.resume["actor_role"] == "support_agent"


# =====================================================
# API CONVERSATION SECURITY TESTS
# =====================================================

def test_customer_cannot_list_other_customer_conversations(client):
    authenticate_as("customer")

    response = client.get("/conversations/2")

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "You cannot access another customer's conversations."
    )


def test_customer_cannot_read_other_customer_conversation_messages(
    client,
    monkeypatch,
):
    authenticate_as("customer")

    conversation_id = "11111111-1111-1111-1111-111111111111"

    monkeypatch.setattr(
        api_module,
        "get_customer_conversation",
        lambda conversation_id, customer_id: None,
    )

    response = client.get(
        f"/conversations/{conversation_id}/messages"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found."



# ==========================================
# APPROVAL ROLE-BASED ACCESS CONTROL
# ==========================================

@pytest.mark.parametrize(
    "role",
    ["customer", "shipping_agent"],
)
def test_unauthorized_roles_cannot_access_approval(
    client,
    role,
):
    authenticate_as(role)

    response = client.post(
        "/approval",
        json={
            "conversation_id": "test-conversation",
            "approved": True,
            "reason": "Test approval",
        },
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    "role,action",
    [
        ("support_agent", "refund"),
        ("returns_agent", "cancel_order"),
        ("returns_agent", "create_return"),
    ],
)
def test_role_cannot_approve_unauthorized_action(
    client,
    monkeypatch,
    role,
    action,
):
    authenticate_as(role)

    monkeypatch.setattr(
        api_module,
        "get_conversation_config",
        lambda conversation_id: {},
    )

    monkeypatch.setattr(
        api_module,
        "get_pending_approval",
        lambda conversation_id: {"action": action},
    )

    response = client.post(
        "/approval",
        json={
            "conversation_id": "test-conversation",
            "approved": True,
            "reason": "Test approval",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Your role cannot approve this action."
    )



# ==========================================
# APPROVAL SUCCESS & FAILURE TESTS
# ==========================================


@pytest.mark.parametrize(
    "role,action",
    [
        ("admin", "cancel_order"),
        ("admin", "create_return"),
        ("admin", "refund"),
        ("support_agent", "cancel_order"),
        ("support_agent", "create_return"),
        ("returns_agent", "refund"),
    ],
)
def test_authorized_roles_can_submit_approval(
    client,
    monkeypatch,
    role,
    action,
):
    db = None
    test_admin = None

    if role == "admin":
        db = SessionLocal()

        test_admin = User(
            email=f"admin-approval-{uuid4().hex}@example.com",
            hashed_password="not-used",
            role="admin",
            customer_id=None,
            is_active=True,
        )

        db.add(test_admin)
        db.commit()
        db.refresh(test_admin)

        app.dependency_overrides[get_current_user] = lambda: test_admin

    else:
        authenticate_as(role)

    try:
        conversation_id = "test-authorized-approval"

        monkeypatch.setattr(
            api_module,
            "get_conversation_config",
            lambda conversation_id: {
                "configurable": {"thread_id": conversation_id}
            },
        )

        monkeypatch.setattr(
            api_module,
            "get_pending_approval",
            lambda conversation_id: {"action": action},
        )

        monkeypatch.setattr(
            api_module,
            "get_conversation_owner_id",
            lambda conversation_id: 1,
        )

        monkeypatch.setattr(
            api_module,
            "update_conversation_last_message",
            lambda *args, **kwargs: True,
        )

        fake = FakeSupervisor([
            {
                "messages": [
                    SimpleNamespace(
                        content="Action completed successfully"
                    )
                ]
            }
        ])

        app.state.supervisor_agent = fake

        response = client.post(
            "/approval",
            json={
                "conversation_id": conversation_id,
                "approved": True,
                "reason": "Authorized approval",
            },
        )

        assert response.status_code == 200
        assert response.json()["status"] == "completed"

        resume = fake.calls[0]["input"].resume

        assert resume["approved"] is True
        assert resume["actor_role"] == role

        if role == "admin":
            audit = db.query(AuditLog).filter(
                AuditLog.actor_user_id == test_admin.id,
                AuditLog.action == f"approval_{action}",
            ).first()

            assert audit is not None
            assert audit.actor_email == test_admin.email
            assert audit.new_value["approved"] is True

    finally:
        if db is not None:
            if test_admin is not None:
                db.query(AuditLog).filter(
                    AuditLog.actor_user_id == test_admin.id
                ).delete(synchronize_session=False)

                db.delete(test_admin)
                db.commit()

            db.close()


def test_rejected_approval_is_forwarded_as_rejected(
    client,
    monkeypatch,
):
    authenticate_as("support_agent")

    conversation_id = "test-rejected-approval"

    monkeypatch.setattr(
        api_module,
        "get_conversation_config",
        lambda conversation_id: {"configurable": {"thread_id": conversation_id}},
    )

    monkeypatch.setattr(
        api_module,
        "get_pending_approval",
        lambda conversation_id: {"action": "cancel_order"},
    )

    monkeypatch.setattr(
        api_module,
        "get_conversation_owner_id",
        lambda conversation_id: 1,
    )

    monkeypatch.setattr(
        api_module,
        "update_conversation_last_message",
        lambda *args, **kwargs: True,
    )

    fake = FakeSupervisor([
        {
            "messages": [
                SimpleNamespace(content="Action rejected.")
            ]
        }
    ])

    app.state.supervisor_agent = fake

    response = client.post(
        "/approval",
        json={
            "conversation_id": conversation_id,
            "approved": False,
            "reason": "I do not approve this action.",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"

    resume = fake.calls[0]["input"].resume

    assert resume["approved"] is False
    assert resume["reason"] == "I do not approve this action."


def test_approval_fails_when_no_pending_request(
    client,
    monkeypatch,
):
    authenticate_as("admin")

    monkeypatch.setattr(
        api_module,
        "get_conversation_config",
        lambda conversation_id: {},
    )

    monkeypatch.setattr(
        api_module,
        "get_pending_approval",
        lambda conversation_id: None,
    )

    response = client.post(
        "/approval",
        json={
            "conversation_id": "test-no-pending",
            "approved": True,
            "reason": "Test",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "There is no pending approval for this conversation."
    )


def test_approval_fails_for_unknown_action(
    client,
    monkeypatch,
):
    authenticate_as("admin")

    monkeypatch.setattr(
        api_module,
        "get_conversation_config",
        lambda conversation_id: {},
    )

    monkeypatch.setattr(
        api_module,
        "get_pending_approval",
        lambda conversation_id: {"action": "delete_customer"},
    )

    response = client.post(
        "/approval",
        json={
            "conversation_id": "test-unknown-action",
            "approved": True,
            "reason": "Test",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown approval action."



# ==========================================
# PENDING APPROVALS API TESTS
# ==========================================

@pytest.mark.parametrize(
    "role,expected_actions",
    [
        ("support_agent", {"cancel_order", "create_return"}),
        ("returns_agent", {"refund"}),
        ("admin", {"cancel_order", "create_return", "refund"}),
    ],
)
def test_staff_can_list_authorized_pending_approvals(
    client,
    monkeypatch,
    role,
    expected_actions,
):
    authenticate_as(role)

    conversations = [
        SimpleNamespace(
            id="conversation-1",
            customer_id=1,
            title="Cancel order",
        ),
        SimpleNamespace(
            id="conversation-2",
            customer_id=2,
            title="Create return",
        ),
        SimpleNamespace(
            id="conversation-3",
            customer_id=3,
            title="Refund",
        ),
    ]

    pending_by_id = {
        "conversation-1": {"action": "cancel_order"},
        "conversation-2": {"action": "create_return"},
        "conversation-3": {"action": "refund"},
    }

    class FakeQuery:
        def order_by(self, *args):
            return self

        def all(self):
            return conversations

    class FakeDB:
        def query(self, model):
            assert model is api_module.Conversation
            return FakeQuery()

        def close(self):
            pass

    monkeypatch.setattr(
        api_module,
        "SessionLocal",
        lambda: FakeDB(),
    )

    monkeypatch.setattr(
        api_module,
        "get_pending_approval",
        lambda conversation_id: pending_by_id.get(conversation_id),
    )

    response = client.get("/approvals")

    assert response.status_code == 200

    data = response.json()

    returned_actions = {
        item["action"]
        for item in data["approvals"]
    }

    assert returned_actions == expected_actions
    assert data["total"] == len(expected_actions)


def test_customer_cannot_list_pending_approvals(client):
    authenticate_as("customer")

    response = client.get("/approvals")

    assert response.status_code == 403


def test_returns_agent_can_approve_return(client, monkeypatch):

    authenticate_as("returns_agent")

    def fake_update_return_status(**kwargs):
        assert kwargs["return_id"] == 2
        assert kwargs["new_status"] == "approved"
        assert kwargs["actor_role"] == "returns_agent"

        return {
            "success": True,
            "return_id": 2,
            "old_status": "pending",
            "new_status": "approved",
        }

    monkeypatch.setattr(
        api_module,
        "update_return_status",
        fake_update_return_status,
    )

    response = client.patch(
        "/returns/2/status",
        json={"new_status": "approved"},
    )

    assert response.status_code == 200
    assert response.json()["new_status"] == "approved"


def test_admin_return_status_update_passes_audit_identity(client, monkeypatch):
    admin = authenticate_as("admin")
    captured = {}

    def fake_update_return_status(**kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "return_id": 2,
            "old_status": "pending",
            "new_status": "approved",
        }

    monkeypatch.setattr(
        api_module,
        "update_return_status",
        fake_update_return_status,
    )

    response = client.patch(
        "/returns/2/status",
        json={"new_status": "approved"},
    )

    assert response.status_code == 200
    assert captured["actor_role"] == "admin"
    assert captured["actor_user_id"] == admin.id
    assert captured["actor_email"] == admin.email

def test_customer_cannot_update_return_status(client):

    authenticate_as("customer")

    response = client.patch(
        "/returns/2/status",
        json={"new_status": "approved"},
    )

    assert response.status_code == 403


def test_support_agent_cannot_update_return_status(client):

    authenticate_as("support_agent")

    response = client.patch(
        "/returns/2/status",
        json={"new_status": "approved"},
    )

    assert response.status_code == 403


def test_return_status_invalid_transition(client, monkeypatch):

    authenticate_as("returns_agent")

    def fake_update_return_status(**kwargs):
        raise ValueError(
            "Cannot change return status from 'pending' to 'received'."
        )

    monkeypatch.setattr(
        api_module,
        "update_return_status",
        fake_update_return_status,
    )

    response = client.patch(
        "/returns/2/status",
        json={"new_status": "received"},
    )

    assert response.status_code == 400


# ==========================================
# CUSTOMER ORDERS & RETURNS API TESTS
# ==========================================


def test_customer_can_list_orders(client, monkeypatch):

    user = authenticate_as("customer")

    expected_orders = [
        {"order_id": 10, "status": "delivered"},
        {"order_id": 11, "status": "processing"},
    ]

    def fake_get_customer_orders(customer_id):
        assert customer_id == user.customer_id
        return expected_orders

    monkeypatch.setattr(
        api_module,
        "get_customer_orders",
        fake_get_customer_orders,
    )

    response = client.get("/orders")

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert response.json()["orders"] == expected_orders


def test_customer_can_get_order_details(client, monkeypatch):

    user = authenticate_as("customer")

    expected_order = {
        "order_id": 10,
        "status": "delivered",
    }

    def fake_get_order_details(order_id, customer_id):
        assert order_id == 10
        assert customer_id == user.customer_id
        return expected_order

    monkeypatch.setattr(
        api_module,
        "get_order_details",
        fake_get_order_details,
    )

    response = client.get("/orders/10")

    assert response.status_code == 200
    assert response.json()["order"] == expected_order


def test_customer_cannot_access_another_customer_order(
    client,
    monkeypatch,
):

    authenticate_as("customer")

    monkeypatch.setattr(
        api_module,
        "get_order_details",
        lambda order_id, customer_id: None,
    )

    response = client.get("/orders/999")

    assert response.status_code == 404


def test_customer_can_list_returns(client, monkeypatch):

    user = authenticate_as("customer")

    expected_returns = [
        {
            "return_id": 5,
            "order_id": 10,
            "status": "pending",
        }
    ]

    def fake_get_customer_returns(customer_id):
        assert customer_id == user.customer_id
        return expected_returns

    monkeypatch.setattr(
        api_module,
        "get_customer_returns",
        fake_get_customer_returns,
    )

    response = client.get("/returns")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["returns"] == expected_returns


def test_staff_cannot_access_customer_orders_or_returns(client):

    authenticate_as("support_agent")

    orders_response = client.get("/orders")
    returns_response = client.get("/returns")

    assert orders_response.status_code == 403
    assert returns_response.status_code == 403