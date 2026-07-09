"""Client minimal pour l'API Mistral (chat completions), sans SDK."""

from __future__ import annotations

import json
import logging
import os
import time

import requests

log = logging.getLogger("veille.mistral")

API_URL = "https://api.mistral.ai/v1/chat/completions"


class MistralClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("MISTRAL_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("MISTRAL_API_KEY manquante (variable d'environnement)")

    def chat(self, model: str, messages: list[dict], json_mode: bool = False, temperature: float = 0.3, max_retries: int = 4) -> str:
        payload: dict = {"model": model, "messages": messages, "temperature": temperature}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        for attempt in range(max_retries):
            try:
                r = requests.post(
                    API_URL,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=180,
                )
                if r.status_code == 429 or r.status_code >= 500:
                    wait = 2 ** (attempt + 1)
                    log.warning("HTTP %d, retry dans %ds", r.status_code, wait)
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
            except requests.RequestException as e:
                if attempt == max_retries - 1:
                    raise
                log.warning("Erreur reseau (%s), retry", e)
                time.sleep(2 ** (attempt + 1))
        raise RuntimeError("Mistral API: retries epuises")

    def chat_json(self, model: str, messages: list[dict], **kw) -> dict:
        text = self.chat(model, messages, json_mode=True, **kw)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # tentative de recuperation si le modele a entoure le JSON de texte
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
            raise
