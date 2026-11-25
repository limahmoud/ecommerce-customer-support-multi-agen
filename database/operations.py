from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from database.db import SessionLocal
from database.models import (
    Base,
    Customer,
    Order,
    Shipment,
    Return,
    User,
    AuditLog,
    Conversation,
)

import uuid


# =====================================================
# 1. CONFIGURATION
# =====================================================

ORDER_TRANSITIONS = {
    "pending": ["confirmed", "cancelled"],
    "confirmed": ["processing", "cancelled"],
    "processing": ["shipped", "cancelled"],
    "shipped": ["delivered"],
    "delivered": [],
    "cancelled": [],
}

SHIPMENT_TRANSITIONS = {
    "pending": ["shipped", "cancelled"],
    "shipped": ["in_transit", "delayed", "delivered"],
    "in_transit": ["delayed", "delivered"],
    "delayed": ["in_transit", "delivered"],
    "delivered": [],
    "cancelled": [],
}

RETURN_STATUSES = {
    "pending",
    "approved",
    "rejected",
    "received",
    "completed",
}

RETURN_TRANSITIONS = {
    "pending": ["approved", "rejected"],
    "approved": ["received"],
    "received": ["completed"],
    "rejected": [],
    "completed": [],
}

REFUND_TRANSITIONS = {
    "not_requested": ["pending"],
    "pending": ["processing", "rejected"],
    "processing": ["completed", "failed"],
    "failed": ["processing"],
    "rejected": [],
    "completed": [],
}

ORDER_UPDATE_ROLES = {
    "admin",
    "support_agent",
}

SHIPPING_UPDATE_ROLES = {
    "admin",
    "shipping_agent",
}

RETURN_CREATE_ROLES = {
    "admin",
    "support_agent",
    "returns_agent",
    "customer",
}

REFUND_UPDATE_ROLES = {
    "admin",
    "support_agent",
    "returns_agent",
}

RETURN_UPDATE_ROLES = {
    "admin",
    "returns_agent",
}


# =====================================================
# 2. HELPER FUNCTIONS
# =====================================================

def check_role(actor_role: str, allowed_roles: set):
    """Check whether the current actor has permission."""

    if actor_role not in allowed_roles:
        raise PermissionError(
            f"Role '{actor_role}' is not allowed to perform this operation."
        )


def get_order_for_update(db, order_id: int):
    """Get an order and lock its row during the transaction."""

    statement = (
        select(Order)
        .where(Order.id == order_id)
        .with_for_update()
    )

    order = db.scalar(statement)

    if not order:
        raise ValueError(f"Order {order_id} was not found.")

    return order


def authorize_customer_access(
    order,
    actor_role: str,
    customer_id: int | None = None,
):
    """
    If an operation is linked to a customer conversation,
    every actor must operate on that customer's orders.
    """

    if customer_id is None:
        if actor_role == "customer":
            raise PermissionError("Customer ID is required.")
        return

    if order.customer_id != customer_id:
        raise PermissionError(
            "You are not allowed to access this customer's order."
        )


def commit_safely(db):
    """Commit changes or rollback if an error occurs."""

    try:
        db.commit()

    except SQLAlchemyError:
        db.rollback()
        raise


# =====================================================
# 3. UPDATE ORDER STATUS
# =====================================================

def update_order_status(
    order_id: int,
    new_status: str,
    actor_role: str,
    customer_id: int | None = None,
    actor_user_id: int | None = None,
    actor_email: str | None = None,
):
    """Update an order status after checking permissions and transitions."""

    check_role(actor_role, ORDER_UPDATE_ROLES)

    new_status = new_status.strip().lower()

    if not new_status:
        raise ValueError("New order status cannot be empty.")

    db = SessionLocal()

    try:
        order = get_order_for_update(db, order_id)

        authorize_customer_access(
            order=order,
            actor_role=actor_role,
            customer_id=customer_id,
        )

        current_status = order.status.lower()

        allowed_next_statuses = ORDER_TRANSITIONS.get(
            current_status
        )

        if allowed_next_statuses is None:
            raise ValueError(
                f"Unknown current order status: {current_status}"
            )

        if new_status not in allowed_next_statuses:
            raise ValueError(
                f"Cannot change order status "
                f"from '{current_status}' to '{new_status}'."
            )

        order.status = new_status

        # Audit Admin changes in the same transaction.
        if (
            actor_role == "admin"
            and actor_user_id is not None
            and actor_email
        ):
            db.add(
                AuditLog(
                    actor_user_id=actor_user_id,
                    actor_email=actor_email,
                    actor_role=actor_role,
                    action="update_order_status",
                    entity_type="order",
                    entity_id=str(order.id),
                    old_value={"status": current_status},
                    new_value={"status": new_status},
                )
            )

        commit_safely(db)

        return {
            "success": True,
            "message": "Order status updated successfully.",
            "order_id": order.id,
            "old_status": current_status,
            "new_status": order.status,
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


# =====================================================
# 4. UPDATE SHIPMENT STATUS
# =====================================================

def update_shipment_status(
    shipment_id: int,
    new_status: str,
    actor_role: str,
    actor_user_id: int | None = None,
    actor_email: str | None = None,
):
    """Update shipment status after permission and transition validation."""

    check_role(actor_role, SHIPPING_UPDATE_ROLES)

    new_status = new_status.strip().lower()

    if not new_status:
        raise ValueError("New shipment status cannot be empty.")

    db = SessionLocal()

    try:
        statement = (
            select(Shipment)
            .where(Shipment.id == shipment_id)
            .with_for_update()
        )

        shipment = db.scalar(statement)

        if not shipment:
            raise ValueError(
                f"Shipment {shipment_id} was not found."
            )

        current_status = shipment.status.lower()

        allowed_next_statuses = SHIPMENT_TRANSITIONS.get(
            current_status
        )

        if allowed_next_statuses is None:
            raise ValueError(
                f"Unknown current shipment status: {current_status}"
            )

        if new_status not in allowed_next_statuses:
            raise ValueError(
                f"Cannot change shipment status "
                f"from '{current_status}' to '{new_status}'."
            )

        shipment.status = new_status

        # Audit Admin changes in the same transaction.
        if (
            actor_role == "admin"
            and actor_user_id is not None
            and actor_email
        ):
            db.add(
                AuditLog(
                    actor_user_id=actor_user_id,
                    actor_email=actor_email,
                    actor_role=actor_role,
                    action="update_shipment_status",
                    entity_type="shipment",
                    entity_id=str(shipment.id),
                    old_value={"status": current_status},
                    new_value={"status": new_status},
                )
            )

        commit_safely(db)

        return {
            "success": True,
            "message": "Shipment status updated successfully.",
            "shipment_id": shipment.id,
            "tracking_number": shipment.tracking_number,
            "old_status": current_status,
            "new_status": shipment.status,
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


# =====================================================
# 5. CREATE RETURN
# =====================================================

def create_return(
    order_id: int,
    reason: str,
    actor_role: str,
    customer_id: int | None = None,
    actor_user_id: int | None = None,
    actor_email: str | None = None,
):
    """Create a return request for a delivered order."""

    check_role(actor_role, RETURN_CREATE_ROLES)

    reason = reason.strip()

    if not reason:
        raise ValueError("Return reason cannot be empty.")

    db = SessionLocal()

    try:
        order = get_order_for_update(db, order_id)

        authorize_customer_access(
            order=order,
            actor_role=actor_role,
            customer_id=customer_id,
        )

        if order.status.strip().lower() != "delivered":
            raise ValueError(
                "A return can only be created for a delivered order."
            )

        returned = Return(
            order_id=order.id,
            reason=reason,
            status="pending",
            refund_status="not_requested",
        )

        db.add(returned)
        db.flush()

        # Audit Admin return creation in the same transaction.
        if (
            actor_role == "admin"
            and actor_user_id is not None
            and actor_email
        ):
            db.add(
                AuditLog(
                    actor_user_id=actor_user_id,
                    actor_email=actor_email,
                    actor_role=actor_role,
                    action="create_return",
                    entity_type="return",
                    entity_id=str(returned.id),
                    old_value=None,
                    new_value={
                        "order_id": order.id,
                        "reason": reason,
                        "status": "pending",
                        "refund_status": "not_requested",
                    },
                )
            )

        commit_safely(db)
        db.refresh(returned)

        return {
            "success": True,
            "message": "Return request created successfully.",
            "return_id": returned.id,
            "order_id": returned.order_id,
            "reason": returned.reason,
            "status": returned.status,
            "refund_status": returned.refund_status,
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def update_return_status(
    return_id: int,
    new_status: str,
    actor_role: str,
    customer_id: int | None = None,
    actor_user_id: int | None = None,
    actor_email: str | None = None,
):
    """Update return status after checking permissions and transitions."""

    check_role(actor_role, RETURN_UPDATE_ROLES)

    new_status = new_status.strip().lower()

    if new_status not in RETURN_STATUSES:
        raise ValueError(f"Invalid return status: {new_status}")

    db = SessionLocal()

    try:
        statement = (
            select(Return)
            .where(Return.id == return_id)
            .with_for_update()
        )

        returned = db.scalar(statement)

        if not returned:
            raise ValueError(f"Return {return_id} was not found.")

        order_statement = (
            select(Order)
            .where(Order.id == returned.order_id)
            .with_for_update()
        )

        order = db.scalar(order_statement)

        if not order:
            raise ValueError(
                f"Order {returned.order_id} was not found."
            )

        authorize_customer_access(
            order=order,
            actor_role=actor_role,
            customer_id=customer_id,
        )

        current_status = returned.status.strip().lower()

        allowed_next_statuses = RETURN_TRANSITIONS.get(
            current_status
        )

        if allowed_next_statuses is None:
            raise ValueError(
                f"Unknown current return status: {current_status}"
            )

        if new_status not in allowed_next_statuses:
            raise ValueError(
                f"Cannot change return status "
                f"from '{current_status}' to '{new_status}'."
            )

        returned.status = new_status

        # Audit Admin changes in the same transaction.
        if (
            actor_role == "admin"
            and actor_user_id is not None
            and actor_email
        ):
            db.add(
                AuditLog(
                    actor_user_id=actor_user_id,
                    actor_email=actor_email,
                    actor_role=actor_role,
                    action="update_return_status",
                    entity_type="return",
                    entity_id=str(returned.id),
                    old_value={"status": current_status},
                    new_value={"status": new_status},
                )
            )

        commit_safely(db)
        db.refresh(returned)

        return {
            "success": True,
            "message": "Return status updated successfully.",
            "return_id": returned.id,
            "order_id": returned.order_id,
            "old_status": current_status,
            "new_status": returned.status,
            "refund_status": returned.refund_status,
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


# =====================================================
def request_refund(
    return_id: int,
    customer_id: int,
):
    """Allow a customer to request a refund for their own approved return."""

    if customer_id is None:
        raise PermissionError("Customer authentication is required.")

    db = SessionLocal()

    try:
        statement = (
            select(Return)
            .where(Return.id == return_id)
            .with_for_update()
        )

        returned = db.scalar(statement)

        if not returned:
            raise ValueError(f"Return {return_id} was not found.")

        order_statement = (
            select(Order)
            .where(Order.id == returned.order_id)
            .with_for_update()
        )

        order = db.scalar(order_statement)

        if not order:
            raise ValueError(f"Order {returned.order_id} was not found.")

        authorize_customer_access(
            order=order,
            actor_role="customer",
            customer_id=customer_id,
        )

        if returned.status.strip().lower() not in {
            "approved",
            "received",
            "completed",
        }:
            raise ValueError(
                "Refund can only be requested after the return is approved."
            )

        current_status = returned.refund_status.strip().lower()

        if current_status == "pending":
            return {
                "success": True,
                "message": "Refund request is already pending approval.",
                "return_id": returned.id,
                "old_status": "pending",
                "new_status": "pending",
            }

        if current_status != "not_requested":
            raise ValueError(
                f"Cannot request a refund when its status is '{current_status}'."
            )

        returned.refund_status = "pending"

        commit_safely(db)

        return {
            "success": True,
            "message": "Refund request submitted and is pending approval.",
            "return_id": returned.id,
            "old_status": current_status,
            "new_status": returned.refund_status,
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


# 6. UPDATE REFUND STATUS
# =====================================================

def update_refund_status(
    return_id: int,
    new_refund_status: str,
    actor_role: str,
    customer_id: int | None = None,
    actor_user_id: int | None = None,
    actor_email: str | None = None,
):
    """Update refund status after checking permissions and business rules."""

    check_role(actor_role, REFUND_UPDATE_ROLES)

    new_refund_status = new_refund_status.strip().lower()

    if not new_refund_status:
        raise ValueError("New refund status cannot be empty.")

    db = SessionLocal()

    try:
        statement = (
            select(Return)
            .where(Return.id == return_id)
            .with_for_update()
        )

        returned = db.scalar(statement)

        if not returned:
            raise ValueError(
                f"Return {return_id} was not found."
            )

        order_statement = (
            select(Order)
            .where(Order.id == returned.order_id)
            .with_for_update()
        )

        order = db.scalar(order_statement)

        if not order:
            raise ValueError(
                f"Order {returned.order_id} was not found."
            )

        authorize_customer_access(
            order=order,
            actor_role=actor_role,
            customer_id=customer_id,
        )

        if returned.status.lower() not in {
            "approved",
            "received",
            "completed",
        }:
            raise ValueError(
                "Refund can only be processed after the return "
                "has been approved or received."
            )

        current_status = returned.refund_status.lower()

        allowed_next_statuses = REFUND_TRANSITIONS.get(
            current_status
        )

        if allowed_next_statuses is None:
            raise ValueError(
                f"Unknown current refund status: {current_status}"
            )

        if new_refund_status not in allowed_next_statuses:
            raise ValueError(
                f"Cannot change refund status "
                f"from '{current_status}' to '{new_refund_status}'."
            )

        returned.refund_status = new_refund_status

        # Audit Admin changes in the same transaction.
        if (
            actor_role == "admin"
            and actor_user_id is not None
            and actor_email
        ):
            db.add(
                AuditLog(
                    actor_user_id=actor_user_id,
                    actor_email=actor_email,
                    actor_role=actor_role,
                    action="update_refund_status",
                    entity_type="return",
                    entity_id=str(returned.id),
                    old_value={"refund_status": current_status},
                    new_value={"refund_status": new_refund_status},
                )
            )

        commit_safely(db)

        return {
            "success": True,
            "message": "Refund status updated successfully.",
            "return_id": returned.id,
            "old_status": current_status,
            "new_status": returned.refund_status,
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


# =====================================================
# 7. QUICK TEST
# =====================================================

if __name__ == "__main__":

    print("\n========== UPDATE ORDER STATUS ==========")

    try:
        result = update_order_status(
            order_id=1,
            new_status="confirmed",
            actor_role="admin",
        )
        print(result)

    except (ValueError, PermissionError) as error:
        print("Error:", error)

    print("\n========== UPDATE SHIPMENT STATUS ==========")

    try:
        result = update_shipment_status(
            shipment_id=1,
            new_status="in_transit",
            actor_role="shipping_agent",
        )
        print(result)

    except (ValueError, PermissionError) as error:
        print("Error:", error)

    print("\n========== CREATE RETURN ==========")

    try:
        result = create_return(
            order_id=1,
            reason="Product is damaged.",
            actor_role="admin",
        )
        print(result)

    except (ValueError, PermissionError) as error:
        print("Error:", error)

    print("\n========== UPDATE REFUND STATUS ==========")

    try:
        result = update_refund_status(
            return_id=1,
            new_refund_status="pending",
            actor_role="finance_agent",
        )
        print(result)

    except (ValueError, PermissionError) as error:
        print("Error:", error)


# =====================================================
# 8. CONVERSATION OPERATIONS
# =====================================================

def create_conversation(
    customer_id: int,
    title: str = "New Conversation",
):
    """Create a new conversation for a customer."""

    db = SessionLocal()

    try:
        conversation = Conversation(
            id=uuid.uuid4(),
            customer_id=customer_id,
            title=title,
        )

        db.add(conversation)
        db.commit()
        db.refresh(conversation)

        return {
            "id": str(conversation.id),
            "customer_id": conversation.customer_id,
            "title": conversation.title,
            "created_at": conversation.created_at.isoformat(),
            "last_opened_at": conversation.last_opened_at.isoformat(),
            "last_message_at": conversation.last_message_at.isoformat(),
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def get_customer_conversations(customer_id: int):
    """Get all conversations belonging to a customer."""

    db = SessionLocal()

    try:
        statement = (
            select(Conversation)
            .where(Conversation.customer_id == customer_id)
            .order_by(Conversation.last_opened_at.desc())
        )

        conversations = db.scalars(statement).all()

        return [
            {
                "id": str(conversation.id),
                "customer_id": conversation.customer_id,
                "title": conversation.title,
                "created_at": conversation.created_at.isoformat(),
                "last_opened_at": conversation.last_opened_at.isoformat(),
                "last_message_at": conversation.last_message_at.isoformat(),
            }
            for conversation in conversations
        ]

    finally:
        db.close()


def get_customer_conversation(
    conversation_id: str,
    customer_id: int,
):
    """Get one conversation only if it belongs to the customer."""

    db = SessionLocal()

    try:
        try:
            conversation_uuid = uuid.UUID(conversation_id)
        except (ValueError, TypeError, AttributeError):
            return None

        statement = select(Conversation).where(
            Conversation.id == conversation_uuid,
            Conversation.customer_id == customer_id,
        )

        conversation = db.scalar(statement)

        if not conversation:
            return None

        return {
            "id": str(conversation.id),
            "customer_id": conversation.customer_id,
            "title": conversation.title,
            "created_at": conversation.created_at.isoformat(),
            "last_opened_at": conversation.last_opened_at.isoformat(),
            "last_message_at": conversation.last_message_at.isoformat(),
        }

    finally:
        db.close()


def update_conversation_last_opened(
    conversation_id: str,
    customer_id: int,
):
    """Update last opened timestamp for an owned conversation."""

    db = SessionLocal()

    try:
        try:
            conversation_uuid = uuid.UUID(conversation_id)
        except (ValueError, TypeError, AttributeError):
            return False

        statement = select(Conversation).where(
            Conversation.id == conversation_uuid,
            Conversation.customer_id == customer_id,
        )

        conversation = db.scalar(statement)

        if not conversation:
            return False

        # Updated: timezone-aware UTC converted to naive UTC
        # to remain compatible with existing DateTime columns.
        conversation.last_opened_at = (
            datetime.now(timezone.utc).replace(tzinfo=None)
        )

        db.commit()

        return True

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def update_conversation_last_message(
    conversation_id: str,
    customer_id: int,
    title: str | None = None,
):
    """Update last message timestamp and optionally conversation title."""

    db = SessionLocal()

    try:
        try:
            conversation_uuid = uuid.UUID(conversation_id)
        except (ValueError, TypeError, AttributeError):
            return False

        statement = select(Conversation).where(
            Conversation.id == conversation_uuid,
            Conversation.customer_id == customer_id,
        )

        conversation = db.scalar(statement)

        if not conversation:
            return False

        # Updated: timezone-aware UTC converted to naive UTC
        # to remain compatible with existing DateTime columns.
        conversation.last_message_at = (
            datetime.now(timezone.utc).replace(tzinfo=None)
        )

        if title:
            conversation.title = title[:200]

        db.commit()

        return True

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()