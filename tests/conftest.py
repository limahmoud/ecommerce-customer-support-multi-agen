import os

# Keep integration tests independent of external LLM API keys.
os.environ.setdefault("LLM_PROVIDER", "ollama")

# Use the isolated test database during pytest
os.environ["DB_NAME"] = "customer_support_test"

from database.db import create_tables

# Create ORM tables in the test database
create_tables()
