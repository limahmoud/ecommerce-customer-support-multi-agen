
import os
import uuid

import psycopg

from dotenv import load_dotenv

from langgraph.types import Command
from langgraph.checkpoint.postgres import PostgresSaver

from agents.approval_graph import build_approval_graph


load_dotenv()


def main():

    db_uri = psycopg.conninfo.make_conninfo(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )

    thread_id = str(uuid.uuid4())

    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    with PostgresSaver.from_conn_string(db_uri) as checkpointer:

        checkpointer.setup()

        approval_graph = build_approval_graph(checkpointer)

        print("\n=== HUMAN IN THE LOOP TEST ===\n")

        # Start workflow
        result = approval_graph.invoke(
            {
                "action": "Issue Refund",
                "details": "Refund for order 1",
                "reason": "Customer requested a refund.",
            },
            config=config,
        )

        # Display approval request
        interrupts = result.get("__interrupt__", [])

        if not interrupts:
            print("No approval request was generated.")
            return

        approval_request = interrupts[0].value

        print("Approval Required!")
        print("----------------------")
        print("Action:", approval_request["action"])
        print("Details:", approval_request["details"])
        print("Reason:", approval_request["reason"])

        # Ask human for decision
        decision = input(
            "\nApprove this action? (yes/no): "
        ).strip().lower()

        approved = decision in ["yes", "y"]

        reason = input("Enter decision reason: ").strip()

        # Resume workflow
        final_result = approval_graph.invoke(
            Command(
                resume={
                    "approved": approved,
                    "reason": reason,
                }
            ),
            config=config,
        )

        print("\n=== FINAL RESULT ===")
        print(final_result["result"])


if __name__ == "__main__":
    main()
