
import pytest

from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.models import (
    Base,
    Customer,
    Order,
    Shipment,
    Return,
    User,
    AuditLog,
)
from database import operations


import uuid
from graph.state import SupportState
from langchain_core.messages import AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command

from api.api import DB_URI
from agents.supervisor_agent import request_sensitive_action

@pytest.fixture
def test_db(monkeypatch):

    # Create isolated in-memory SQLite database
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    TestingSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    # Replace production SessionLocal with test SessionLocal
    monkeypatch.setattr(
        operations,
        "SessionLocal",
        TestingSessionLocal,
    )

    # Create test customer
    with TestingSessionLocal() as db:

        customer = Customer(
            name="Test Customer",
            email="test@example.com",
        )

        db.add(customer)
        db.flush()

        # Create pending order
        order = Order(
            customer_id=customer.id,
            status="pending",
            total_amount=Decimal("100.00"),
        )

        db.add(order)
        db.flush()

        # Create pending shipment
        shipment = Shipment(
            order_id=order.id,
            tracking_number="TEST-TRACK-001",
            carrier="Test Carrier",
            status="pending",
        )

        db.add(shipment)
        db.flush()

        admin = User(
            email="admin-audit@test.com",
            hashed_password="test-hash",
            role="admin",
            is_active=True,
        )

        db.add(admin)
        db.flush()

        db.commit()

        data = {
            "customer_id": customer.id,
            "order_id": order.id,
            "shipment_id": shipment.id,
            "admin_user_id": admin.id,
            "admin_email": admin.email,
        }

    yield data

    Base.metadata.drop_all(engine)
    engine.dispose()


# ==========================================
# 1. ORDER OPERATIONS
# ==========================================

def test_update_order_status_success(test_db):

    result = operations.update_order_status(
        order_id=test_db["order_id"],
        new_status="confirmed",
        actor_role="admin",
    )

    assert result["success"] is True
    assert result["old_status"] == "pending"
    assert result["new_status"] == "confirmed"


def test_update_order_status_unauthorized(test_db):

    with pytest.raises(PermissionError):

        operations.update_order_status(
            order_id=test_db["order_id"],
            new_status="confirmed",
            actor_role="customer",
        )


def test_update_order_status_invalid_transition(test_db):

    with pytest.raises(ValueError):

        operations.update_order_status(
            order_id=test_db["order_id"],
            new_status="delivered",
            actor_role="admin",
        )


# ==========================================
# 2. SHIPMENT OPERATIONS
# ==========================================

def test_update_shipment_status_success(test_db):

    result = operations.update_shipment_status(
        shipment_id=test_db["shipment_id"],
        new_status="shipped",
        actor_role="admin",
    )

    assert result["success"] is True
    assert result["old_status"] == "pending"
    assert result["new_status"] == "shipped"


def test_update_shipment_status_invalid_transition(test_db):

    with pytest.raises(ValueError):

        operations.update_shipment_status(
            shipment_id=test_db["shipment_id"],
            new_status="delivered",
            actor_role="admin",
        )


# ==========================================
# 3. RETURN OPERATIONS
# ==========================================

def test_create_return_success(test_db):

    # Create a delivered order
    with operations.SessionLocal() as db:

        order = db.get(Order, test_db["order_id"])
        order.status = "delivered"
        db.commit()

    result = operations.create_return(
        order_id=test_db["order_id"],
        reason="Damaged product",
        actor_role="admin",
    )

    assert result["success"] is True
    assert result["order_id"] == test_db["order_id"]
    assert result["status"] == "pending"
    assert result["refund_status"] == "not_requested"


def test_create_return_for_undelivered_order(test_db):

    with pytest.raises(ValueError):

        operations.create_return(
            order_id=test_db["order_id"],
            reason="Damaged product",
            actor_role="admin",
        )


def test_update_return_status_approved(test_db):

    with operations.SessionLocal() as db:
        returned = Return(
            order_id=test_db["order_id"],
            reason="Damaged product",
            status="pending",
            refund_status="not_requested",
        )
        db.add(returned)
        db.commit()
        return_id = returned.id

    result = operations.update_return_status(
        return_id=return_id,
        new_status="approved",
        actor_role="returns_agent",
    )

    assert result["success"] is True
    assert result["old_status"] == "pending"
    assert result["new_status"] == "approved"


def test_update_return_status_rejected(test_db):

    with operations.SessionLocal() as db:
        returned = Return(
            order_id=test_db["order_id"],
            reason="Ordered by mistake",
            status="pending",
            refund_status="not_requested",
        )
        db.add(returned)
        db.commit()
        return_id = returned.id

    result = operations.update_return_status(
        return_id=return_id,
        new_status="rejected",
        actor_role="returns_agent",
    )

    assert result["success"] is True
    assert result["new_status"] == "rejected"


def test_update_return_status_invalid_transition(test_db):

    with operations.SessionLocal() as db:
        returned = Return(
            order_id=test_db["order_id"],
            reason="Damaged product",
            status="pending",
            refund_status="not_requested",
        )
        db.add(returned)
        db.commit()
        return_id = returned.id

    with pytest.raises(ValueError):
        operations.update_return_status(
            return_id=return_id,
            new_status="received",
            actor_role="returns_agent",
        )


def test_customer_cannot_update_return_status(test_db):

    with operations.SessionLocal() as db:
        returned = Return(
            order_id=test_db["order_id"],
            reason="Damaged product",
            status="pending",
            refund_status="not_requested",
        )
        db.add(returned)
        db.commit()
        return_id = returned.id

    with pytest.raises(PermissionError):
        operations.update_return_status(
            return_id=return_id,
            new_status="approved",
            actor_role="customer",
        )


# ==========================================
# 4. REFUND OPERATIONS
# ==========================================

def test_refund_before_return_approval(test_db):

    # Create a return that is still pending
    with operations.SessionLocal() as db:

        returned = Return(
            order_id=test_db["order_id"],
            reason="Damaged product",
            status="pending",
            refund_status="not_requested",
        )

        db.add(returned)
        db.commit()
        return_id = returned.id

    with pytest.raises(ValueError):

        operations.update_refund_status(
            return_id=return_id,
            new_refund_status="pending",
            actor_role="returns_agent",
        )


def test_update_refund_status_success(test_db):

    # Create an approved return
    with operations.SessionLocal() as db:

        returned = Return(
            order_id=test_db["order_id"],
            reason="Damaged product",
            status="approved",
            refund_status="not_requested",
        )

        db.add(returned)
        db.commit()
        return_id = returned.id

    result = operations.update_refund_status(
        return_id=return_id,
        new_refund_status="pending",
        actor_role="returns_agent",
    )

    assert result["success"] is True
    assert result["old_status"] == "not_requested"
    assert result["new_status"] == "pending"



def test_request_refund_success(test_db):

    with operations.SessionLocal() as db:
        returned = Return(
            order_id=test_db["order_id"],
            reason="Damaged product",
            status="approved",
            refund_status="not_requested",
        )
        db.add(returned)
        db.commit()
        return_id = returned.id

    result = operations.request_refund(
        return_id=return_id,
        customer_id=test_db["customer_id"],
    )

    assert result["success"] is True
    assert result["new_status"] == "pending"


def test_request_refund_is_idempotent(test_db):

    with operations.SessionLocal() as db:
        returned = Return(
            order_id=test_db["order_id"],
            reason="Damaged product",
            status="approved",
            refund_status="pending",
        )
        db.add(returned)
        db.commit()
        return_id = returned.id

    result = operations.request_refund(
        return_id=return_id,
        customer_id=test_db["customer_id"],
    )

    assert result["success"] is True
    assert result["new_status"] == "pending"


def test_customer_cannot_request_refund_for_another_customer(test_db):

    with operations.SessionLocal() as db:
        other_customer = Customer(
            name="Another Customer",
            email="another-refund-request@example.com",
        )
        db.add(other_customer)
        db.flush()

        other_order = Order(
            customer_id=other_customer.id,
            status="delivered",
            total_amount=Decimal("200.00"),
        )
        db.add(other_order)
        db.flush()

        returned = Return(
            order_id=other_order.id,
            reason="Damaged product",
            status="approved",
            refund_status="not_requested",
        )
        db.add(returned)
        db.commit()
        return_id = returned.id

    with pytest.raises(PermissionError):
        operations.request_refund(
            return_id=return_id,
            customer_id=test_db["customer_id"],
        )


def test_request_refund_before_return_approval(test_db):

    with operations.SessionLocal() as db:
        returned = Return(
            order_id=test_db["order_id"],
            reason="Damaged product",
            status="pending",
            refund_status="not_requested",
        )
        db.add(returned)
        db.commit()
        return_id = returned.id

    with pytest.raises(ValueError):
        operations.request_refund(
            return_id=return_id,
            customer_id=test_db["customer_id"],
        )


@pytest.mark.integration
def test_cancel_order_after_approval(test_db):

    with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
        checkpointer.setup()

        response = run_approval_test(
            checkpointer,
            {
                "action": "cancel_order",
                "order_id": test_db["order_id"],
                "return_id": None,
                "details": "Cancel test order",
                "reason": "Customer requested cancellation",
            },
            approved=True,
            customer_id=test_db["customer_id"],
        )

    with operations.SessionLocal() as db:
        order = db.get(Order, test_db["order_id"])
        assert order.status == "cancelled"

    assert "successfully" in response.lower()


@pytest.mark.integration
def test_cancel_order_after_rejection(test_db):

    with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
        checkpointer.setup()

        response = run_approval_test(
            checkpointer,
            {
                "action": "cancel_order",
                "order_id": test_db["order_id"],
                "return_id": None,
                "details": "Cancel test order",
                "reason": "Customer requested cancellation",
            },
            approved=False,
            customer_id=test_db["customer_id"],
        )

    with operations.SessionLocal() as db:
        order = db.get(Order, test_db["order_id"])
        assert order.status == "pending"

    assert "rejected" in response.lower()


@pytest.mark.integration
def test_create_return_after_approval(test_db):

    # Return is allowed only for delivered orders.
    with operations.SessionLocal() as db:
        order = db.get(Order, test_db["order_id"])
        order.status = "delivered"
        db.commit()

    with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
        checkpointer.setup()

        response = run_approval_test(
            checkpointer,
            {
                "action": "create_return",
                "order_id": test_db["order_id"],
                "return_id": None,
                "details": "Create a product return",
                "reason": "Damaged product",
            },
            approved=True,
            customer_id=test_db["customer_id"],
        )

    with operations.SessionLocal() as db:
        returns = db.scalars(
            select(Return).where(
                Return.order_id == test_db["order_id"]
            )
        ).all()

        assert len(returns) == 1
        assert returns[0].status == "pending"
        assert returns[0].refund_status == "not_requested"

    assert "successfully" in response.lower()


@pytest.mark.integration
def test_create_return_after_rejection(test_db):

    with operations.SessionLocal() as db:
        order = db.get(Order, test_db["order_id"])
        order.status = "delivered"
        db.commit()

    with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
        checkpointer.setup()

        response = run_approval_test(
            checkpointer,
            {
                "action": "create_return",
                "order_id": test_db["order_id"],
                "return_id": None,
                "details": "Create a product return",
                "reason": "Damaged product",
            },
            approved=False,
            customer_id=test_db["customer_id"],
        )

    with operations.SessionLocal() as db:
        returns = db.scalars(
            select(Return).where(
                Return.order_id == test_db["order_id"]
            )
        ).all()

        assert len(returns) == 0

    assert "rejected" in response.lower()


@pytest.mark.integration
def test_refund_after_approval(test_db):

    # Create an approved return.
    with operations.SessionLocal() as db:
        returned = Return(
            order_id=test_db["order_id"],
            reason="Damaged product",
            status="approved",
            refund_status="not_requested",
        )

        db.add(returned)
        db.commit()

        return_id = returned.id

    with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
        checkpointer.setup()

        response = run_approval_test(
            checkpointer,
            {
                "action": "refund",
                "order_id": None,
                "return_id": return_id,
                "details": "Request refund",
                "reason": "Customer requested refund",
            },
            approved=True,
            customer_id=test_db["customer_id"],
        )

    with operations.SessionLocal() as db:
        returned = db.get(Return, return_id)

        assert returned.refund_status == "processing"

    assert "successfully" in response.lower()


@pytest.mark.integration
def test_refund_after_rejection(test_db):

    with operations.SessionLocal() as db:
        returned = Return(
            order_id=test_db["order_id"],
            reason="Damaged product",
            status="approved",
            refund_status="not_requested",
        )

        db.add(returned)
        db.commit()

        return_id = returned.id

    with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
        checkpointer.setup()

        response = run_approval_test(
            checkpointer,
            {
                "action": "refund",
                "order_id": None,
                "return_id": return_id,
                "details": "Request refund",
                "reason": "Customer requested refund",
            },
            approved=False,
            customer_id=test_db["customer_id"],
        )

    with operations.SessionLocal() as db:
        returned = db.get(Return, return_id)

        assert returned.refund_status == "rejected"

    assert "rejected" in response.lower()


def build_approval_test_graph(checkpointer):
    builder = StateGraph(SupportState)

    builder.add_node(
        "tools",
        ToolNode([request_sensitive_action]),
    )

    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)

    return builder.compile(checkpointer=checkpointer)


def run_approval_test(
    checkpointer,
    action_args,
    approved,
    customer_id,
):
    graph = build_approval_test_graph(checkpointer)

    config = {
        "configurable": {
            "thread_id": f"test-{uuid.uuid4()}"
        }
    }

    tool_call = {
        "name": "request_sensitive_action",
        "args": action_args,
        "id": str(uuid.uuid4()),
        "type": "tool_call",
    }

    # Start execution and wait for human approval.
    result = graph.invoke(
        {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[tool_call],
                )
            ],
            "customer_id": customer_id,
        },
        config=config,
    )

    interrupts = result.get("__interrupt__", [])

    assert interrupts, "Expected an approval interrupt"

    test_role = (
        "returns_agent"
        if action_args["action"] == "refund"
        else "support_agent"
    )

    resumed_result = graph.invoke(
        Command(
            resume={
                "approved": approved,
                "reason": "Test approval decision",
                "actor_user_id": 999,
                "actor_role": test_role,
            }
        ),
        config=config,
    )

    assert not resumed_result.get("__interrupt__", [])

    return resumed_result["messages"][-1].content


def test_support_agent_cannot_update_another_customer_order(test_db):

    with operations.SessionLocal() as db:
        other_customer = Customer(
            name="Another Customer",
            email="another@example.com",
        )
        db.add(other_customer)
        db.flush()

        other_order = Order(
            customer_id=other_customer.id,
            status="pending",
            total_amount=Decimal("200.00"),
        )
        db.add(other_order)
        db.commit()
        other_order_id = other_order.id

    with pytest.raises(PermissionError):
        operations.update_order_status(
            order_id=other_order_id,
            new_status="confirmed",
            actor_role="support_agent",
            customer_id=test_db["customer_id"],
        )


def test_support_agent_cannot_create_return_for_another_customer(test_db):

    with operations.SessionLocal() as db:
        other_customer = Customer(
            name="Another Customer",
            email="another-return@example.com",
        )
        db.add(other_customer)
        db.flush()

        other_order = Order(
            customer_id=other_customer.id,
            status="delivered",
            total_amount=Decimal("200.00"),
        )
        db.add(other_order)
        db.commit()
        other_order_id = other_order.id

    with pytest.raises(PermissionError):
        operations.create_return(
            order_id=other_order_id,
            reason="Damaged product",
            actor_role="support_agent",
            customer_id=test_db["customer_id"],
        )


def test_returns_agent_cannot_refund_another_customer_return(test_db):

    with operations.SessionLocal() as db:
        other_customer = Customer(
            name="Another Customer",
            email="another-refund@example.com",
        )
        db.add(other_customer)
        db.flush()

        other_order = Order(
            customer_id=other_customer.id,
            status="delivered",
            total_amount=Decimal("200.00"),
        )
        db.add(other_order)
        db.flush()

        other_return = Return(
            order_id=other_order.id,
            reason="Damaged product",
            status="approved",
            refund_status="not_requested",
        )
        db.add(other_return)
        db.commit()
        other_return_id = other_return.id

    with pytest.raises(PermissionError):
        operations.update_refund_status(
            return_id=other_return_id,
            new_refund_status="pending",
            actor_role="returns_agent",
            customer_id=test_db["customer_id"],
        )



# ==========================================
# 5. ROLE-BASED ACCESS CONTROL MATRIX
# ==========================================

@pytest.mark.parametrize(
    "role",
    ["returns_agent", "shipping_agent", "customer", "order_agent"],
)
def test_unauthorized_roles_cannot_update_order(test_db, role):

    with pytest.raises(PermissionError):
        operations.update_order_status(
            order_id=test_db["order_id"],
            new_status="confirmed",
            actor_role=role,
        )


@pytest.mark.parametrize(
    "role",
    ["support_agent", "returns_agent", "customer", "order_agent"],
)
def test_unauthorized_roles_cannot_update_shipment(test_db, role):

    with pytest.raises(PermissionError):
        operations.update_shipment_status(
            shipment_id=test_db["shipment_id"],
            new_status="shipped",
            actor_role=role,
        )


@pytest.mark.parametrize(
    "role",
    ["shipping_agent", "customer"],
)
def test_unauthorized_roles_cannot_update_refund(test_db, role):

    with pytest.raises(PermissionError):
        operations.update_refund_status(
            return_id=999,
            new_refund_status="pending",
            actor_role=role,
        )


# =====================================================
# ADMIN AUDIT LOG TESTS
# =====================================================

def test_admin_order_status_update_creates_audit_log(test_db):
    result = operations.update_order_status(
        order_id=test_db["order_id"],
        new_status="confirmed",
        actor_role="admin",
        actor_user_id=test_db["admin_user_id"],
        actor_email=test_db["admin_email"],
    )

    assert result["success"] is True

    with operations.SessionLocal() as db:
        log = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "update_order_status",
                AuditLog.entity_id == str(test_db["order_id"]),
            )
        )

        assert log is not None
        assert log.actor_user_id == test_db["admin_user_id"]
        assert log.actor_email == test_db["admin_email"]
        assert log.old_value == {"status": "pending"}
        assert log.new_value == {"status": "confirmed"}


def test_admin_shipment_status_update_creates_audit_log(test_db):
    result = operations.update_shipment_status(
        shipment_id=test_db["shipment_id"],
        new_status="shipped",
        actor_role="admin",
        actor_user_id=test_db["admin_user_id"],
        actor_email=test_db["admin_email"],
    )

    assert result["success"] is True

    with operations.SessionLocal() as db:
        log = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "update_shipment_status",
                AuditLog.entity_id == str(test_db["shipment_id"]),
            )
        )

        assert log is not None
        assert log.actor_user_id == test_db["admin_user_id"]
        assert log.actor_email == test_db["admin_email"]
        assert log.old_value == {"status": "pending"}
        assert log.new_value == {"status": "shipped"}


def test_admin_refund_status_update_creates_audit_log(test_db):
    with operations.SessionLocal() as db:
        returned = Return(
            order_id=test_db["order_id"],
            reason="Damaged product",
            status="approved",
            refund_status="pending",
        )

        db.add(returned)
        db.commit()
        return_id = returned.id

    result = operations.update_refund_status(
        return_id=return_id,
        new_refund_status="processing",
        actor_role="admin",
        actor_user_id=test_db["admin_user_id"],
        actor_email=test_db["admin_email"],
    )

    assert result["success"] is True

    with operations.SessionLocal() as db:
        log = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "update_refund_status",
                AuditLog.entity_id == str(return_id),
            )
        )

        assert log is not None
        assert log.actor_user_id == test_db["admin_user_id"]
        assert log.actor_email == test_db["admin_email"]
        assert log.old_value == {"refund_status": "pending"}
        assert log.new_value == {"refund_status": "processing"}


def test_admin_return_status_update_creates_audit_log(test_db):
    with operations.SessionLocal() as db:
        returned = Return(
            order_id=test_db["order_id"],
            reason="Damaged product",
            status="pending",
            refund_status="not_requested",
        )
        db.add(returned)
        db.commit()
        return_id = returned.id

    result = operations.update_return_status(
        return_id=return_id,
        new_status="approved",
        actor_role="admin",
        actor_user_id=test_db["admin_user_id"],
        actor_email=test_db["admin_email"],
    )

    assert result["success"] is True

    with operations.SessionLocal() as db:
        log = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "update_return_status",
                AuditLog.entity_id == str(return_id),
            )
        )

        assert log is not None
        assert log.actor_user_id == test_db["admin_user_id"]
        assert log.actor_email == test_db["admin_email"]
        assert log.actor_role == "admin"
        assert log.old_value == {"status": "pending"}
        assert log.new_value == {"status": "approved"}


def test_admin_create_return_creates_audit_log(test_db):
    # A return can only be created for a delivered order.
    with operations.SessionLocal() as db:
        order = db.get(Order, test_db["order_id"])
        order.status = "delivered"
        db.commit()

    result = operations.create_return(
        order_id=test_db["order_id"],
        reason="Damaged product",
        actor_role="admin",
        actor_user_id=test_db["admin_user_id"],
        actor_email=test_db["admin_email"],
    )

    assert result["success"] is True

    with operations.SessionLocal() as db:
        log = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "create_return",
                AuditLog.entity_id == str(result["return_id"]),
            )
        )

        assert log is not None
        assert log.actor_user_id == test_db["admin_user_id"]
        assert log.actor_email == test_db["admin_email"]
        assert log.actor_role == "admin"
        assert log.old_value is None
        assert log.new_value == {
            "order_id": test_db["order_id"],
            "reason": "Damaged product",
            "status": "pending",
            "refund_status": "not_requested",
        }
