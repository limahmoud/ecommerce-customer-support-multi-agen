
import os
import uuid

import requests
import streamlit as st


# ==========================================
# CONFIGURATION
# ==========================================

API_BASE_URL = os.getenv(
    "API_BASE_URL",
    "http://127.0.0.1:8000",
).rstrip("/")



CHAT_ENDPOINT = f"{API_BASE_URL}/chat"
APPROVALS_ENDPOINT = f"{API_BASE_URL}/approvals"
APPROVAL_ENDPOINT = f"{API_BASE_URL}/approval"
HEALTH_ENDPOINT = f"{API_BASE_URL}/health"
CONVERSATIONS_ENDPOINT = f"{API_BASE_URL}/conversations"
LOGIN_ENDPOINT = f"{API_BASE_URL}/auth/login"
ME_ENDPOINT = f"{API_BASE_URL}/auth/me"
ORDERS_ENDPOINT = f"{API_BASE_URL}/orders"
RETURNS_ENDPOINT = f"{API_BASE_URL}/returns"
STAFF_RETURNS_ENDPOINT = f"{API_BASE_URL}/staff/returns"
# ==========================================
# PAGE CONFIGURATION
# ==========================================

st.set_page_config(
    page_title="Multi-Agent AI Support System",
    page_icon="🤖",
    layout="centered",
)


# ==========================================
# SESSION STATE
# ==========================================

if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = None

if "messages" not in st.session_state:
    st.session_state.messages = []

if "pending_approval" not in st.session_state:
    st.session_state.pending_approval = None

if "conversations" not in st.session_state:
    st.session_state.conversations = []

if "initialization_done" not in st.session_state:
    st.session_state.initialization_done = False

if "access_token" not in st.session_state:
    st.session_state.access_token = None

if "current_user" not in st.session_state:
    st.session_state.current_user = None


# ==========================================
# AUTHENTICATION FUNCTIONS
# ==========================================

def get_auth_headers():
    token = st.session_state.access_token

    return {
        "Authorization": f"Bearer {token}"
    }


def login_user(email: str, password: str):
    response = requests.post(
        LOGIN_ENDPOINT,
        data={
            "username": email,
            "password": password,
        },
        timeout=30,
    )

    response.raise_for_status()

    st.session_state.access_token = response.json()["access_token"]


def fetch_current_user():
    response = requests.get(
        ME_ENDPOINT,
        headers=get_auth_headers(),
        timeout=10,
    )

    response.raise_for_status()

    st.session_state.current_user = response.json()


def logout_user():
    st.session_state.access_token = None
    st.session_state.current_user = None
    st.session_state.conversation_id = None
    st.session_state.messages = []
    st.session_state.pending_approval = None
    st.session_state.conversations = []
    st.session_state.initialization_done = False


# ==========================================
# LOGIN SCREEN
# ==========================================

if not st.session_state.access_token:
    st.title("Customer Support Login")

    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input(
            "Password",
            type="password",
        )

        submitted = st.form_submit_button(
            "Login",
            use_container_width=True,
        )

    if submitted:
        try:
            login_user(email.strip(), password)
            st.rerun()

        except requests.HTTPError as error:
            status_code = error.response.status_code

            try:
              detail = error.response.json().get("detail")
            except ValueError:
               detail = error.response.text

            st.error(f"Login failed: HTTP {status_code}")
            st.error(f"Details: {detail}")

        except requests.ConnectionError:
           st.error(
                 "Cannot connect to FastAPI. "
                 "Check whether the backend is running."
         )

        except requests.RequestException as error:
            st.error(f"Request failed: {error}")

    st.stop()


# ==========================================
# LOAD CURRENT USER
# ==========================================

if st.session_state.current_user is None:
    try:
        fetch_current_user()

    except requests.RequestException:
        logout_user()
        st.error(
            "Session expired. Please login again."
        )
        st.stop()


# ==========================================
# API FUNCTIONS
# ==========================================

def check_api_health():

    try:
        response = requests.get(
            HEALTH_ENDPOINT,
            timeout=5,
        )

        response.raise_for_status()
        return True

    except requests.RequestException:
        return False


def fetch_conversations():
    customer_id = st.session_state.current_user["customer_id"]

    response = requests.get(
        f"{CONVERSATIONS_ENDPOINT}/{customer_id}",
        headers=get_auth_headers(),
        timeout=10,
    )

    response.raise_for_status()

    return response.json().get("conversations", [])

def fetch_orders():

    response = requests.get(
        ORDERS_ENDPOINT,
        headers=get_auth_headers(),
        timeout=10,
    )

    response.raise_for_status()

    return response.json().get("orders", [])


def fetch_order_details(order_id):

    response = requests.get(
        f"{ORDERS_ENDPOINT}/{order_id}",
        headers=get_auth_headers(),
        timeout=10,
    )

    response.raise_for_status()

    return response.json().get("order")


def fetch_returns():

    response = requests.get(
        RETURNS_ENDPOINT,
        headers=get_auth_headers(),
        timeout=10,
    )

    response.raise_for_status()

    return response.json().get("returns", [])

def fetch_staff_returns():

    response = requests.get(
        STAFF_RETURNS_ENDPOINT,
        headers=get_auth_headers(),
        timeout=10,
    )

    response.raise_for_status()

    return response.json().get("returns", [])


def update_staff_return_status(return_id, new_status):

    response = requests.patch(
        f"{RETURNS_ENDPOINT}/{return_id}/status",
        json={"new_status": new_status},
        headers=get_auth_headers(),
        timeout=10,
    )

    response.raise_for_status()

    return response.json()

def fetch_approvals():

    response = requests.get(
        APPROVALS_ENDPOINT,
        headers=get_auth_headers(),
        timeout=20,
    )

    response.raise_for_status()

    return response.json().get("approvals", [])

def create_new_conversation():
    response = requests.post(
        CONVERSATIONS_ENDPOINT,
        json={"title": "New Conversation"},
        headers=get_auth_headers(),
        timeout=10,
    )

    response.raise_for_status()

    return response.json()["conversation"]

def open_conversation(conversation_id):
    response = requests.get(
        f"{CONVERSATIONS_ENDPOINT}/{conversation_id}/messages",
        headers=get_auth_headers(),
        timeout=20,
    )

    response.raise_for_status()

    data = response.json()

    st.session_state.conversation_id = conversation_id
    st.session_state.messages = data.get("messages", [])
    st.session_state.pending_approval = data.get("approval_request")
    st.session_state.conversations = fetch_conversations()


def send_message(question):
    payload = {
        "question": question,
        "conversation_id": st.session_state.conversation_id,
    }

    response = requests.post(
        CHAT_ENDPOINT,
        json=payload,
        headers=get_auth_headers(),
        timeout=180,
    )

    response.raise_for_status()

    return response.json()


def submit_approval(conversation_id, approved, reason=""):

    payload = {
        "conversation_id": conversation_id,
        "approved": approved,
        "reason": reason,
    }

    response = requests.post(
        APPROVAL_ENDPOINT,
        json=payload,
        headers=get_auth_headers(),
        timeout=180,
    )

    response.raise_for_status()

    return response.json()

# ==========================================
# RESPONSE HANDLING
# ==========================================

def handle_api_response(data):

    status = data.get("status")

    if status == "completed":

        answer = data.get("answer") or "No response returned."

        st.session_state.messages.append({
            "role": "assistant",
            "content": answer,
        })

        st.session_state.pending_approval = None

    elif status == "approval_required":

        st.session_state.pending_approval = (
            data.get("approval_request") or {}
        )

    else:

        st.session_state.messages.append({
            "role": "assistant",
            "content": "Unexpected API response.",
        })



# ==========================================
# INITIALIZE FIRST CONVERSATION
# ==========================================

user_role = st.session_state.current_user["role"]

is_customer = user_role == "customer"

is_staff = user_role in {
    "support_agent",
    "returns_agent",
    "admin",
}

if not st.session_state.initialization_done:

    if is_customer:

        try:
            conversations = fetch_conversations()

            if conversations:
                open_conversation(conversations[0]["id"])

            else:
                conversation = create_new_conversation()

                st.session_state.conversation_id = conversation["id"]
                st.session_state.messages = []

                st.session_state.conversations = fetch_conversations()

        except requests.RequestException:
            st.error(
                "Unable to initialize conversations. "
                "Please check that the backend is running."
            )
            st.stop()

    st.session_state.initialization_done = True




# ==========================================
# SIDEBAR
# ==========================================

with st.sidebar:

    st.title("🤖 Multi-Agent AI Support System")

    st.caption("Designed & Developed by Ali Mahmoud EL BAgoury")

    # Logout Button
    if st.button("Logout", use_container_width=True):
        logout_user()
        st.rerun()

    st.divider()

    if not check_api_health():
        st.error("Support system is currently unavailable.")
        st.stop()

    # Navigation based on user role
    if is_customer:
        navigation_pages = ["Chat", "Orders", "Returns"]

    elif user_role == "support_agent":
        navigation_pages = ["Approvals"]

    elif user_role in {"returns_agent", "admin"}:
         navigation_pages = ["Approvals", "Returns Review"]

    else:
        st.error("Your account role is not supported.")
        st.stop()

    selected_page = st.radio(
        "Navigation",
        navigation_pages,
        key="selected_page",
    )

    st.divider()

    # Customer conversations only
    if is_customer:

        st.subheader("Conversations")

        if st.button(
            "➕ New Conversation",
            use_container_width=True,
            type="primary",
        ):

            try:
                conversation = create_new_conversation()

                st.session_state.conversation_id = conversation["id"]
                st.session_state.messages = []
                st.session_state.pending_approval = None

                st.session_state.conversations = fetch_conversations()

                st.rerun()

            except requests.RequestException as error:
                st.error(f"Could not create conversation: {error}")

        st.divider()

        # Refresh conversation list
        try:
            st.session_state.conversations = fetch_conversations()

        except requests.RequestException:
            st.warning("Could not load conversation history.")

        for conversation in st.session_state.conversations:

            conversation_id = conversation["id"]
            title = conversation["title"]

            last_opened = conversation.get("last_opened_at", "")

            if last_opened:
                last_opened = last_opened.replace("T", " ")[:16]
            else:
                last_opened = "Unknown"

            is_active = (
                conversation_id == st.session_state.conversation_id
            )

            if st.button(
                f"{'📍 ' if is_active else '💬 '}{title}\n🕒 {last_opened}",
                key=f"conversation_{conversation_id}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):

                if not is_active:
                    try:
                        open_conversation(conversation_id)
                        st.rerun()

                    except requests.RequestException as error:
                        st.error(f"Could not open conversation: {error}")

    st.divider()

    st.caption("Powered by LangGraph, LangChain and Ollama")



# ==========================================
# APPROVALS PAGE
# ==========================================

if selected_page == "Approvals":

    st.title("Pending Approvals")

    try:

        approvals = fetch_approvals()

        if not approvals:

            st.info("There are no pending approvals.")

        else:

            st.write(f"Total Pending Approvals: {len(approvals)}")

            for approval in approvals:

                conversation_id = approval["conversation_id"]

                with st.container(border=True):

                    st.subheader( "Approval Request")

                    st.write(
                        f"**Customer ID:** {approval.get('customer_id')}"
                    )

                    st.write(
                        f"**Action:** {approval.get('action', 'Unknown')}"
                    )

                    st.write(
                        f"**Details:** {approval.get('details', '')}"
                    )

                    st.write(
                        f"**Reason:** {approval.get('reason', '')}"
                    )

                    rejection_reason = st.text_input(
                        "Rejection reason",
                        key=f"approval_reason_{conversation_id}",
                    )

                    col1, col2 = st.columns(2)

                    with col1:

                        if st.button(
                            "Approve",
                            key=f"approve_{conversation_id}",
                            use_container_width=True,
                            type="primary",
                        ):

                            try:

                                submit_approval(
                                    conversation_id=conversation_id,
                                    approved=True,
                                )

                                st.rerun()

                            except requests.RequestException as error:

                                st.error(
                                    f"Approval failed: {error}"
                                )

                    with col2:

                        if st.button(
                            "Reject",
                            key=f"reject_{conversation_id}",
                            use_container_width=True,
                        ):

                            try:

                                submit_approval(
                                    conversation_id=conversation_id,
                                    approved=False,
                                    reason=rejection_reason,
                                )

                                st.rerun()

                            except requests.RequestException as error:

                                st.error(
                                    f"Rejection failed: {error}"
                                )

    except requests.RequestException as error:

        st.error(f"Could not load pending approvals: {error}")

    st.stop()



# ==========================================
# RETURNS REVIEW PAGE
# ==========================================

if selected_page == "Returns Review":

    st.title("Returns Review")

    try:

        returns = fetch_staff_returns()

        if not returns:

            st.info("There are no return requests.")

        else:

            st.write(f"Total Return Requests: {len(returns)}")

            for returned in returns:

                return_id = returned["return_id"]

                with st.container(border=True):

                    st.subheader(f"Return #{return_id}")

                    st.write(f"**Order ID:** {returned['order_id']}")
                    st.write(f"**Reason:** {returned['reason']}")
                    st.write(f"**Return Status:** {returned['status']}")
                    st.write(
                        f"**Refund Status:** {returned['refund_status']}"
                    )
                    st.write(
                        f"**Created At:** {returned['created_at']}"
                    )

                    if returned["status"] == "pending":

                        col1, col2 = st.columns(2)

                        with col1:

                            if st.button(
                                "Approve Return",
                                key=f"approve_return_{return_id}",
                                use_container_width=True,
                                type="primary",
                            ):

                                try:

                                    update_staff_return_status(
                                        return_id,
                                        "approved",
                                    )

                                    st.success(
                                        f"Return #{return_id} approved."
                                    )

                                    st.rerun()

                                except requests.RequestException as error:

                                    st.error(
                                        f"Approval failed: {error}"
                                    )

                        with col2:

                            if st.button(
                                "Reject Return",
                                key=f"reject_return_{return_id}",
                                use_container_width=True,
                            ):

                                try:

                                    update_staff_return_status(
                                        return_id,
                                        "rejected",
                                    )

                                    st.success(
                                        f"Return #{return_id} rejected."
                                    )

                                    st.rerun()

                                except requests.RequestException as error:

                                    st.error(
                                        f"Rejection failed: {error}"
                                    )

                    else:

                        st.info("This return has already been reviewed.")

    except requests.RequestException as error:

        st.error(f"Could not load return requests: {error}")

    st.stop()



# ==========================================
# ORDERS PAGE
# ==========================================

if selected_page == "Orders":

    st.title("My Orders")

    try:

        orders = fetch_orders()

        if not orders:

            st.info("You don't have any orders yet.")

        else:

            selected_order = st.selectbox(
                "Select an order",
                orders,
                format_func=lambda order: (
                    f"Order #{order['order_id']} - "
                    f"{order['status']}"
                ),
            )

            if selected_order:

                order_id = selected_order["order_id"]

                order_data = fetch_order_details(order_id)

                if order_data:

                    st.subheader(f"Order #{order_id}")

                    st.write(
                        f"**Date:** {order_data['order_date']}"
                    )

                    st.write(
                        f"**Status:** {order_data['status']}"
                    )

                    st.write(
                        f"**Total:** {order_data['total_amount']}"
                    )

                    st.divider()

                    st.subheader("Order Items")

                    if order_data["items"]:
                        st.table(order_data["items"])
                    else:
                        st.info("No items found.")

                    st.subheader("Shipments")

                    if order_data["shipments"]:
                        st.table(order_data["shipments"])
                    else:
                        st.info("No shipment information available.")

                    st.subheader("Returns")

                    if order_data["returns"]:
                        st.table(order_data["returns"])
                    else:
                        st.info("No returns for this order.")

    except requests.RequestException as error:

        st.error(f"Could not load orders: {error}")

    st.stop()


# ==========================================
# RETURNS PAGE
# ==========================================

if selected_page == "Returns":

    st.title("My Returns")

    try:

        returns = fetch_returns()

        if not returns:

            st.info("You don't have any returns yet.")

        else:

            st.write(f"Total Returns: {len(returns)}")

            st.table(returns)

    except requests.RequestException as error:

        st.error(f"Could not load returns: {error}")

    st.stop()



# ==========================================
# MAIN HEADER
# ==========================================

st.title("Customer Support Assistant")

st.write("Hello! How can I help you today?")

st.divider()


# ==========================================
# CUSTOMER CHAT WITH AUTO REFRESH
# ==========================================

@st.fragment(run_every="5s")
def customer_chat():

    conversation_id = st.session_state.conversation_id

    # Refresh messages and approval status
    if conversation_id:

        try:
            response = requests.get(
                f"{CONVERSATIONS_ENDPOINT}/{conversation_id}/messages",
                headers=get_auth_headers(),
                timeout=10,
            )

            response.raise_for_status()

            data = response.json()

            st.session_state.messages = data.get("messages", [])

            st.session_state.pending_approval = data.get(
                "approval_request"
            )

        except requests.RequestException:
            st.warning("Unable to refresh conversation messages.")

    # Display chat history
    for message in st.session_state.messages:

        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Pending approval status
    pending = st.session_state.pending_approval

    if pending:

        st.info(
            "You can continue once an authorized team member "
            "has reviewed your request."
        )

    # Chat input
    if st.session_state.pending_approval is None:

        question = st.chat_input(
            "Type your message here..."
        )

        if question:

            st.session_state.messages.append({
                "role": "user",
                "content": question,
            })

            try:

                with st.spinner("Assistant is thinking..."):

                    result = send_message(question)

                handle_api_response(result)

                st.session_state.conversations = fetch_conversations()

                st.rerun()

            except requests.RequestException as error:

                st.error(
                    f"Could not connect to the backend: {error}"
                )

    else:

        st.info(
            "Please approve or reject the pending action "
            "before sending another message."
        )


customer_chat()
