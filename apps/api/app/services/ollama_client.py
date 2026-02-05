from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx


@dataclass
class OllamaChatResult:
    text: str


class OllamaClient:
    """
    Minimal Ollama client for local generation.

    Uses /api/generate (simple) to keep integration stable.
    """

    def __init__(self, base_url: str, timeout_s: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def generate(
        self,
        model: str,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.2,
    ) -> OllamaChatResult:
        url = f"{self.base_url}/api/generate"

        payload: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }
        if system:
            payload["system"] = system

        with httpx.Client(timeout=self.timeout_s) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()

        # Ollama returns {"response": "...", ...}
        text = (data.get("response") or "").strip()
        return OllamaChatResult(text=text)