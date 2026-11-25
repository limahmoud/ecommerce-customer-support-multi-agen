
import os
import uuid

from contextlib import asynccontextmanager

import psycopg

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.types import Command
from langgraph.checkpoint.postgres import PostgresSaver

from agents.supervisor_agent import build_supervisor

from database.operations import (
    create_conversation,
    get_customer_conversations,
    get_customer_conversation,
    update_conversation_last_opened,
    update_conversation_last_message,
    update_return_status,
)

from api.auth import router as auth_router

from database.db import SessionLocal
from database.queries import (
    get_customer_orders,
    get_order_details,
    get_customer_returns,
    get_all_returns,
)
from database.models import User, Conversation, AuditLog
from security.dependencies import get_current_user, require_roles

load_dotenv()


# ==========================================
# CONFIGURATION
# ==========================================

DB_URI = psycopg.conninfo.make_conninfo(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
)



# ==========================================
# LIFESPAN
# ==========================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    with PostgresSaver.from_conn_string(DB_URI) as checkpointer:

        checkpointer.setup()

        app.state.supervisor_agent = build_supervisor(checkpointer)

        yield


app = FastAPI(
    title="Customer Support Multi-Agent API",
    version="1.0.0",
    lifespan=lifespan,
)

# Authentication Routes
app.include_router(auth_router)

# ==========================================
# REQUEST / RESPONSE MODELS
# ==========================================


class ConversationCreateRequest(BaseModel):
    title: str = Field(
        default="New Conversation",
        min_length=1,
        max_length=200,
    )


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    status: str
    answer: str | None = None
    conversation_id: str
    approval_request: dict | None = None


class ApprovalRequest(BaseModel):
    conversation_id: str
    approved: bool
    reason: str = ""


class ReturnStatusRequest(BaseModel):
    new_status: str = Field(min_length=1)



# ==========================================
# HELPERS
# ==========================================

def validate_conversation(conversation_id: str, customer_id: int):

    conversation = get_customer_conversation(
        conversation_id,
        customer_id,
    )

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found.",
        )

    return conversation

def get_customer_id_from_user(current_user: User) -> int:
    if current_user.role != "customer" or current_user.customer_id is None:
        raise HTTPException(
            status_code=403,
            detail="A linked customer account is required.",
        )

    return current_user.customer_id


def get_conversation_owner_id(conversation_id: str) -> int:
    try:
        conversation_uuid = uuid.UUID(conversation_id)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=404,
            detail="Conversation not found.",
        )

    db = SessionLocal()

    try:
        conversation = db.get(Conversation, conversation_uuid)

        if conversation is None:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found.",
            )

        return conversation.customer_id

    finally:
        db.close()

def get_conversation_config(conversation_id: str):

    return {
        "configurable": {
            "thread_id": conversation_id
        }
    }


def serialize_conversation_messages(conversation_id: str):

    config = get_conversation_config(conversation_id)

    try:
        snapshot = app.state.supervisor_agent.get_state(config)

    except Exception:
        return []

    messages = snapshot.values.get("messages", [])

    history = []

    for message in messages:

        if isinstance(message, HumanMessage):

            role = "user"

        elif isinstance(message, AIMessage):

            # Do not expose internal agent/tool calls
            if message.tool_calls:
                continue

            role = "assistant"

        else:
            # Ignore ToolMessage and other internal messages
            continue

        content = message.content

        if not content:
            continue

        if not isinstance(content, str):
            content = str(content)

        history.append({
            "role": role,
            "content": content,
        })

    return history

def get_pending_approval(conversation_id: str):

    config = get_conversation_config(conversation_id)

    try:
        snapshot = app.state.supervisor_agent.get_state(config)

        for task in snapshot.tasks:
            for interruption in getattr(task, "interrupts", []):
                return interruption.value

    except Exception:
        return None

    return None

# ==========================================
# BASIC ENDPOINTS
# ==========================================

@app.get("/")
def home():

    return {
        "message": "Customer Support API is running",
        "status": "success",
    }


@app.get("/health")
def health():

    return {"status": "healthy"}


# ==========================================
# CONVERSATION ENDPOINTS
# ==========================================


@app.post("/conversations")
def create_new_conversation(
    request: ConversationCreateRequest,
    current_user: User = Depends(get_current_user),
):
    customer_id = get_customer_id_from_user(current_user)

    try:
        conversation = create_conversation(
            customer_id=customer_id,
            title=request.title.strip(),
        )

        return {
            "status": "success",
            "conversation": conversation,
        }

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Failed to create conversation.",
        )


@app.get("/conversations/{customer_id}")
def list_conversations(
    customer_id: int,
    current_user: User = Depends(get_current_user),
):
    authenticated_customer_id = get_customer_id_from_user(current_user)

    if customer_id != authenticated_customer_id:
        raise HTTPException(
            status_code=403,
            detail="You cannot access another customer's conversations.",
        )

    try:
        conversations = get_customer_conversations(
            authenticated_customer_id
        )

        return {
            "status": "success",
            "conversations": conversations,
        }

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve conversations.",
        )


@app.get("/conversations/{conversation_id}/messages")
def get_conversation_messages(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
):
    customer_id = get_customer_id_from_user(current_user)

    validate_conversation(conversation_id, customer_id)

    updated = update_conversation_last_opened(
        conversation_id,
        customer_id,
    )

    if not updated:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found.",
        )

    messages = serialize_conversation_messages(conversation_id)
    pending_approval = get_pending_approval(conversation_id)

    return {
        "status": "success",
        "conversation_id": conversation_id,
        "messages": messages,
        "approval_request": pending_approval,
    }


# ==========================================
# CUSTOMER CHAT
# ==========================================

@app.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    customer_id = get_customer_id_from_user(current_user)
    question = request.question.strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty.",
        )

    try:
        if request.conversation_id is None:
            conversation = create_conversation(
                customer_id=customer_id,
                title=question[:50],
            )
            conversation_id = conversation["id"]

        else:
            conversation_id = request.conversation_id

            conversation = validate_conversation(
                conversation_id,
                customer_id,
            )

            title = (
                question[:50]
                if conversation["title"] == "New Conversation"
                else None
            )

            updated = update_conversation_last_message(
                conversation_id,
                customer_id,
                title=title,
            )

            if not updated:
                raise HTTPException(
                    status_code=404,
                    detail="Conversation not found.",
                )

        if request.conversation_id is None:
            update_conversation_last_message(
                conversation_id,
                customer_id,
            )

        config = get_conversation_config(conversation_id)

        result = app.state.supervisor_agent.invoke(
          {
              "messages": [HumanMessage(content=question)],
              "customer_id": customer_id,
          },
          config=get_conversation_config(conversation_id),
      )

        interrupts = result.get("__interrupt__", [])

        if interrupts:
            return ChatResponse(
                status="approval_required",
                conversation_id=conversation_id,
                approval_request=interrupts[0].value,
            )

        answer = result["messages"][-1].content

        return ChatResponse(
            status="completed",
            answer=answer,
            conversation_id=conversation_id,
        )

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Failed to process customer request.",
        )

# ==========================================
# HUMAN APPROVAL
# ==========================================


@app.get("/approvals")
def list_pending_approvals(
    current_user: User = Depends(
        require_roles("support_agent", "returns_agent", "admin")
    ),
):
    allowed_roles = {
        "cancel_order": {"support_agent", "admin"},
        "create_return": {"support_agent", "admin"},
        "refund": {"returns_agent", "admin"},
    }

    db = SessionLocal()

    try:
        conversations = (
            db.query(Conversation)
            .order_by(Conversation.created_at.desc())
            .all()
        )

        approvals = []

        for conversation in conversations:
            conversation_id = str(conversation.id)

            pending = get_pending_approval(conversation_id)

            if not pending:
                continue

            action = pending.get("action")

            if action not in allowed_roles:
                continue

            if current_user.role not in allowed_roles[action]:
                continue

            approvals.append({
                "conversation_id": conversation_id,
                "customer_id": conversation.customer_id,
                "title": conversation.title,
                "action": action,
                "details": pending.get("details", ""),
                "reason": pending.get("reason", ""),
            })

        return {
            "approvals": approvals,
            "total": len(approvals),
        }

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve pending approvals.",
        )

    finally:
        db.close()


@app.post("/approval")
def submit_approval(
    request: ApprovalRequest,
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {
        "support_agent",
        "returns_agent",
        "admin",
    }:
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to review approval requests.",
        )

    config = get_conversation_config(request.conversation_id)

    pending = get_pending_approval(request.conversation_id)

    if not pending:
        raise HTTPException(
            status_code=409,
            detail="There is no pending approval for this conversation.",
        )

    action = pending.get("action")

    allowed_roles = {
        "cancel_order": {"support_agent", "admin"},
        "create_return": {"support_agent", "admin"},
        "refund": {"returns_agent", "admin"},
    }

    if action not in allowed_roles:
        raise HTTPException(
            status_code=400,
            detail="Unknown approval action.",
        )

    if current_user.role not in allowed_roles[action]:
        raise HTTPException(
            status_code=403,
            detail="Your role cannot approve this action.",
        )

    customer_id = get_conversation_owner_id(
        request.conversation_id
    )

    try:
        result = app.state.supervisor_agent.invoke(
            Command(
                resume={
                    "approved": request.approved,
                    "reason": request.reason,
                    "actor_user_id": current_user.id,
                    "actor_role": current_user.role,
                    "actor_email": current_user.email,
                }
            ),
            config=config,
        )

        interrupts = result.get("__interrupt__", [])

        if interrupts:
            return {
                "status": "approval_required",
                "approval_request": interrupts[0].value,
                "conversation_id": request.conversation_id,
            }

        answer = result["messages"][-1].content

        if current_user.role == "admin":
            audit_db = SessionLocal()

            try:
                audit_log = AuditLog(
                    actor_user_id=current_user.id,
                    actor_email=current_user.email,
                    actor_role=current_user.role,
                    action=f"approval_{action}",
                    entity_type=(
                        "return" if action == "refund"
                        else "order"
                    ),
                    entity_id=str(
                        pending.get("return_id")
                        if action == "refund"
                        else pending.get("order_id")
                    ),
                    old_value={
                        "approval_status": "pending",
                    },
                    new_value={
                        "approved": request.approved,
                        "decision": "approved" if request.approved else "rejected",
                        "reason": request.reason,
                        "details": pending.get("details"),
                        "execution_result": answer,
                        "conversation_id": request.conversation_id,
                    },
                )

                audit_db.add(audit_log)
                audit_db.commit()

            except Exception:
                audit_db.rollback()
                raise

            finally:
                audit_db.close()

        update_conversation_last_message(
            request.conversation_id,
            customer_id,
        )

        return {
            "status": "completed",
            "answer": answer,
            "conversation_id": request.conversation_id,
        }

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Failed to process approval.",
        )



# ==========================================
# CUSTOMER ORDERS & RETURNS
# ==========================================


@app.get("/orders")
def list_customer_orders(
    current_user: User = Depends(get_current_user),
):
    customer_id = get_customer_id_from_user(current_user)

    try:
        orders = get_customer_orders(customer_id)

        return {
            "orders": orders,
            "total": len(orders),
        }

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve customer orders.",
        )


@app.get("/orders/{order_id}")
def customer_order_details(
    order_id: int,
    current_user: User = Depends(get_current_user),
):
    customer_id = get_customer_id_from_user(current_user)

    try:
        order = get_order_details(
            order_id=order_id,
            customer_id=customer_id,
        )

        if not order:
            raise HTTPException(
                status_code=404,
                detail="Order not found.",
            )

        return {"order": order}

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve order details.",
        )


@app.get("/returns")
def list_customer_returns(
    current_user: User = Depends(get_current_user),
):
    customer_id = get_customer_id_from_user(current_user)

    try:
        returns = get_customer_returns(customer_id)

        return {
            "returns": returns,
            "total": len(returns),
        }

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve customer returns.",
        )

@app.get("/staff/returns")
def list_all_returns(
    current_user: User = Depends(
        require_roles("returns_agent", "admin")
    ),
):
    try:
        returns = get_all_returns()

        return {
            "returns": returns,
            "total": len(returns),
        }

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve returns.",
        )


@app.patch("/returns/{return_id}/status")
def review_return_status(
    return_id: int,
    request: ReturnStatusRequest,
    current_user: User = Depends(
        require_roles("returns_agent", "admin")
    ),
):
    try:
        result = update_return_status(
            return_id=return_id,
            new_status=request.new_status,
            actor_role=current_user.role,
            actor_user_id=current_user.id,
            actor_email=current_user.email,
        )

        return result

    except PermissionError as error:
        raise HTTPException(
            status_code=403,
            detail=str(error),
        )

    except ValueError as error:
        status_code = (
            404 if "was not found" in str(error) else 400
        )
        raise HTTPException(
            status_code=status_code,
            detail=str(error),
        )

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Failed to update return status.",
        )
