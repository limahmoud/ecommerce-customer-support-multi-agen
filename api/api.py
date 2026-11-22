
import os
import uuid

from contextlib import asynccontextmanager

import psycopg

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
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
)


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

# Temporary demo customer until Authentication
DEFAULT_CUSTOMER_ID = 1


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


# ==========================================
# REQUEST / RESPONSE MODELS
# ==========================================

class ConversationCreateRequest(BaseModel):

    customer_id: int = DEFAULT_CUSTOMER_ID

    title: str = Field(
        default="New Conversation",
        min_length=1,
        max_length=200,
    )


class ChatRequest(BaseModel):

    question: str = Field(min_length=1)

    conversation_id: str | None = None

    customer_id: int = DEFAULT_CUSTOMER_ID


class ChatResponse(BaseModel):

    status: str
    answer: str | None = None
    conversation_id: str
    approval_request: dict | None = None


class ApprovalRequest(BaseModel):

    conversation_id: str

    customer_id: int = DEFAULT_CUSTOMER_ID

    approved: bool

    reason: str = ""


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
def create_new_conversation(request: ConversationCreateRequest):

    try:

        conversation = create_conversation(
            customer_id=request.customer_id,
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
def list_conversations(customer_id: int):

    try:

        conversations = get_customer_conversations(customer_id)

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
    customer_id: int = DEFAULT_CUSTOMER_ID,
):

    validate_conversation(conversation_id, customer_id)

    # Opening the conversation updates its last-opened timestamp
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
def chat(request: ChatRequest):

    question = request.question.strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty.",
        )

    customer_id = request.customer_id

    try:

        # Create a conversation automatically if none was supplied
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

            # Use first user message as conversation title
            title = None

            if conversation["title"] == "New Conversation":
                title = question[:50]

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

        # Update activity timestamp for newly created conversations too
        if request.conversation_id is None:
            update_conversation_last_message(
                conversation_id,
                customer_id,
            )

        config = get_conversation_config(conversation_id)

        result = app.state.supervisor_agent.invoke(
            {
                "messages": [
                    HumanMessage(content=question)
                ]
            },
            config=config,
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

@app.post("/approval")
def submit_approval(request: ApprovalRequest):

    validate_conversation(
        request.conversation_id,
        request.customer_id,
    )

    config = get_conversation_config(
        request.conversation_id
    )

    try:

        result = app.state.supervisor_agent.invoke(
            Command(
                resume={
                    "approved": request.approved,
                    "reason": request.reason,
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

        update_conversation_last_message(
            request.conversation_id,
            request.customer_id,
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
