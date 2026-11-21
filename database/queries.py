
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database.db import SessionLocal
from database.models import (
    Customer,
    Order,
    OrderItem,
    Shipment,
    Return,
    SupportTicket,
)


# ==========================================
# 1. CUSTOMER QUERIES
# ==========================================

def get_customer_by_id(customer_id: int):

    with SessionLocal() as db:

        customer = db.get(Customer, customer_id)

        if not customer:
            return None

        return {
            "id": customer.id,
            "name": customer.name,
            "email": customer.email,
            "phone": customer.phone,
        }


def get_customer_by_email(email: str):

    with SessionLocal() as db:

        statement = select(Customer).where(
            Customer.email == email
        )

        customer = db.scalar(statement)

        if not customer:
            return None

        return {
            "id": customer.id,
            "name": customer.name,
            "email": customer.email,
            "phone": customer.phone,
        }


# ==========================================
# 2. ORDER QUERIES
# ==========================================

def get_customer_orders(customer_id: int):

    with SessionLocal() as db:

        statement = (
            select(Order)
            .where(Order.customer_id == customer_id)
            .options(selectinload(Order.items))
            .order_by(Order.id)
        )

        orders = db.scalars(statement).all()

        result = []

        for order in orders:

            result.append({
                "order_id": order.id,
                "customer_id": order.customer_id,
                "order_date": order.order_date.isoformat(),
                "status": order.status,
                "total_amount": float(order.total_amount),

                "items": [
                    {
                        "id": item.id,
                        "product_name": item.product_name,
                        "quantity": item.quantity,
                        "unit_price": float(item.unit_price),
                    }
                    for item in order.items
                ]
            })

        return result


def get_order_details(order_id: int):

    with SessionLocal() as db:

        statement = (
            select(Order)
            .where(Order.id == order_id)
            .options(
                selectinload(Order.customer),
                selectinload(Order.items),
                selectinload(Order.shipments),
                selectinload(Order.returns),
            )
        )

        order = db.scalar(statement)

        if not order:
            return None

        return {
            "order_id": order.id,
            "status": order.status,
            "order_date": order.order_date.isoformat(),
            "total_amount": float(order.total_amount),

            "customer": {
                "id": order.customer.id,
                "name": order.customer.name,
                "email": order.customer.email,
            },

            "items": [
                {
                    "product_name": item.product_name,
                    "quantity": item.quantity,
                    "unit_price": float(item.unit_price),
                }
                for item in order.items
            ],

            "shipments": [
                {
                    "tracking_number": shipment.tracking_number,
                    "carrier": shipment.carrier,
                    "status": shipment.status,
                    "estimated_delivery": (
                        shipment.estimated_delivery.isoformat()
                        if shipment.estimated_delivery else None
                    ),
                }
                for shipment in order.shipments
            ],

            "returns": [
                {
                    "return_id": returned.id,
                    "reason": returned.reason,
                    "status": returned.status,
                    "refund_status": returned.refund_status,
                }
                for returned in order.returns
            ],
        }


# ==========================================
# 3. ORDER ITEM QUERIES
# ==========================================

def get_order_items(order_id: int):

    with SessionLocal() as db:

        statement = select(OrderItem).where(
            OrderItem.order_id == order_id
        )

        items = db.scalars(statement).all()

        return [
            {
                "id": item.id,
                "product_name": item.product_name,
                "quantity": item.quantity,
                "unit_price": float(item.unit_price),
                "subtotal": float(item.unit_price * item.quantity),
            }
            for item in items
        ]


# ==========================================
# 4. SHIPPING QUERIES
# ==========================================

def get_order_shipments(order_id: int):

    with SessionLocal() as db:

        statement = (
            select(Shipment)
            .where(Shipment.order_id == order_id)
            .order_by(Shipment.id)
        )

        shipments = db.scalars(statement).all()

        return [
            {
                "shipment_id": shipment.id,
                "order_id": shipment.order_id,
                "tracking_number": shipment.tracking_number,
                "carrier": shipment.carrier,
                "status": shipment.status,
                "estimated_delivery": (
                    shipment.estimated_delivery.isoformat()
                    if shipment.estimated_delivery else None
                ),
            }
            for shipment in shipments
        ]


def get_shipment_by_tracking_number(tracking_number: str):

    with SessionLocal() as db:

        statement = (
            select(Shipment)
            .where(Shipment.tracking_number == tracking_number)
        )

        shipment = db.scalar(statement)

        if not shipment:
            return None

        return {
            "shipment_id": shipment.id,
            "order_id": shipment.order_id,
            "tracking_number": shipment.tracking_number,
            "carrier": shipment.carrier,
            "status": shipment.status,
            "estimated_delivery": (
                shipment.estimated_delivery.isoformat()
                if shipment.estimated_delivery else None
            ),
        }


# ==========================================
# 5. RETURNS QUERIES
# ==========================================

def get_order_returns(order_id: int):

    with SessionLocal() as db:

        statement = (
            select(Return)
            .where(Return.order_id == order_id)
            .order_by(Return.id)
        )

        returns = db.scalars(statement).all()

        return [
            {
                "return_id": returned.id,
                "order_id": returned.order_id,
                "reason": returned.reason,
                "status": returned.status,
                "refund_status": returned.refund_status,
                "created_at": returned.created_at.isoformat(),
            }
            for returned in returns
        ]


def get_return_by_id(return_id: int):

    with SessionLocal() as db:

        returned = db.get(Return, return_id)

        if not returned:
            return None

        return {
            "return_id": returned.id,
            "order_id": returned.order_id,
            "reason": returned.reason,
            "status": returned.status,
            "refund_status": returned.refund_status,
            "created_at": returned.created_at.isoformat(),
        }


# ==========================================
# 6. SUPPORT TICKET QUERIES
# ==========================================

def get_customer_tickets(customer_id: int):

    with SessionLocal() as db:

        statement = (
            select(SupportTicket)
            .where(SupportTicket.customer_id == customer_id)
            .order_by(SupportTicket.id)
        )

        tickets = db.scalars(statement).all()

        return [
            {
                "ticket_id": ticket.id,
                "customer_id": ticket.customer_id,
                "order_id": ticket.order_id,
                "subject": ticket.subject,
                "description": ticket.description,
                "status": ticket.status,
                "created_at": ticket.created_at.isoformat(),
            }
            for ticket in tickets
        ]


# ==========================================
# 7. TESTING
# ==========================================

if __name__ == "__main__":

    print("\n========== CUSTOMER ==========")
    print(get_customer_by_id(1))

    print("\n========== CUSTOMER ORDERS ==========")
    print(get_customer_orders(1))

    print("\n========== ORDER DETAILS ==========")
    print(get_order_details(1))

    print("\n========== ORDER ITEMS ==========")
    print(get_order_items(1))

    print("\n========== ORDER SHIPMENTS ==========")
    print(get_order_shipments(1))

    print("\n========== SHIPMENT TRACKING ==========")
    print(get_shipment_by_tracking_number("TRK-SEED-1001"))

    print("\n========== ORDER RETURNS ==========")
    print(get_order_returns(1))

    print("\n========== RETURN DETAILS ==========")
    print(get_return_by_id(1))

    print("\n========== CUSTOMER TICKETS ==========")
    print(get_customer_tickets(1))
