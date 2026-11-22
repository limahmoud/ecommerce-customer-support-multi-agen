
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

CUSTOMER_ID = 1

CHAT_ENDPOINT = f"{API_BASE_URL}/chat"
APPROVAL_ENDPOINT = f"{API_BASE_URL}/approval"
HEALTH_ENDPOINT = f"{API_BASE_URL}/health"
CONVERSATIONS_ENDPOINT = f"{API_BASE_URL}/conversations"


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

    response = requests.get(
        f"{CONVERSATIONS_ENDPOINT}/{CUSTOMER_ID}",
        timeout=10,
    )

    response.raise_for_status()

    return response.json().get("conversations", [])


def create_new_conversation():

    response = requests.post(
        CONVERSATIONS_ENDPOINT,
        json={
            "customer_id": CUSTOMER_ID,
            "title": "New Conversation",
        },
        timeout=10,
    )

    response.raise_for_status()

    return response.json()["conversation"]


def open_conversation(conversation_id):

    response = requests.get(
        f"{CONVERSATIONS_ENDPOINT}/{conversation_id}/messages",
        params={
            "customer_id": CUSTOMER_ID,
        },
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
        "customer_id": CUSTOMER_ID,
    }

    response = requests.post(
        CHAT_ENDPOINT,
        json=payload,
        timeout=180,
    )

    response.raise_for_status()

    return response.json()


def submit_approval(approved, reason=""):

    payload = {
        "conversation_id": st.session_state.conversation_id,
        "customer_id": CUSTOMER_ID,
        "approved": approved,
        "reason": reason,
    }

    response = requests.post(
        APPROVAL_ENDPOINT,
        json=payload,
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

if not st.session_state.initialization_done:

    try:

        conversations = fetch_conversations()

        if conversations:

            # Open the most recently active conversation
            open_conversation(conversations[0]["id"])

        else:

            conversation = create_new_conversation()

            st.session_state.conversation_id = conversation["id"]
            st.session_state.messages = []

            st.session_state.conversations = fetch_conversations()

        st.session_state.initialization_done = True

    except requests.RequestException:
        st.error(
            "Unable to initialize conversations. "
            "Please check that the backend is running."
        )
        st.stop()


# ==========================================
# SIDEBAR
# ==========================================

with st.sidebar:

    st.title("🤖 Multi-Agent AI Support System")

    st.caption("Designed & Developed by Ali Mahmoud EL BAgoury")

    st.divider()

    if not check_api_health():

        st.error("Support system is currently unavailable.")
        st.stop()

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

                    st.error(
                        f"Could not open conversation: {error}"
                    )

    st.divider()

    st.caption("Powered by LangGraph, LangChain and Ollama")


# ==========================================
# MAIN HEADER
# ==========================================

st.title("Customer Support Assistant")

st.write("Hello! How can I help you today?")

st.divider()


# ==========================================
# DISPLAY CHAT HISTORY
# ==========================================

for message in st.session_state.messages:

    with st.chat_message(message["role"]):

        st.markdown(message["content"])


# ==========================================
# HUMAN APPROVAL
# ==========================================

pending = st.session_state.pending_approval

if pending:

    st.warning("Human Approval Required")

    action = pending.get("action", "Unknown action")
    order_id = pending.get("order_id")
    return_id = pending.get("return_id")
    details = pending.get("details", "")
    reason = pending.get("reason", "")

    with st.container(border=True):

        st.subheader("Approval Request")

        st.write(f"**Action:** {action}")

        if order_id is not None:
            st.write(f"**Order ID:** {order_id}")

        if return_id is not None:
            st.write(f"**Return ID:** {return_id}")

        st.write(f"**Details:** {details}")
        st.write(f"**Reason:** {reason}")

        st.divider()

        rejection_reason = st.text_input(
            "Rejection reason (optional)",
            key="rejection_reason",
        )

        col1, col2 = st.columns(2)

        with col1:

            approve_clicked = st.button(
                "✅ Approve",
                type="primary",
                use_container_width=True,
                key="approve_action",
            )

        with col2:

            reject_clicked = st.button(
                "❌ Reject",
                use_container_width=True,
                key="reject_action",
            )

        if approve_clicked or reject_clicked:

            approved = approve_clicked

            final_reason = (
                "Approved by human reviewer"
                if approved
                else rejection_reason.strip() or "Rejected by human reviewer"
            )

            try:

                with st.spinner("Processing decision..."):

                    result = submit_approval(
                        approved=approved,
                        reason=final_reason,
                    )

                handle_api_response(result)

                st.session_state.conversations = fetch_conversations()

                st.rerun()

            except requests.RequestException as error:

                st.error(f"Could not submit approval: {error}")


# ==========================================
# CHAT INPUT
# ==========================================

if st.session_state.pending_approval is None:

    question = st.chat_input(
        "Type your message here..."
    )

    if question:

        st.session_state.messages.append({
            "role": "user",
            "content": question,
        })

        with st.chat_message("user"):
            st.markdown(question)

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
