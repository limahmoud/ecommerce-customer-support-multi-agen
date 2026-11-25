import os

from dotenv import load_dotenv

load_dotenv()


def create_chat_model():
    """
    Create the configured chat model.

    Supported providers:
    - groq
    - ollama
    """

    provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()
    temperature = float(os.getenv("LLM_TEMPERATURE", "0"))

    if provider == "groq":
        api_key = os.getenv("GROQ_API_KEY")

        if not api_key:
            raise ValueError(
                "GROQ_API_KEY is missing from .env"
            )

        from langchain_groq import ChatGroq

        model = os.getenv(
            "LLM_MODEL",
            "openai/gpt-oss-120b",
        )

        return ChatGroq(
            model=model,
            api_key=api_key,
            temperature=temperature,
        )

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
        base_url = os.getenv(
            "OLLAMA_BASE_URL",
            "http://localhost:11434",
        )

        return ChatOllama(
            model=model,
            base_url=base_url,
            temperature=temperature,
        )

    raise ValueError(
        f"Unsupported LLM_PROVIDER: {provider}. "
        "Supported providers: groq, ollama"
    )
