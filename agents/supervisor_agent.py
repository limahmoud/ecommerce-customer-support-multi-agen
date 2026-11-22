
import os
import re
from uuid import uuid4
from typing import Annotated

from dotenv import load_dotenv

from langchain_ollama import ChatOllama
from langchain_core.tools import tool
from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    SystemMessage,
)

from langgraph.graph import StateGraph, START, MessagesState
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
)

# 1. Load Environment Variables
load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")

if not OLLAMA_MODEL or not OLLAMA_BASE_URL:
    raise ValueError("OLLAMA_MODEL or OLLAMA_BASE_URL is missing from .env")


# 2. Prepare Conversation History for Specialist Agents
def prepare_agent_messages(state: MessagesState, question: str):

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
    state: Annotated[MessagesState, InjectedState],
) -> str:
    """Use for customer information, customer email, customer ID, and support tickets."""

    messages = prepare_agent_messages(state, question)

    result = customer_agent.invoke({
        "messages": messages
    })

    return str(result["messages"][-1].content)


@tool
def ask_order_agent(
    question: str,
    state: Annotated[MessagesState, InjectedState],
) -> str:
    """Use for customer orders, order details, and products inside orders."""

    messages = prepare_agent_messages(state, question)

    result = order_agent.invoke({
        "messages": messages
    })

    return str(result["messages"][-1].content)


@tool
def ask_shipping_agent(
    question: str,
    state: Annotated[MessagesState, InjectedState],
) -> str:
    """Use for shipment information, tracking numbers, delivery status, and estimated delivery."""

    messages = prepare_agent_messages(state, question)

    result = shipping_agent.invoke({
        "messages": messages
    })

    return str(result["messages"][-1].content)


@tool
def ask_returns_agent(question: str,state: Annotated[MessagesState, InjectedState],) -> str:
    """Use for product returns, return IDs, return status, and return information."""

    messages = prepare_agent_messages(state, question)

    result = returns_agent.invoke({
        "messages": messages
    })

    return str(result["messages"][-1].content)


@tool
def request_sensitive_action(
    action: Literal["refund", "cancel_order", "create_return"],
    details: str,
    reason: str,
    order_id: int | None = None,
    return_id: int | None = None,
) -> str:
    """
    Request human approval before executing a sensitive action.

    cancel_order: requires order_id.
    create_return: requires order_id.
    refund: requires return_id.
    """

    # 1. Validate IDs.
    if action in ("cancel_order", "create_return"):

        if order_id is None or return_id is not None:
            return "Invalid IDs: this action requires order_id only."

    elif action == "refund":

        if return_id is None or order_id is not None:
            return "Invalid IDs: refund requires return_id only."

    # 2. Request human approval.
    approval_data = {
        "action": action,
        "order_id": order_id,
        "return_id": return_id,
        "details": details,
        "reason": reason,
    }

    decision = interrupt(approval_data)

    # 3. Stop if rejected.
    if not decision.get("approved", False):
        return (
            f"Action rejected. "
            f"Reason: {decision.get('reason', 'Not provided')}"
        )

    # 4. Execute only after approval.
    # Prototype role: will be replaced with authenticated identity.
    actor_role = "support_agent"

    try:

        if action == "cancel_order":

            result = update_order_status(
                order_id=order_id,
                new_status="cancelled",
                actor_role=actor_role,
            )

        elif action == "create_return":

            result = create_return(
                order_id=order_id,
                reason=reason,
                actor_role=actor_role,
            )

        elif action == "refund":

            result = update_refund_status(
                return_id=return_id,
                new_refund_status="pending",
                actor_role=actor_role,
            )

        return (
            f"Action approved and executed successfully. "
            f"Result: {result}"
        )

    except ValueError as error:

        return (
            f"Action was approved but could not be executed: {error}"
        )

    except Exception:

        return (
            "Action was approved but execution failed "
            "because of an internal database error."
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
llm = ChatOllama(
    model=OLLAMA_MODEL,
    base_url=OLLAMA_BASE_URL,
    temperature=0,
)

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


def detect_sensitive_action(state: MessagesState):

    messages = state["messages"]

    # Only process a new customer message.
    if not messages or not isinstance(messages[-1], HumanMessage):
        return None

    question = str(messages[-1].content)

    # Detect sensitive action.
    patterns = {
        "cancel_order": r"\b(cancel|cancellation|cancelling|canceling)\b",
        "create_return": r"\b(return|returning)\b",
        "refund": r"\b(refund|refunding|reimburse)\b",
    }

    action = None

    for action_name, pattern in patterns.items():
        if re.search(pattern, question, re.IGNORECASE):
            action = action_name
            break

    if action is None:
        return None

    # Find the required ID in the current message.
    if action == "refund":
        id_pattern = r"\breturn\s*#?\s*(\d+)\b"
    else:
        id_pattern = r"\border\s*#?\s*(\d+)\b"

    id_match = re.search(
        id_pattern,
        question,
        re.IGNORECASE,
    )

    # Search previous customer messages if needed.
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
                content="Which return would you like to request a refund for? Please provide the return ID."
            )

        return AIMessage(
            content="Which order are you referring to? Please provide the order ID."
        )

    entity_id = int(id_match.group(1))

    
    # Prepare approval request.
    args = {
        "action": action,
        "order_id": (
            entity_id if action in ("cancel_order", "create_return")
            else None
        ),
        "return_id": (
            entity_id if action == "refund"
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
def supervisor_node(state: MessagesState):

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

    response = llm_with_tools.invoke(messages)

    return {
        "messages": [response]
    }


# 8. Build Graph
builder = StateGraph(MessagesState)

builder.add_node("supervisor", supervisor_node)
builder.add_node("tools", ToolNode(supervisor_tools))

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
