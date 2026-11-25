from agents.error_handling import invoke_llm_safely, TOOL_ERROR_MESSAGE

import os
import re
from uuid import uuid4
from typing import Annotated


from agents.llm_factory import create_chat_model
from langchain_core.tools import tool
from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    SystemMessage,
)

from langgraph.graph import StateGraph, START
from graph.state import SupportState
from langgraph.prebuilt import (
    ToolNode,
    tools_condition,
    InjectedState,
)

from agents.customer_agent import customer_agent
from agents.order_agent import order_agent
from agents.shipping_agent import shipping_agent
from agents.returns_agent import returns_agent

from typing import Literal
from langgraph.types import interrupt

from database.operations import (
    update_order_status,
    create_return,
    update_refund_status,
    request_refund,
)

from graph.state import SupportState

# 1. Load Environment Variables

# 2. Prepare Conversation History for Specialist Agents
def prepare_agent_messages(state: SupportState, question: str):

    conversation_history = []

    for message in state["messages"]:

        # Ignore supervisor messages that contain tool calls.
        # Their tool calls belong to the supervisor, not the specialist.
        if isinstance(message, AIMessage) and message.tool_calls:
            continue

        # Keep actual customer messages and normal assistant responses.
        if isinstance(message, (HumanMessage, AIMessage)):
            conversation_history.append(message)

    # Add the clear task assigned by the supervisor.
    conversation_history.append(
        HumanMessage(
            content=f"Task from Supervisor: {question}"
        )
    )

    return conversation_history


# 3. Convert Specialist Agents into Tools

@tool
def ask_customer_agent(
    question: str,
    state: Annotated[SupportState, InjectedState],
) -> str:
    """Use for customer information, customer email, customer ID, and support tickets."""

    messages = prepare_agent_messages(state, question)

    result = customer_agent.invoke({
    "messages": messages,
    "customer_id": state["customer_id"],
    })

    return str(result["messages"][-1].content)


@tool
def ask_order_agent(
    question: str,
    state: Annotated[SupportState, InjectedState],
) -> str:
    """Use for customer orders, order details, and products inside orders."""

    messages = prepare_agent_messages(state, question)

    result = order_agent.invoke({
    "messages": messages,
    "customer_id": state["customer_id"],
    })

    return str(result["messages"][-1].content)


@tool
def ask_shipping_agent(
    question: str,
    state: Annotated[SupportState, InjectedState],
) -> str:
    """Use for shipment information, tracking numbers, delivery status, and estimated delivery."""

    messages = prepare_agent_messages(state, question)

    result = shipping_agent.invoke({
    "messages": messages,
    "customer_id": state["customer_id"],
    })

    return str(result["messages"][-1].content)


@tool
def ask_returns_agent(question: str,state: Annotated[SupportState, InjectedState],) -> str:
    """Use for product returns, return IDs, return status, and return information."""

    messages = prepare_agent_messages(state, question)

    result = returns_agent.invoke({
    "messages": messages,
    "customer_id": state["customer_id"],
    })

    return str(result["messages"][-1].content)


@tool
def request_sensitive_action(
    state: Annotated[SupportState, InjectedState],
    action: Literal["refund", "cancel_order", "create_return"],
    details: str,
    reason: str,
    order_id: int | None = None,
    return_id: int | None = None,
) -> str:
    """
    Request human approval before executing a sensitive action.

    Customer ID is injected from the authenticated graph state.
    """

    customer_id = state["customer_id"]

    # 1. Validate IDs.
    if action in ("cancel_order", "create_return"):

        if order_id is None or return_id is not None:
            return "Invalid IDs: this action requires order_id only."

    elif action == "refund":

        if return_id is None or order_id is not None:
            return "Invalid IDs: refund requires return_id only."

    # 2. Submit refund request before asking for human approval.
    if action == "refund":
        try:
            request_refund(
                return_id=return_id,
                customer_id=customer_id,
            )
        except (ValueError, PermissionError) as error:
            return f"Refund request could not be submitted: {error}"

    # 3. Request human approval.
    approval_data = {
        "action": action,
        "order_id": order_id,
        "return_id": return_id,
        "details": details,
        "reason": reason,
    }

    decision = interrupt(approval_data)

    approved = decision.get("approved", False)

    # Preserve the existing rejection behavior for other actions.
    if not approved and action != "refund":
        return (
            f"Action rejected. "
            f"Reason: {decision.get('reason', 'Not provided')}"
        )

        # Reviewer identity comes from the authenticated API.
    actor_role = decision.get("actor_role")
    actor_user_id = decision.get("actor_user_id")
    actor_email = decision.get("actor_email")

    allowed_roles = {
        "cancel_order": {"support_agent", "admin"},
        "create_return": {"support_agent", "admin"},
        "refund": {"returns_agent", "admin"},
    }

    if (
        not actor_role
        or actor_role not in allowed_roles[action]
        or not actor_user_id
    ):
        return "Approval rejected: reviewer is not authorized."

    try:

        if action == "cancel_order":

            result = update_order_status(
                order_id=order_id,
                new_status="cancelled",
                actor_role=actor_role,
                customer_id=customer_id,
                actor_user_id=actor_user_id,
                actor_email=actor_email,
            )

        elif action == "create_return":

            result = create_return(
                order_id=order_id,
                reason=reason,
                actor_role=actor_role,
                customer_id=customer_id,
                actor_user_id=actor_user_id,
                actor_email=actor_email,
            )

        elif action == "refund":

            result = update_refund_status(
                return_id=return_id,
                new_refund_status="processing" if approved else "rejected",
                actor_role=actor_role,
                customer_id=customer_id,
                actor_user_id=actor_user_id,
                actor_email=actor_email,
            )

        if not approved:
            return (
                "Refund request rejected. "
                f"Reason: {decision.get('reason', 'Not provided')}. "
                f"Result: {result}"
            )

        return (
            "Action approved and executed successfully. "
            f"Result: {result}"
        )

    except (ValueError, PermissionError) as error:

        return (
            f"Action could not be executed: {error}"
        )




# 4. Supervisor Tools
supervisor_tools = [
    ask_customer_agent,
    ask_order_agent,
    ask_shipping_agent,
    ask_returns_agent,
     request_sensitive_action,
]


# 5. Initialize LLM
llm = create_chat_model()

llm_with_tools = llm.bind_tools(supervisor_tools)


# 6. Supervisor System Prompt
supervisor_system_message = SystemMessage(
    content="""
    You are the Supervisor of an e-commerce customer support system.

    Your job is to understand the customer's question and select
    the correct specialized agent.

    AVAILABLE AGENTS:

    1. Customer Agent:
       Customer information, email, customer ID, support tickets.

    2. Order Agent:
       Orders, order details, order items, products.

    3. Shipping Agent:
       Shipment tracking, delivery status, tracking numbers.

    4. Returns Agent:
       Returns, return status, return details.

    RULES:

    - Use the appropriate agent for database questions.
    - Never invent database information.
    - Never invent customer IDs, order IDs, return IDs, or tracking numbers.
    - Ask the customer if essential information is missing.
    - For questions involving multiple topics, call the relevant agents.

    CONVERSATION MEMORY:

    - Use the complete conversation history.
    - Remember IDs and details mentioned in previous messages.
    - Resolve references such as "it", "that order", and "the shipment".
    - Do not ask for information already provided.

    WHEN CALLING AN AGENT:

    - Pass a clear and complete task in the question argument.
    - Include the exact relevant IDs from conversation history.
    - Resolve pronouns before calling the agent.

    Example:

    Customer: Show me the details of order 1.
    Customer: What products are included in it?

    The second question refers to order 1.

    Call ask_order_agent with:
    "Show me the products included in order 1."

    Never replace a known ID with a guessed ID.
    Wait for the actual agent result before answering.

MANDATORY TOOL FOR SENSITIVE ACTIONS:

You MUST call request_sensitive_action whenever
the customer requests:

- Canceling an order.
- Creating a product return.
- Requesting a refund.

Use:
- cancel_order for cancellation.
- create_return for a new return.
- refund for refund requests.

Never claim that an action was approved or completed
without receiving the corresponding approval.


SPECIALIST ROUTING RULES:

1. When the customer asks about order details,
   always use ask_order_agent.

2. When the customer asks about shipment status,
   tracking numbers, carriers, or delivery estimates,
   ALWAYS call ask_shipping_agent.

3. Do NOT answer shipment questions directly
   using shipment information found in previous messages
   or Order Agent responses.

4. Use the conversation history to identify the relevant
   order_id when the customer uses references such as:
   "its shipment", "that order", or "the same order".

5. If the order_id is available from conversation history,
   pass it to the appropriate specialist without asking
   the customer to provide it again.

6. Each specialist must handle its own domain.
   Do not replace a specialist call with information
   retrieved from another specialist.

    """
)


def detect_sensitive_action(state: SupportState):

    messages = state["messages"]

    # Only process a new customer message.
    if not messages or not isinstance(messages[-1], HumanMessage):
        return None

    question = str(messages[-1].content).strip()

    # Detect explicit action intent, not ordinary status inquiries.
    patterns = {
        "refund": [
            r"\brequest\s+(?:a\s+)?refund\b",
            r"\b(?:process|initiate|claim)\s+(?:a\s+)?refund\b",
            r"\b(?:i want|i need|i'd like)\s+(?:to get\s+)?(?:a\s+)?refund\b",
            r"\bget\s+my money back\b",
            r"\brefund\s+(?:for|on)\s+return\s*#?\s*\d+\b",
        ],
        "cancel_order": [
            r"\b(?:please\s+)?cancel\s+(?:my\s+)?order\b",
            r"\b(?:i want|i need|i'd like)\s+to cancel\b",
            r"\b(?:can|could)\s+you\s+cancel\b",
            r"\bcancel\s+(?:it|this order|that order)\b",
        ],
        "create_return": [
            r"\b(?:create|open|start|submit|request|initiate)\s+(?:a\s+)?(?:product\s+)?return\b",
            r"\b(?:i want|i need|i'd like)\s+to return\b",
            r"\b(?:please|can you|could you)\s+return\b",
            r"\breturn\s+(?:my\s+)?order\s*#?\s*\d+\b",
            r"\bsend\s+(?:this|that|the|my)?\s*(?:product|item|order)\s+back\b",
        ],
    }

    action = None

    for action_name, action_patterns in patterns.items():
        if any(
            re.search(pattern, question, re.IGNORECASE)
            for pattern in action_patterns
        ):
            action = action_name
            break

    if action is None:
        return None

    # Refund requires a return ID.
    if action == "refund":
        id_pattern = r"\breturn\s*#?\s*(\d+)\b"
    else:
        id_pattern = r"\border\s*#?\s*(\d+)\b"

    id_match = re.search(
        id_pattern,
        question,
        re.IGNORECASE,
    )

    # Search previous customer messages for the relevant ID.
    if not id_match:
        for message in reversed(messages[:-1]):
            if isinstance(message, HumanMessage):
                id_match = re.search(
                    id_pattern,
                    str(message.content),
                    re.IGNORECASE,
                )

                if id_match:
                    break

    if not id_match:

        if action == "refund":
            return AIMessage(
                content=(
                    "Which return would you like to request a refund for? "
                    "Please provide the return ID."
                )
            )

        return AIMessage(
            content=(
                "Which order are you referring to? "
                "Please provide the order ID."
            )
        )

    entity_id = int(id_match.group(1))

    args = {
        "action": action,
        "order_id": (
            entity_id
            if action in ("cancel_order", "create_return")
            else None
        ),
        "return_id": (
            entity_id
            if action == "refund"
            else None
        ),
        "details": f"Customer requested {action}.",
        "reason": question,
    }

    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "request_sensitive_action",
                "args": args,
                "id": str(uuid4()),
                "type": "tool_call",
            }
        ],
    )



# 7. Supervisor Node
def supervisor_node(state: SupportState):

    # 1. Check for mandatory sensitive actions.
    sensitive_action = detect_sensitive_action(state)

    if sensitive_action is not None:

        return {
            "messages": [sensitive_action]
        }

    # 2. Normal Supervisor routing.
    messages = [
        supervisor_system_message,
        *state["messages"]
    ]

    response = invoke_llm_safely(llm_with_tools, messages)

    return {
        "messages": [response]
    }


# 8. Build Graph
builder = StateGraph(SupportState)

builder.add_node("supervisor", supervisor_node)
builder.add_node("tools", ToolNode(supervisor_tools, handle_tool_errors=TOOL_ERROR_MESSAGE))

builder.add_edge(START, "supervisor")

builder.add_conditional_edges(
    "supervisor",
    tools_condition
)

builder.add_edge("tools", "supervisor")


# 9. Compile with External Checkpointer
def build_supervisor(checkpointer):

    return builder.compile(
        checkpointer=checkpointer
    )
