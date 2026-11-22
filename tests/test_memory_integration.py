
import uuid

import pytest

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres import PostgresSaver

from api.api import DB_URI
from agents.supervisor_agent import build_supervisor


@pytest.mark.integration
def test_postgres_checkpointer_persists_conversation():

    conversation_id = f"pytest-memory-{uuid.uuid4()}"

    config = {
        "configurable": {
            "thread_id": conversation_id
        }
    }

    first_question = "Show me the details of order 1"

    second_question = "What is its shipment status?"

    # ----------------------------------
    # First conversation: Save checkpoint
    # ----------------------------------

    with PostgresSaver.from_conn_string(DB_URI) as checkpointer:

        checkpointer.setup()

        supervisor = build_supervisor(checkpointer)

        first_result = supervisor.invoke(
            {
                "messages": [
                    HumanMessage(content=first_question)
                ]
            },
            config=config,
        )

        assert not first_result.get("__interrupt__"), (
            "Unexpected approval interrupt during order lookup"
        )

        saved_state = supervisor.get_state(config)

        saved_messages = saved_state.values["messages"]

        assert any(
            first_question in str(message.content)
            for message in saved_messages
            if hasattr(message, "content")
        ), "First question was not saved in checkpoint"

    # ----------------------------------
    # Second connection: Restore checkpoint
    # ----------------------------------

    with PostgresSaver.from_conn_string(DB_URI) as checkpointer:

        checkpointer.setup()

        # Build a NEW supervisor with a NEW checkpointer connection
        supervisor = build_supervisor(checkpointer)

        restored_state = supervisor.get_state(config)

        restored_messages = restored_state.values["messages"]

        # Verify that the previous conversation was restored
        assert any(
            first_question in str(message.content)
            for message in restored_messages
            if hasattr(message, "content")
        ), "Previous conversation was not restored from PostgreSQL"

        # Continue the same conversation
        second_result = supervisor.invoke(
            {
                "messages": [
                    HumanMessage(content=second_question)
                ]
            },
            config=config,
        )

        assert not second_result.get("__interrupt__"), (
            "Unexpected approval interrupt during shipment lookup"
        )

        final_state = supervisor.get_state(config)

        final_messages = final_state.values["messages"]

        # Verify both questions exist in the same conversation
        assert any(
            first_question in str(message.content)
            for message in final_messages
            if hasattr(message, "content")
        )

        assert any(
            second_question in str(message.content)
            for message in final_messages
            if hasattr(message, "content")
        )

        print("\nConversation ID:", conversation_id)
        print("\nFirst question:", first_question)
        print("\nSecond question:", second_question)

        print("\nFinal response:")
        print(second_result["messages"][-1].content)

        
# 3. افهم الاختبار بيعمل إيه
# 1. إنشاء Conversation ID
   
#    بننشئ ID فريد للمحادثة باستخدام uuid عشان كل اختبار يكون مستقل.
# 2. حفظ أول رسالة
   
#    بنبعت سؤال عن Order 1، والـ Supervisor بيشتغل باستخدام PostgresSaver.
# 3. إغلاق الاتصال
   
#    بنخرج من with، وبالتالي اتصال الـ Checkpointer الأول بيتقفل.
# 4. إعادة فتح PostgreSQL
   
#    بنفتح Checkpointer جديد ونبني Supervisor جديد.
# 5. استرجاع المحادثة
   
#    get_state(config) بيسترجع المحادثة القديمة باستخدام نفس thread_id.
# 6. استكمال المحادثة
   
#    بنسأل عن حالة الشحنة باستخدام كلمة its، والـ Supervisor المفروض يفهم إن المقصود Order 1.
# 4. شغّل الاختبار
# تأكد إن PostgreSQL وOllama شغالين، وإن الموديل المحدد في .env متاح.