"""Groq chat completion — the only paid-adjacent call in the app.

Groq hosts open chat models (Llama, GPT-OSS, ...) behind a fast,
OpenAI-compatible API with a workable free tier. It does not do embeddings
(see rag.py for that half of the pipeline) — this module only turns a
question plus retrieved headlines into a grounded answer.
"""

from __future__ import annotations

import os

import httpx

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_CHAT_MODEL = os.getenv("GROQ_CHAT_MODEL", "openai/gpt-oss-120b")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class ChatError(RuntimeError):
    pass


def _system_prompt(sources: list) -> str:
    if not sources:
        listing = "(no matching headlines were found in the current feed)"
    else:
        listing = "\n".join(
            f"[{i}] {s.title} — {s.source}, {s.published}\n    {s.summary}"
            for i, s in enumerate(sources, 1)
        )
    return (
        "You are the assistant for a live news wire. Answer the user's "
        "question using ONLY the numbered headlines below — do not use "
        "outside knowledge. Cite sources inline like [1], [2]. If the "
        "headlines don't cover the question, say so plainly instead of "
        "guessing.\n\n" + listing
    )


async def ask(question: str, history: list[dict], sources: list) -> str:
    if not GROQ_API_KEY:
        raise ChatError("GROQ_API_KEY is not configured")

    messages = [{"role": "system", "content": _system_prompt(sources)}]
    messages.extend(history)
    messages.append({"role": "user", "content": question})

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json={"model": GROQ_CHAT_MODEL, "messages": messages, "temperature": 0.2},
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise ChatError(f"Groq request failed: {exc}") from exc

    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise ChatError("Groq returned an unexpected response") from exc
