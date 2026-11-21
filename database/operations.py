
# from datetime import datetime, timezone

# from sqlalchemy import select
# from sqlalchemy.exc import SQLAlchemyError

# from database.db import SessionLocal
# from database.models import Order, Shipment, Return


# # =====================================================
# # 1. CONFIGURATION
# # =====================================================

# # الحالات المسموح بها للطلبات
# ORDER_TRANSITIONS = {
#     "pending": ["confirmed", "cancelled"],
#     "confirmed": ["processing", "cancelled"],
#     "processing": ["shipped", "cancelled"],
#     "shipped": ["delivered"],
#     "delivered": [],
#     "cancelled": [],
# }

# # الحالات المسموح بها للشحنات
# SHIPMENT_TRANSITIONS = {
#     "pending": ["shipped", "cancelled"],
#     "shipped": ["in_transit", "delayed", "delivered"],
#     "in_transit": ["delayed", "delivered"],
#     "delayed": ["in_transit", "delivered"],
#     "delivered": [],
#     "cancelled": [],
# }

# # الحالات المسموح بها للمرتجعات
# RETURN_STATUSES = {
#     "pending",
#     "approved",
#     "rejected",
#     "received",
#     "completed",
# }

# # انتقالات حالة استرداد الأموال
# REFUND_TRANSITIONS = {
#     "not_requested": ["pending"],
#     "pending": ["processing", "rejected"],
#     "processing": ["completed", "failed"],
#     "failed": ["processing"],
#     "rejected": [],
#     "completed": [],
# }

# # الأدوار المسموح لها بتغيير حالات الطلبات
# ORDER_UPDATE_ROLES = {
#     "admin",
#     "support_agent",
#     "order_agent",
# }

# # الأدوار المسموح لها بتحديث الشحنات
# SHIPPING_UPDATE_ROLES = {
#     "admin",
#     "shipping_agent",
# }

# # الأدوار المسموح لها بإنشاء المرتجعات
# RETURN_CREATE_ROLES = {
#     "admin",
#     "support_agent",
#     "returns_agent",
#     "customer",
# }

# # الأدوار المسموح لها بتحديث Refund
# REFUND_UPDATE_ROLES = {
#     "admin",
#     "support_agent",
#     "returns_agent",
#     "finance_agent",
# }


# # =====================================================
# # 2. HELPER FUNCTIONS
# # =====================================================

# def check_role(actor_role: str, allowed_roles: set):
#     """
#     Check whether the current actor has permission.
#     """

#     if actor_role not in allowed_roles:
#         raise PermissionError(
#             f"Role '{actor_role}' is not allowed to perform this operation."
#         )


# def get_order_for_update(db, order_id: int):
#     """
#     Get an order and lock its row during the transaction.
#     """

#     statement = (
#         select(Order)
#         .where(Order.id == order_id)
#         .with_for_update()
#     )

#     order = db.scalar(statement)

#     if not order:
#         raise ValueError(f"Order {order_id} was not found.")

#     return order


# def authorize_customer_access(
#     order,
#     actor_role: str,
#     customer_id: int | None = None,
# ):
#     """
#     Staff roles can access orders.
#     Customers can access only their own orders.
#     """

#     if actor_role == "customer":
#         if customer_id is None:
#             raise PermissionError(
#                 "Customer ID is required."
#             )

#         if order.customer_id != customer_id:
#             raise PermissionError(
#                 "You are not allowed to access this order."
#             )


# def commit_safely(db):
#     """
#     Commit changes or rollback if an error occurs.
#     """

#     try:
#         db.commit()

#     except SQLAlchemyError:
#         db.rollback()
#         raise


# # =====================================================
# # 3. UPDATE ORDER STATUS
# # =====================================================

# def update_order_status(
#     order_id: int,
#     new_status: str,
#     actor_role: str,
# ):
#     """
#     Update an order status after checking permissions
#     and allowed status transitions.
#     """

#     check_role(actor_role, ORDER_UPDATE_ROLES)

#     new_status = new_status.strip().lower()

#     if not new_status:
#         raise ValueError("New order status cannot be empty.")

#     db = SessionLocal()

#     try:
#         order = get_order_for_update(db, order_id)

#         current_status = order.status.lower()

#         allowed_next_statuses = ORDER_TRANSITIONS.get(
#             current_status
#         )

#         if allowed_next_status is None:
#             raise ValueError(
#                 f"Unknown current order status: {current_status}"
#             )

#         if new_status not in allowed_next_statuses:
#             raise ValueError(
#                 f"Cannot change order status "
#                 f"from '{current_status}' to '{new_status}'."
#             )

#         order.status = new_status

#         commit_safely(db)

#         return {
#             "success": True,
#             "message": "Order status updated successfully.",
#             "order_id": order.id,
#             "old_status": current_status,
#             "new_status": order.status,
#         }

#     except Exception:
#         db.rollback()
#         raise

#     finally:
#         db.close()


# # =====================================================
# # 4. UPDATE SHIPMENT STATUS
# # =====================================================

# def update_shipment_status(
#     shipment_id: int,
#     new_status: str,
#     actor_role: str,
# ):
#     """
#     Update shipment status after permission and
#     transition validation.
#     """

#     check_role(actor_role, SHIPPING_UPDATE_ROLES)

#     new_status = new_status.strip().lower()

#     if not new_status:
#         raise ValueError("New shipment status cannot be empty.")

#     db = SessionLocal()

#     try:
#         statement = (
#             select(Shipment)
#             .where(Shipment.id == shipment_id)
#             .with_for_update()
#         )

#         shipment = db.scalar(statement)

#         if not shipment:
#             raise ValueError(
#                 f"Shipment {shipment_id} was not found."
#             )

#         current_status = shipment.status.lower()

#         allowed_next_statuses = SHIPMENT_TRANSITIONS.get(
#             current_status
#         )

#         if allowed_next_statuses is None:
#             raise ValueError(
#                 f"Unknown current shipment status: {current_status}"
#             )

#         if new_status not in allowed_next_statuses:
#             raise ValueError(
#                 f"Cannot change shipment status "
#                 f"from '{current_status}' to '{new_status}'."
#             )

#         shipment.status = new_status

#         commit_safely(db)

#         return {
#             "success": True,
#             "message": "Shipment status updated successfully.",
#             "shipment_id": shipment.id,
#             "tracking_number": shipment.tracking_number,
#             "old_status": current_status,
#             "new_status": shipment.status,
#         }

#     except Exception:
#         db.rollback()
#         raise

#     finally:
#         db.close()


# # =====================================================
# # 5. CREATE RETURN
# # =====================================================

# def create_return(
#     order_id: int,
#     reason: str,
#     actor_role: str,
#     customer_id: int | None = None,
# ):
#     """
#     Create a return request for a delivered order.

#     Customers can create returns only for their own orders.
#     Staff roles can create returns according to their permissions.
#     """

#     check_role(actor_role, RETURN_CREATE_ROLES)

#     reason = reason.strip()

#     if not reason:
#         raise ValueError("Return reason cannot be empty.")

#     db = SessionLocal()

#     try:
#         order = get_order_for_update(db, order_id)

#         authorize_customer_access(
#             order=order,
#             actor_role=actor_role,
#             customer_id=customer_id,
#         )

#         if order.status.lower() != "delivered":
#             raise ValueError(
#                 "A return can only be created for a delivered order."
#             )

#         returned = Return(
#             order_id=order.id,
#             reason=reason,
#             status="pending",
#             refund_status="not_requested",
#         )

#         db.add(returned)

#         commit_safely(db)
#         db.refresh(returned)

#         return {
#             "success": True,
#             "message": "Return request created successfully.",
#             "return_id": returned.id,
#             "order_id": returned.order_id,
#             "reason": returned.reason,
#             "status": returned.status,
#             "refund_status": returned.refund_status,
#         }

#     except Exception:
#         db.rollback()
#         raise

#     finally:
#         db.close()


# # =====================================================
# # 6. UPDATE REFUND STATUS
# # =====================================================

# def update_refund_status(
#     return_id: int,
#     new_refund_status: str,
#     actor_role: str,
# ):
#     """
#     Update refund status after checking permissions
#     and business rules.
#     """

#     check_role(actor_role, REFUND_UPDATE_ROLES)

#     new_refund_status = new_refund_status.strip().lower()

#     if not new_refund_status:
#         raise ValueError("New refund status cannot be empty.")

#     db = SessionLocal()

#     try:
#         statement = (
#             select(Return)
#             .where(Return.id == return_id)
#             .with_for_update()
#         )

#         returned = db.scalar(statement)

#         if not returned:
#             raise ValueError(
#                 f"Return {return_id} was not found."
#             )

#         if returned.status.lower() not in {
#             "approved",
#             "received",
#             "completed",
#         }:
#             raise ValueError(
#                 "Refund can only be processed after the return "
#                 "has been approved or received."
#             )

#         current_status = returned.refund_status.lower()

#         allowed_next_statuses = REFUND_TRANSITIONS.get(
#             current_status
#         )

#         if allowed_next_statuses is None:
#             raise ValueError(
#                 f"Unknown current refund status: {current_status}"
#             )

#         if new_refund_status not in allowed_next_statuses:
#             raise ValueError(
#                 f"Cannot change refund status "
#                 f"from '{current_status}' to '{new_refund_status}'."
#             )

#         returned.refund_status = new_refund_status

#         commit_safely(db)

#         return {
#             "success": True,
#             "message": "Refund status updated successfully.",
#             "return_id": returned.id,
#             "old_status": current_status,
#             "new_status": returned.refund_status,
#         }

#     except Exception:
#         db.rollback()
#         raise

#     finally:
#         db.close()


# # =====================================================
# # 7. QUICK TEST
# # =====================================================

# if __name__ == "__main__":

#     print("\n========== UPDATE ORDER STATUS ==========")

#     try:
#         result = update_order_status(
#             order_id=1,
#             new_status="confirmed",
#             actor_role="admin",
#         )
#         print(result)

#     except (ValueError, PermissionError) as error:
#         print("Error:", error)

#     print("\n========== UPDATE SHIPMENT STATUS ==========")

#     try:
#         result = update_shipment_status(
#             shipment_id=1,
#             new_status="in_transit",
#             actor_role="shipping_agent",
#         )
#         print(result)

#     except (ValueError, PermissionError) as error:
#         print("Error:", error)

#     print("\n========== CREATE RETURN ==========")

#     try:
#         result = create_return(
#             order_id=1,
#             reason="Product is damaged.",
#             actor_role="admin",
#         )
#         print(result)

#     except (ValueError, PermissionError) as error:
#         print("Error:", error)

#     print("\n========== UPDATE REFUND STATUS ==========")

#     try:
#         result = update_refund_status(
#             return_id=1,
#             new_refund_status="pending",
#             actor_role="finance_agent",
#         )
#         print(result)

#     except (ValueError, PermissionError) as error:
#         print("Error:", error)
