from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from database.db import SessionLocal
from database.models import (
    Customer,
    Order,
    OrderItem,
    Shipment,
    Return,
    SupportTicket,
)


def seed_database():

    with SessionLocal() as db:

        # Prevent inserting the same seed data twice
        existing_customer = db.scalar(
            select(Customer).where(
                Customer.email == "ahmed.seed@example.com"
            )
        )

        if existing_customer:
            print("Seed data already exists!")
            return

        try:
            # 1. Customers
            customer1 = Customer(
                name="Ahmed Mohamed",
                email="ahmed.seed@example.com",
                phone="01011111111",
            )

            customer2 = Customer(
                name="Omar Ali",
                email="omar.seed@example.com",
                phone="01022222222",
            )

            customer3 = Customer(
                name="Sara Hassan",
                email="sara.seed@example.com",
                phone="01033333333",
            )

            db.add_all([customer1, customer2, customer3])
            db.flush()

            # 2. Orders
            order1 = Order(
                customer=customer1,
                status="shipped",
                total_amount=Decimal("3000.00"),
            )

            order2 = Order(
                customer=customer2,
                status="pending",
                total_amount=Decimal("1500.00"),
            )

            order3 = Order(
                customer=customer3,
                status="delivered",
                total_amount=Decimal("2200.00"),
            )

            db.add_all([order1, order2, order3])
            db.flush()

            # 3. Order Items
            items = [
                OrderItem(
                    order=order1,
                    product_name="Laptop",
                    quantity=1,
                    unit_price=Decimal("2500.00"),
                ),
                OrderItem(
                    order=order1,
                    product_name="Mouse",
                    quantity=2,
                    unit_price=Decimal("250.00"),
                ),
                OrderItem(
                    order=order2,
                    product_name="Keyboard",
                    quantity=1,
                    unit_price=Decimal("1500.00"),
                ),
                OrderItem(
                    order=order3,
                    product_name="Headphones",
                    quantity=2,
                    unit_price=Decimal("1100.00"),
                ),
            ]

            # 4. Shipments
            shipments = [
                Shipment(
                    order=order1,
                    tracking_number="TRK-SEED-1001",
                    carrier="Aramex",
                    status="in_transit",
                    estimated_delivery=(
                        datetime.now(timezone.utc).replace(tzinfo=None)
                        + timedelta(days=2)
                    ),
                ),
                Shipment(
                    order=order1,
                    tracking_number="TRK-SEED-1002",
                    carrier="DHL",
                    status="preparing",
                    estimated_delivery=(
                        datetime.now(timezone.utc).replace(tzinfo=None)
                        + timedelta(days=3)
                    ),
                ),
                Shipment(
                    order=order3,
                    tracking_number="TRK-SEED-1003",
                    carrier="FedEx",
                    status="delivered",
                    estimated_delivery=(
                        datetime.now(timezone.utc).replace(tzinfo=None)
                    ),
                ),
            ]

            # 5. Returns
            return1 = Return(
                order=order3,
                reason="Product arrived damaged",
                status="approved",
                refund_status="pending",
            )

            # 6. Support Tickets
            ticket1 = SupportTicket(
                customer=customer1,
                order=order1,
                subject="Where is my second shipment?",
                description="I received the first shipment but not the second.",
                status="open",
            )

            ticket2 = SupportTicket(
                customer=customer2,
                order=order2,
                subject="Order confirmation",
                description="I want to confirm my order.",
                status="open",
            )

            db.add_all(
                items
                + shipments
                + [return1, ticket1, ticket2]
            )

            db.commit()

            print("Seed data inserted successfully!")

        except Exception as error:
            db.rollback()
            print("Error inserting seed data:", error)


if __name__ == "__main__":
    seed_database()
