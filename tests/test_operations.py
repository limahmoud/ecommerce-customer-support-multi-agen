
import pytest

from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.models import Base, Customer, Order, Shipment, Return
from database import operations


import uuid

from langchain_core.messages import AIMessage
from langgraph.graph import StateGraph, START, END, MessagesState
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
        db.commit()

        data = {
            "customer_id": customer.id,
            "order_id": order.id,
            "shipment_id": shipment.id,
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
            actor_role="finance_agent",
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
        actor_role="finance_agent",
    )

    assert result["success"] is True
    assert result["old_status"] == "not_requested"
    assert result["new_status"] == "pending"


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
        )

    with operations.SessionLocal() as db:
        returned = db.get(Return, return_id)

        assert returned.refund_status == "pending"

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
        )

    with operations.SessionLocal() as db:
        returned = db.get(Return, return_id)

        assert returned.refund_status == "not_requested"

    assert "rejected" in response.lower()


def build_approval_test_graph(checkpointer):
    builder = StateGraph(MessagesState)

    builder.add_node(
        "tools",
        ToolNode([request_sensitive_action]),
    )

    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)

    return builder.compile(checkpointer=checkpointer)


def run_approval_test(checkpointer, action_args, approved):
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
            ]
        },
        config=config,
    )

    interrupts = result.get("__interrupt__", [])

    assert interrupts, "Expected an approval interrupt"

    # Resume after the human decision.
    resumed_result = graph.invoke(
        Command(
            resume={
                "approved": approved,
                "reason": "Test approval decision",
            }
        ),
        config=config,
    )

    assert not resumed_result.get("__interrupt__", [])

    return resumed_result["messages"][-1].content