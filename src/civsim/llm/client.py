"""What the strategy layer needs from a language model.

Given a system prompt, a user prompt and a JSON schema, return a JSON object.
The sim runs on a local Ollama model; the Protocol exists so tests can stand in
a scripted client without a model server.
"""

from typing import Protocol


class LLMError(Exception):
    """The model could not be reached or did not return a JSON object."""


class LLMClient(Protocol):
    name: str

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        """Return the model's reply as a dict shaped by `schema`. Raises LLMError on any failure."""
        ...


def make_client(provider: str, model: str | None = None, base_url: str | None = None) -> LLMClient:
    if provider == "ollama":
        from .ollama import DEFAULT_MODEL, DEFAULT_URL, OllamaClient

        return OllamaClient(model or DEFAULT_MODEL, base_url or DEFAULT_URL)
    raise ValueError(f"unknown LLM provider {provider!r}; available: ollama")
