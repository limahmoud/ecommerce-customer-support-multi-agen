
import os
import uuid

from dotenv import load_dotenv

from psycopg.conninfo import make_conninfo
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_core.messages import HumanMessage

from agents.supervisor_agent import build_supervisor


# 1. Load Environment Variables

load_dotenv()


# 2. Database Configuration

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5433")
DB_NAME = os.getenv("DB_NAME", "customer_support")
DB_USER = os.getenv("DB_USER", "support_user")
DB_PASSWORD = os.getenv("DB_PASSWORD")

if not DB_PASSWORD:
    raise ValueError("DB_PASSWORD is missing from .env")


# Build PostgreSQL connection string safely
DB_URI = make_conninfo(
    host=DB_HOST,
    port=DB_PORT,
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD,
)

# 3. Main Application

def main():

    print("=" * 60)
    print("       CUSTOMER SUPPORT MULTI-AGENT SYSTEM")
    print("=" * 60)

    print("\nConnecting to PostgreSQL Memory...")

    # Open PostgreSQL Checkpointer
    with PostgresSaver.from_conn_string(DB_URI) as checkpointer:

        # Create checkpoint tables if they don't exist
        checkpointer.setup()

        # Build Supervisor with PostgreSQL Memory
        supervisor_agent = build_supervisor(checkpointer)

        print("\nPostgreSQL Memory Connected!")
        print("\nEnter an existing Conversation ID to resume.")
        print("Leave empty to create a new conversation.\n")

        conversation_id = input("Conversation ID: ").strip()

        if not conversation_id:
            conversation_id = str(uuid.uuid4())

        config = {
            "configurable": {
                "thread_id": conversation_id
            }
        }

        print("\nSystem is ready!")
        print("Conversation ID:", conversation_id)
        print("Type 'exit' to stop.\n")

        while True:

            question = input("Customer: ").strip()

            if question.lower() in ["exit", "quit", "bye"]:
                print("\nGoodbye!")
                break

            if not question:
                continue

            try:

                result = supervisor_agent.invoke(
                    {
                        "messages": [
                            HumanMessage(content=question)
                        ]
                    },
                    config=config
                )

                response = result["messages"][-1].content

                print("\nAssistant:", response)
                print("\n" + "-" * 60)

            except Exception as error:

                print("\nError:", str(error))
                print("\nPlease try again.")


if __name__ == "__main__":
    main()
