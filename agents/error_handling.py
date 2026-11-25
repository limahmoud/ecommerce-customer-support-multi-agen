import logging

from langchain_core.messages import AIMessage


logger = logging.getLogger(__name__)

SAFE_ERROR_MESSAGE = (
    "I'm sorry, I'm unable to process your request right now. "
    "Please try again later."
)

TOOL_ERROR_MESSAGE = (
    "The requested operation could not be completed. "
    "Do not expose internal error details. "
    "Inform the user that the operation failed and suggest trying again."
)


def invoke_llm_safely(llm, messages) -> AIMessage:
    """Invoke an LLM safely and return a valid AIMessage."""

    try:
        response = llm.invoke(messages)

        if not isinstance(response, AIMessage):
            logger.error(
                "LLM returned an invalid response type: %s",
                type(response).__name__,
            )
            return AIMessage(content=SAFE_ERROR_MESSAGE)

        return response

    except Exception:
        logger.exception("LLM invocation failed")
        return AIMessage(content=SAFE_ERROR_MESSAGE)