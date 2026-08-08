import json
import re

from openai import OpenAI

PROVIDERS = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "default_model": "gemini-2.0-flash",
        "needs_key": True,
        "hint": "Free API key at aistudio.google.com",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "needs_key": True,
        "hint": "Free API key at console.groq.com",
    },
    "xai": {
        "base_url": "https://api.x.ai/v1",
        "default_model": "grok-3-fast",
        "needs_key": True,
        "hint": "xAI (Grok). Key starts with 'xai-'. Models like grok-3 / grok-3-fast.",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "default_model": "llama3.2",
        "needs_key": False,
        "hint": "Runs locally. Install Ollama and run: ollama pull llama3.2",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "needs_key": True,
        "hint": "Pay-as-you-go. Requires a credit card.",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "meta-llama/llama-3.3-70b-instruct",
        "needs_key": True,
        "hint": "Free models available at openrouter.ai",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "needs_key": True,
        "hint": "Very cheap. API key at platform.deepseek.com",
    },
}


def extract_json(text):
    text = re.sub(r"```(?:json)?", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON found in model output: {text[:200]}")
    return json.loads(text[start : end + 1])


class LLMClient:
    def __init__(self, provider, api_key=None, model=None, base_url=None):
        spec = PROVIDERS[provider]
        self.provider = provider
        self.model = model or spec["default_model"]
        self.base_url = base_url or spec["base_url"]
        self.api_key = api_key or "ollama"
        self.client = OpenAI(base_url=self.base_url, api_key=self.api_key)

    def complete(self, system, user, temperature=0.0):
        kwargs = dict(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
        )
        try:
            resp = self.client.chat.completions.create(
                **kwargs, response_format={"type": "json_object"}
            )
        except Exception:
            resp = self.client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content

    def complete_json(self, system, user):
        text = self.complete(system, user)
        return extract_json(text)