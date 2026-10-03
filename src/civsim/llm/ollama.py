"""Ollama backend: a local model server, so development costs no API credits."""

import json
import urllib.error
import urllib.request

from .client import LLMError

DEFAULT_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1:8b"


class OllamaClient:
    def __init__(self, model: str = DEFAULT_MODEL, base_url: str = DEFAULT_URL, timeout: float = 120.0,
                 temperature: float = 0.7):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.temperature = temperature
        self.name = f"ollama:{model}"

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        body = {
            "model": self.model,
            "stream": False,
            "format": schema,  # constrains the reply to this JSON schema
            "options": {"temperature": self.temperature, "num_ctx": 8192},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        reply = self._post("/api/chat", body)
        try:
            parsed = json.loads(reply["message"]["content"])
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise LLMError(f"{self.name} did not return JSON") from exc
        if not isinstance(parsed, dict):
            raise LLMError(f"{self.name} returned JSON that is not an object")
        return parsed

    def check(self) -> str | None:
        """None if the server is up and has the model; otherwise what is wrong."""
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=5) as response:
                models = [entry["name"] for entry in json.load(response).get("models", [])]
        except (OSError, ValueError, KeyError) as exc:
            return f"cannot reach Ollama at {self.base_url} ({exc})"
        if self.model not in models:
            return f"Ollama has no model {self.model!r}; run: ollama pull {self.model}"
        return None

    def _post(self, path: str, body: dict) -> dict:
        request = urllib.request.Request(
            self.base_url + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except (OSError, ValueError) as exc:  # URLError and timeouts are OSErrors
            raise LLMError(f"{self.name} request failed: {exc}") from exc
