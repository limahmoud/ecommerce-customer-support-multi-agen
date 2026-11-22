
from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from agents.approval import (
    approval_node,
    execute_action,
    reject_action,
)


class ApprovalState(TypedDict, total=False):

    action: str
    details: str
    reason: str

    approved: bool
    approval_reason: str

    result: str


def approval_router(state: ApprovalState):

    if state["approved"]:
        return "execute"

    return "reject"


builder = StateGraph(ApprovalState)

builder.add_node("approval", approval_node)
builder.add_node("execute", execute_action)
builder.add_node("reject", reject_action)

builder.add_edge(START, "approval")

builder.add_conditional_edges(
    "approval",
    approval_router,
    {
        "execute": "execute",
        "reject": "reject",
    },
)

builder.add_edge("execute", END)
builder.add_edge("reject", END)


def build_approval_graph(checkpointer):

    return builder.compile(
        checkpointer=checkpointer
    )
