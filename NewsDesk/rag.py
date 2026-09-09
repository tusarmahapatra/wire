"""Retrieval over the live STORE — local embeddings, no vector DB.

The corpus is small (<=400 items/tab x 4 tabs), so a plain dict of vectors
plus a numpy cosine scan is plenty; a real vector DB would be overkill.
Embeddings run locally via fastembed (ONNX, no torch, no API key) so this
stays free to host — Groq (see chat.py) is only used for the answer, never
for turning text into vectors.
"""

from __future__ import annotations

import asyncio
import logging
import os

import numpy as np

log = logging.getLogger("newsdesk.rag")

EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "32"))
RAG_MAX_ITEMS = int(os.getenv("RAG_MAX_ITEMS", "600"))

_model = None
_INDEX: dict[str, tuple[object, np.ndarray]] = {}  # id -> (Item, unit vector)
_index_lock = asyncio.Lock()


def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding(model_name=EMBED_MODEL)
    return _model


def _embed(texts: list[str]) -> np.ndarray:
    vecs = np.array(list(_get_model().embed(texts)), dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vecs / norms


def _text_of(item) -> str:
    return f"{item.title}. {item.summary}".strip()


async def sync_index(store: dict[str, dict[str, object]]) -> None:
    live: dict[str, object] = {}
    for bucket in store.values():
        live.update(bucket)

    # Cap the corpus so a big first refresh (or a large MAX_PER_TAB) can't
    # force an unbounded embedding burst — keep only the most recent items.
    if len(live) > RAG_MAX_ITEMS:
        newest = sorted(live.values(), key=lambda i: i.published, reverse=True)[:RAG_MAX_ITEMS]
        live = {item.id: item for item in newest}

    async with _index_lock:
        stale = [id_ for id_ in _INDEX if id_ not in live]
        for id_ in stale:
            del _INDEX[id_]

        new_items = [item for id_, item in live.items() if id_ not in _INDEX]
        # Embed in small batches rather than all at once — bounds peak memory
        # regardless of how many new items showed up in this refresh.
        for i in range(0, len(new_items), EMBED_BATCH_SIZE):
            chunk = new_items[i : i + EMBED_BATCH_SIZE]
            texts = [_text_of(item) for item in chunk]
            vecs = await asyncio.to_thread(_embed, texts)
            for item, vec in zip(chunk, vecs):
                _INDEX[item.id] = (item, vec)

    if stale or new_items:
        log.info("rag index: %d items (+%d, -%d)", len(_INDEX), len(new_items), len(stale))


async def search(query: str, tab: str | None, k: int) -> list:
    async with _index_lock:
        pool = list(_INDEX.values())
    if not pool:
        return []
    if tab:
        pool = [(item, vec) for item, vec in pool if item.tab == tab]
    if not pool:
        return []

    q_vec = (await asyncio.to_thread(_embed, [query]))[0]
    matrix = np.stack([vec for _, vec in pool])
    scores = matrix @ q_vec
    top = np.argsort(-scores)[:k]
    return [pool[i][0] for i in top]
