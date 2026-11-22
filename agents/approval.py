
from langgraph.types import interrupt


def approval_node(state):

    approval_request = {
        "action": state["action"],
        "details": state["details"],
        "reason": state["reason"],
    }

    # Pause execution and wait for human decision
    decision = interrupt(approval_request)

    return {
        "approved": decision.get("approved", False),
        "approval_reason": decision.get("reason", ""),
    }


def execute_action(state):

    # Demo only - no real database operation
    return {
        "result": (
            f"Action '{state['action']}' approved. "
            f"Reason: {state['approval_reason']}"
        )
    }


def reject_action(state):

    return {
        "result": (
            f"Action '{state['action']}' rejected. "
            f"Reason: {state['approval_reason']}"
        )
    }
