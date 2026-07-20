from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI


def as_chat_completions_model(
    model: BaseChatModel | Any,
) -> BaseChatModel | Any:
    """Use Chat Completions for structured agents on compatible gateways."""

    if not isinstance(model, ChatOpenAI):
        return model
    return model.model_copy(update={"use_responses_api": False, "output_version": None})


__all__ = ["as_chat_completions_model"]
