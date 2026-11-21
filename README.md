# E-commerce Customer Support Multi-Agent System

An AI-powered customer support system designed to handle e-commerce customer inquiries using multiple specialized AI agents, LangGraph, and a relational database.

## Overview

This project aims to automate e-commerce customer support operations by allowing AI agents to retrieve customer information, track orders and shipments, manage returns, and handle refund-related inquiries.

The system combines Large Language Models (LLMs), Agentic AI, and database operations to provide structured and context-aware responses.

## Key Features

- **Multi-Agent Architecture:** Specialized agents handle different customer support tasks.
- **Order Management:** Retrieve order details and update order statuses.
- **Customer Information:** Access customer records and related information.
- **Shipment Tracking:** Retrieve shipment details using tracking numbers.
- **Returns Management:** Handle return-related operations.
- **Refund Management:** Retrieve and update refund information.
- **Tool Calling:** Allow agents to select and execute tools based on user requests.
- **Database Integration:** Interact with relational database tables through SQLAlchemy.

## Technologies Used

| Technology | Purpose |
|---|---|
| Python | Main programming language |
| LangGraph | Agent workflow orchestration |
| LangChain | LLM and tool integration |
| SQLAlchemy | ORM and database operations |
| PostgreSQL | Relational database |
| Docker | Containerization |
| Git & GitHub | Version control |

## Architecture

The system follows an agent-based architecture where each agent is responsible for a specific part of the customer support workflow.

### Agent Workflow

1. The customer sends a support request.
2. The appropriate agent receives the request.
3. The LLM determines whether a database tool is required.
4. LangGraph routes the execution to the appropriate tool.
5. The tool retrieves or updates the requested information.
6. The result is returned to the agent.
7. The agent generates a response for the customer.

### Example Workflow

**Customer:** "Where is my order number 10?"

- The Order Agent analyzes the request.
- It selects the appropriate order retrieval tool.
- The tool queries the database.
- The result is returned to the agent.
- The agent generates a customer-friendly response.

## Database

The database is designed to support the main e-commerce customer support operations.

Core entities include:

- Customers
- Orders
- Shipments
- Returns
- Refunds

SQLAlchemy is used to define ORM models and implement database operations.

## Project Structure

```text
Customer Support Multi-Agent System/
│
├── database/
│   ├── __init__.py
│   ├── base.py
│   ├── customers.py
│   ├── orders.py
│   └── operations.py
│
├── agents/
│   └── ...
│
├── tools/
│   └── ...
│
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

*Note: The structure above is an illustrative overview. Update it to match the actual files in the repository.*

## Installation

### 1. Clone the repository

```bash
git clone YOUR_REPOSITORY_URL
cd "Customer Support Multi-Agent System"
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file based on `.env.example` and add your own API credentials and database configuration.

Never commit your `.env` file or expose API keys and passwords.

### 5. Run the application

Run the project's entry-point script after configuring the database and environment variables.

## Future Improvements

- Add more specialized customer support agents.
- Implement human-in-the-loop approval for sensitive operations.
- Improve authentication and role-based authorization.
- Add conversation memory.
- Integrate monitoring and logging.
- Deploy the system to a cloud environment.

## Project Status

<code>In Development</code>

This project is being developed incrementally, with a focus on building a reliable multi-agent customer support architecture.

## Author

**Ali Mahmoud Ali**

Computer and Data Science Student | AI & Machine Learning Enthusiast

