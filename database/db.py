
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from database.models import Base

# Load environment variables
load_dotenv()

DB_PASSWORD = os.getenv("DB_PASSWORD")

if not DB_PASSWORD:
    raise ValueError("DB_PASSWORD is missing from .env")

# Database URL
DATABASE_URL = URL.create(
    drivername="postgresql+psycopg",
    username="support_user",
    password=DB_PASSWORD,
    host="localhost",
    port=5433,
    database="customer_support",
)

# Create Engine
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)

# Create Session Factory
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False
)


# Create database tables
def create_tables():
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")


# Test database connection
def test_connection():
    with engine.connect() as connection:
        result = connection.execute(text("SELECT version()"))
        print("Database connected successfully!")
        print(result.scalar())


if __name__ == "__main__":
    create_tables()
    test_connection()
