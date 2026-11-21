
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    String,
    DateTime,
    ForeignKey,
    Numeric,
    Integer,
    Text
)

from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship
)


# =====================================
# BASE
# =====================================

class Base(DeclarativeBase):
    pass


# =====================================
# 1. CUSTOMERS
# =====================================

class Customer(Base):

    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(100))

    email: Mapped[str] = mapped_column(
        String(150),
        unique=True,
        index=True
    )

    phone: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    orders: Mapped[list["Order"]] = relationship(
        back_populates="customer"
    )

    support_tickets: Mapped[list["SupportTicket"]] = relationship(
        back_populates="customer"
    )


# =====================================
# 2. ORDERS
# =====================================

class Order(Base):

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id")
    )

    order_date: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default="pending"
    )

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2)
    )

    customer: Mapped["Customer"] = relationship(
        back_populates="orders"
    )

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan"
    )

    shipments: Mapped[list["Shipment"]] = relationship(
    back_populates="order"
    )

    returns: Mapped[list["Return"]] = relationship(
        back_populates="order"
    )

    support_tickets: Mapped[list["SupportTicket"]] = relationship(
        back_populates="order"
    )


# =====================================
# 3. ORDER ITEMS
# =====================================

class OrderItem(Base):

    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id")
    )

    product_name: Mapped[str] = mapped_column(
        String(150)
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        default=1
    )

    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2)
    )

    order: Mapped["Order"] = relationship(
        back_populates="items"
    )


# =====================================
# 4. SHIPMENTS
# =====================================

class Shipment(Base):

    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(primary_key=True)

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id"),
        unique=True
    )

    tracking_number: Mapped[str] = mapped_column(
        String(100)
    )

    carrier: Mapped[str] = mapped_column(
        String(100)
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default="preparing"
    )

    estimated_delivery: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )

    order: Mapped["Order"] = relationship(
        back_populates="shipments"
    )


# =====================================
# 5. RETURNS
# =====================================

class Return(Base):

    __tablename__ = "returns"

    id: Mapped[int] = mapped_column(primary_key=True)

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id")
    )

    reason: Mapped[str] = mapped_column(
        Text
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default="requested"
    )

    refund_status: Mapped[str] = mapped_column(
        String(50),
        default="pending"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    order: Mapped["Order"] = relationship(
        back_populates="returns"
    )


# =====================================
# 6. SUPPORT TICKETS
# =====================================

class SupportTicket(Base):

    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(primary_key=True)

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id")
    )

    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id"),
        nullable=True
    )

    subject: Mapped[str] = mapped_column(
        String(200)
    )

    description: Mapped[str] = mapped_column(
        Text
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default="open"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    customer: Mapped["Customer"] = relationship(
        back_populates="support_tickets"
    )

    order: Mapped["Order | None"] = relationship(
        back_populates="support_tickets"
    )
