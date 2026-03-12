from __future__ import annotations

from dataclasses import dataclass

import requests

from .config import Settings


class QwenClientError(RuntimeError):
    """Raised when the planner model endpoint cannot be used."""


@dataclass
class ChatResponse:
    content: str
    raw_payload: dict


class QwenClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def chat(self, messages: list[dict[str, str]], max_tokens: int | None = None) -> ChatResponse:
        headers = {'Content-Type': 'application/json'}
        if self.settings.qwen_api_key:
            headers['Authorization'] = f'Bearer {self.settings.qwen_api_key}'

        payload = {
            'model': self.settings.planner_model_name,
            'messages': messages,
            'temperature': self.settings.planner_temperature,
            'max_tokens': max_tokens or self.settings.planner_max_tokens,
            'seed': self.settings.planner_seed,
        }
        try:
            response = requests.post(
                f"{self.settings.qwen_api_base.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.settings.qwen_timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise QwenClientError(str(exc)) from exc

        data = response.json()
        try:
            content = data['choices'][0]['message']['content']
        except (KeyError, IndexError, TypeError) as exc:
            raise QwenClientError('planner model response missing choices[0].message.content') from exc
        return ChatResponse(content=content, raw_payload=data)

    def list_models(self) -> dict:
        headers = {}
        if self.settings.qwen_api_key:
            headers['Authorization'] = f'Bearer {self.settings.qwen_api_key}'
        try:
            response = requests.get(
                f"{self.settings.qwen_api_base.rstrip('/')}/models",
                headers=headers,
                timeout=self.settings.qwen_timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise QwenClientError(str(exc)) from exc
        return response.json()
