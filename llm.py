"""The one place where the model provider is chosen.

Calls go through LangChain so that switching provider is a one-line change here.
Gemini is in use because the Anthropic billing form could not be completed; the
Anthropic branch is kept working so the swap costs nothing later.

Baseline and the real implementation must be measured on the same model. Measuring
them on different ones would make the comparison table read as a difference between
models rather than the effect of the validation node, which is the whole claim this
project makes. Provider and model therefore go into every run record.
"""

from __future__ import annotations

import os

from langchain_core.language_models import BaseChatModel
from pydantic import SecretStr

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5"

# A learner staring at a frozen screen assumes their own Japanese broke something,
# so a stuck call must surface as an error rather than hang.
REQUEST_TIMEOUT_SECONDS = 30.0


class MissingCredentialsError(RuntimeError):
    """Raised when the selected provider has no API key in the environment."""


def active_model_name() -> str:
    """Return provider/model as it should appear in a run record."""
    provider = _provider()
    if provider == "anthropic":
        return f"anthropic/{os.environ.get('ANTHROPIC_MODEL', DEFAULT_ANTHROPIC_MODEL)}"
    return f"gemini/{os.environ.get('GEMINI_MODEL', DEFAULT_GEMINI_MODEL)}"


def build_chat_model(temperature: float) -> BaseChatModel:
    """Return the chat model for the configured provider.

    Temperature is explicit at every call site rather than defaulted, because the
    conversation wants variety and the correction must not have any.
    """
    provider = _provider()

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
            google_api_key=_require_key("GEMINI_API_KEY"),
            temperature=temperature,
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model_name=os.environ.get("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL),
            api_key=SecretStr(_require_key("ANTHROPIC_API_KEY")),
            temperature=temperature,
            timeout=REQUEST_TIMEOUT_SECONDS,
            stop=None,
        )

    raise ValueError(f"Unknown LLM_PROVIDER: {provider!r}. Use 'gemini' or 'anthropic'.")


def as_text(content: object) -> str:
    """Flatten LangChain's message-content union down to plain text.

    The union spans providers, so the flattening belongs next to the provider
    choice rather than being repeated by every caller.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [part for part in content if isinstance(part, str)]
        parts += [
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        return "".join(parts)
    return str(content)


def _provider() -> str:
    return os.environ.get("LLM_PROVIDER", "gemini").strip().lower()


def _require_key(name: str) -> str:
    # GEMINI_API_KEY lives in ~/.zshenv and is deliberately not copied into .env,
    # so a missing key here usually means the shell environment did not carry over.
    key = os.environ.get(name, "").strip()
    if not key:
        raise MissingCredentialsError(
            f"{name} is not set. It is read from the environment, not from .env."
        )
    return key
