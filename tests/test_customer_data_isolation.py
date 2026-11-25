
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.models import (
    Base,
    Customer,
    Order,
    OrderItem,
    Shipment,
    Return,
    Conversation,
)

from database import queries, operations


@pytest.fixture
def isolation_db(monkeypatch):
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

    monkeypatch.setattr(
        queries,
        "SessionLocal",
        TestingSessionLocal,
    )

    monkeypatch.setattr(
        operations,
        "SessionLocal",
        TestingSessionLocal,
    )

    with TestingSessionLocal() as db:

        # 1. Customers
        customer1 = Customer(
            name="Customer One",
            email="customer1@test.com",
        )

        customer2 = Customer(
            name="Customer Two",
            email="customer2@test.com",
        )

        db.add_all([customer1, customer2])
        db.flush()

        # 2. Conversations
        conversation1 = Conversation(
            customer_id=customer1.id,
            title="Customer One Conversation",
        )

        conversation2 = Conversation(
            customer_id=customer2.id,
            title="Customer Two Conversation",
        )

        db.add_all([conversation1, conversation2])
        db.flush()

        # 3. Orders
        order1 = Order(
            customer_id=customer1.id,
            total_amount=Decimal("200.00"),
            status="pending",
        )

        order2 = Order(
            customer_id=customer2.id,
            total_amount=Decimal("200.00"),
            status="shipped",
        )

        db.add_all([order1, order2])
        db.flush()

        # 4. Order Items
        item1 = OrderItem(
            order_id=order1.id,
            product_name="Customer One Product",
            quantity=2,
            unit_price=Decimal("100.00"),
        )

        item2 = OrderItem(
            order_id=order2.id,
            product_name="Customer Two Product",
            quantity=1,
            unit_price=Decimal("200.00"),
        )

        # 5. Shipments
        shipment1 = Shipment(
            order_id=order1.id,
            tracking_number="TRACK-CUSTOMER-1",
            carrier="DHL",
            status="preparing",
        )

        shipment2 = Shipment(
            order_id=order2.id,
            tracking_number="TRACK-CUSTOMER-2",
            carrier="FedEx",
            status="shipped",
        )

        # 6. Returns
        return1 = Return(
            order_id=order1.id,
            reason="Damaged product",
        )

        return2 = Return(
            order_id=order2.id,
            reason="Wrong product",
        )

        db.add_all([
            item1,
            item2,
            shipment1,
            shipment2,
            return1,
            return2,
        ])

        db.commit()

        data = {
            "customer1_id": customer1.id,
            "customer2_id": customer2.id,

            "conversation1_id": str(conversation1.id),
            "conversation2_id": str(conversation2.id),

            "order1_id": order1.id,
            "order2_id": order2.id,

            "item1_id": item1.id,
            "item2_id": item2.id,

            "shipment1_id": shipment1.id,
            "shipment2_id": shipment2.id,

            "shipment1_tracking": shipment1.tracking_number,
            "shipment2_tracking": shipment2.tracking_number,

            "return1_id": return1.id,
            "return2_id": return2.id,
        }

    yield data

    Base.metadata.drop_all(engine)
    engine.dispose()


# ============================================================
# CUSTOMER ORDERS ISOLATION
# ============================================================

def test_customer_can_get_own_orders(isolation_db):
    result = queries.get_customer_orders(
        isolation_db["customer1_id"]
    )

    assert len(result) == 1
    assert result[0]["customer_id"] == isolation_db["customer1_id"]


def test_customer_cannot_get_other_customer_orders(isolation_db):
    result = queries.get_customer_orders(
        isolation_db["customer1_id"]
    )

    order_ids = [order["order_id"] for order in result]

    assert isolation_db["order2_id"] not in order_ids


def test_customer_gets_empty_orders_when_no_orders(isolation_db):
    result = queries.get_customer_orders(99999)

    assert result == []


def test_customer_can_get_own_order_details(isolation_db):
    result = queries.get_order_details(
        isolation_db["order1_id"],
        isolation_db["customer1_id"],
    )

    assert result is not None
    assert result["customer_id"] == isolation_db["customer1_id"]


def test_customer_cannot_get_other_customer_order_details(isolation_db):
    result = queries.get_order_details(
        isolation_db["order2_id"],
        isolation_db["customer1_id"],
    )

    assert result is None


# ============================================================
# ORDER ITEMS ISOLATION
# ============================================================

def test_customer_can_get_own_order_items(isolation_db):
    result = queries.get_order_items(
        isolation_db["order1_id"],
        isolation_db["customer1_id"],
    )

    assert len(result) == 1
    assert result[0]["product_name"] == "Customer One Product"


def test_customer_cannot_get_other_customer_order_items(isolation_db):
    result = queries.get_order_items(
        isolation_db["order2_id"],
        isolation_db["customer1_id"],
    )

    assert result == []


# ============================================================
# SHIPMENTS ISOLATION
# ============================================================

def test_customer_can_get_own_shipments(isolation_db):
    result = queries.get_order_shipments(
        isolation_db["order1_id"],
        isolation_db["customer1_id"],
    )

    assert len(result) == 1
    assert result[0]["tracking_number"] == "TRACK-CUSTOMER-1"


def test_customer_cannot_get_other_customer_shipments(isolation_db):
    result = queries.get_order_shipments(
        isolation_db["order2_id"],
        isolation_db["customer1_id"],
    )

    assert result == []


def test_customer_can_track_own_shipment(isolation_db):
    result = queries.get_shipment_by_tracking_number(
        isolation_db["shipment1_tracking"],
        isolation_db["customer1_id"],
    )

    assert result is not None
    assert result["shipment_id"] == isolation_db["shipment1_id"]


def test_customer_cannot_track_other_customer_shipment(isolation_db):
    result = queries.get_shipment_by_tracking_number(
        isolation_db["shipment2_tracking"],
        isolation_db["customer1_id"],
    )

    assert result is None


# ============================================================
# RETURNS ISOLATION
# ============================================================

def test_customer_can_get_own_returns(isolation_db):
    result = queries.get_order_returns(
        isolation_db["order1_id"],
        isolation_db["customer1_id"],
    )

    assert len(result) == 1
    assert result[0]["reason"] == "Damaged product"


def test_customer_cannot_get_other_customer_returns(isolation_db):
    result = queries.get_order_returns(
        isolation_db["order2_id"],
        isolation_db["customer1_id"],
    )

    assert result == []


def test_customer_can_get_own_return_details(isolation_db):
    result = queries.get_return_by_id(
        isolation_db["return1_id"],
        isolation_db["customer1_id"],
    )

    assert result is not None
    assert result["return_id"] == isolation_db["return1_id"]


def test_customer_cannot_get_other_customer_return_details(isolation_db):
    result = queries.get_return_by_id(
        isolation_db["return2_id"],
        isolation_db["customer1_id"],
    )

    assert result is None


# ============================================================
# CONVERSATIONS ISOLATION
# ============================================================

def test_customer_can_get_own_conversation(isolation_db):
    result = operations.get_customer_conversation(
        isolation_db["conversation1_id"],
        isolation_db["customer1_id"],
    )

    assert result is not None
    assert result["customer_id"] == isolation_db["customer1_id"]


def test_customer_cannot_get_other_customer_conversation(isolation_db):
    result = operations.get_customer_conversation(
        isolation_db["conversation2_id"],
        isolation_db["customer1_id"],
    )

    assert result is None


def test_customer_cannot_update_other_customer_conversation(isolation_db):
    result = operations.update_conversation_last_message(
        isolation_db["conversation2_id"],
        isolation_db["customer1_id"],
    )

    assert result is False


def test_customer_cannot_open_other_customer_conversation(isolation_db):
    result = operations.update_conversation_last_opened(
        isolation_db["conversation2_id"],
        isolation_db["customer1_id"],
    )

    assert result is False


def test_customer_can_update_own_conversation(isolation_db):
    result = operations.update_conversation_last_message(
        isolation_db["conversation1_id"],
        isolation_db["customer1_id"],
    )

    assert result is True


def test_customer_can_open_own_conversation(isolation_db):
    result = operations.update_conversation_last_opened(
        isolation_db["conversation1_id"],
        isolation_db["customer1_id"],
    )

    assert result is True


def test_invalid_conversation_id_is_rejected(isolation_db):
    result = operations.get_customer_conversation(
        "invalid-uuid",
        isolation_db["customer1_id"],
    )

    assert result is None



# ============================================================
# ADDITIONAL CUSTOMER DATA ISOLATION TESTS
# ============================================================

def test_customer_orders_contain_only_own_data(isolation_db):
    result = queries.get_customer_orders(
        isolation_db["customer1_id"]
    )

    assert result

    for order in result:
        assert order["customer_id"] == isolation_db["customer1_id"]

    assert all(
        order["order_id"] != isolation_db["order2_id"]
        for order in result
    )


def test_order_items_query_does_not_leak_other_customer_data(
    isolation_db,
):
    result = queries.get_order_items(
        isolation_db["order2_id"],
        isolation_db["customer1_id"],
    )

    assert result == []


def test_shipments_query_does_not_leak_other_customer_data(
    isolation_db,
):
    result = queries.get_order_shipments(
        isolation_db["order2_id"],
        isolation_db["customer1_id"],
    )

    assert result == []


def test_returns_query_does_not_leak_other_customer_data(
    isolation_db,
):
    result = queries.get_order_returns(
        isolation_db["order2_id"],
        isolation_db["customer1_id"],
    )

    assert result == []


def test_customer_cannot_access_nonexistent_conversation(
    isolation_db,
):
    result = operations.get_customer_conversation(
        "11111111-1111-1111-1111-111111111111",
        isolation_db["customer1_id"],
    )

    assert result is None


def test_customer_cannot_update_nonexistent_conversation(
    isolation_db,
):
    result = operations.update_conversation_last_message(
        "11111111-1111-1111-1111-111111111111",
        isolation_db["customer1_id"],
    )

    assert result is False


def test_customer_cannot_open_nonexistent_conversation(
    isolation_db,
):
    result = operations.update_conversation_last_opened(
        "11111111-1111-1111-1111-111111111111",
        isolation_db["customer1_id"],
    )

    assert result is False
