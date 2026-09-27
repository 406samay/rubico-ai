"""
The one place that talks to Claude. Every tool that needs Claude to think
(writing the brief, answering chat, reading a reminder) goes through here,
so the model name and API key come from config instead of being scattered.
"""

import json

import anthropic

import config


def has_key():
    return bool(config.env("ANTHROPIC_API_KEY"))


def _client():
    key = config.env("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is missing from .env - run setup.py to add it."
        )
    return anthropic.Anthropic(api_key=key)


def ask(system, user_message, max_tokens=2048, tools=None):
    """Send one message, return Claude's text reply."""
    kwargs = {
        "model": config.model(),
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user_message}],
    }
    if tools:
        kwargs["tools"] = tools
    response = _client().messages.create(**kwargs)
    parts = [block.text for block in response.content if block.type == "text"]
    return "\n".join(parts).strip()


def parse_json_object(text):
    """Pulls a JSON object out of a reply, or None. Tolerates a code fence
    or a stray sentence around it rather than failing the whole request."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def voice_instructions():
    """How the assistant should sound - from config.yaml, so it's yours to change."""
    cfg = config.get()
    name = config.user_name()
    who = f"The user's name is {name}. " if name else ""
    return (
        f"You are {config.assistant_name()}, a personal assistant. {who}"
        f"Voice: {cfg['assistant']['voice'].strip()} "
        "No markdown (no **bold**, no - bullets, no # headers) - Telegram shows "
        "it as literal characters, so write plain sentences."
    )
