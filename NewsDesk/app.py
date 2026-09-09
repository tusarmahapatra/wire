"""News desk — one process that polls RSS, keeps a rolling store, serves JSON.

Run:  uvicorn app:app --reload --port 8000
Open: http://localhost:8000

Why a backend at all: browsers can't fetch third-party RSS directly (no CORS
headers on any news site). The server also gives you caching, dedupe and
scoring, so the page loads in one request instead of forty.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import html as html_lib
import logging
import os
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import httpx
from dotenv import load_dotenv

load_dotenv(override=True)  # must run before importing chat — it reads GROQ_API_KEY at import time

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import chat
import rag
from feeds import NAV, TAB_FEEDS, Feed
from relevance import score_item

log = logging.getLogger("newsdesk")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

REFRESH_SECONDS = int(os.getenv("REFRESH_SECONDS", "240"))
RETENTION_HOURS = int(os.getenv("RETENTION_HOURS", "72"))
MAX_PER_TAB = int(os.getenv("MAX_PER_TAB", "400"))
CHAT_TOP_K = int(os.getenv("CHAT_TOP_K", "8"))
FETCH_TIMEOUT = 15.0
CONCURRENCY = 8
UA = "newsdesk/1.0 (feed check)"

BASE = Path(__file__).parent
STATIC = BASE / "static"


# --------------------------------------------------------------------------
# Store
# --------------------------------------------------------------------------
@dataclass
class Item:
    id: str
    tab: str
    title: str
    link: str
    source: str
    summary: str
    published: str          # ISO-8601 UTC
    first_seen: str         # ISO-8601 UTC — when *this* app first saw it
    score: float
    tags: list[str] = field(default_factory=list)


STORE: dict[str, dict[str, Item]] = {tab: {} for tab in TAB_FEEDS}
HEALTH: dict[str, dict] = {}
LAST_REFRESH: datetime | None = None
_lock = asyncio.Lock()

_TAGS = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")
_PUNCT = re.compile(r"[^a-z0-9 ]+")

# Indic, Arabic, CJK, Cyrillic, Thai scripts — a title containing any of these
# isn't English, whatever the feed's declared language parameter claims.
_NON_LATIN = re.compile(
    "["
    "؀-ۿ܀-ݏ"                      # Arabic, Syriac
    "ऀ-ॿঀ-৿਀-੿઀-૿"
    "଀-୿஀-௿ఀ-౿ಀ-೿ഀ-ൿ"
    "฀-๿"                                    # Devanagari .. Malayalam, Thai
    "Ѐ-ӿ"                                    # Cyrillic
    "぀-ヿ一-鿿가-힯"           # CJK / Hangul
    "]"
)


def is_english(title: str, summary: str) -> bool:
    return not (_NON_LATIN.search(title) or _NON_LATIN.search(summary))


def strip_html(raw: str, limit: int = 260) -> str:
    text = html_lib.unescape(_TAGS.sub(" ", raw or ""))
    text = _SPACE.sub(" ", text).strip()
    return text[: limit - 1] + "…" if len(text) > limit else text


def fingerprint(title: str, link: str) -> str:
    """Same story from Mint and Moneycontrol should collapse into one row."""
    key = _PUNCT.sub("", title.lower())
    key = " ".join(key.split()[:9]) or link
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def entry_time(entry) -> datetime:
    for attr in ("published_parsed", "updated_parsed"):
        value = getattr(entry, attr, None)
        if value:
            with contextlib.suppress(Exception):
                return datetime(*value[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Fetch
# --------------------------------------------------------------------------
async def fetch_feed(client: httpx.AsyncClient, feed: Feed, tab: str) -> list[Item]:
    try:
        resp = await client.get(feed.url, timeout=FETCH_TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        parsed = await asyncio.to_thread(feedparser.parse, resp.content)
    except Exception as exc:  # noqa: BLE001 — one bad feed must not kill a refresh
        HEALTH[feed.url] = {"source": feed.source, "tab": tab, "ok": False,
                            "detail": type(exc).__name__, "count": 0}
        log.warning("feed failed %s (%s): %s", feed.source, feed.url, exc)
        return []

    now = datetime.now(timezone.utc).isoformat()
    items: list[Item] = []

    for entry in parsed.entries[:40]:
        title = _SPACE.sub(" ", html_lib.unescape(getattr(entry, "title", ""))).strip()
        link = getattr(entry, "link", "")
        if not title or not link:
            continue

        source = feed.source
        if feed.kind == "gnews" and " - " in title:
            # Google News formats titles as "Headline - Publisher".
            title, _, publisher = title.rpartition(" - ")
            source = f"{publisher.strip()} · via {feed.source}"

        summary = strip_html(getattr(entry, "summary", ""))
        if feed.kind == "gnews":
            summary = ""  # Google's summary is a list of link markup, not prose.

        if not is_english(title, summary):
            continue

        score, tags = score_item(title, summary, tab, feed.weight)
        items.append(Item(
            id=fingerprint(title, link),
            tab=tab,
            title=title,
            link=link,
            source=source,
            summary=summary,
            published=entry_time(entry).isoformat(),
            first_seen=now,
            score=score,
            tags=tags,
        ))

    HEALTH[feed.url] = {"source": feed.source, "tab": tab, "ok": True,
                        "detail": "", "count": len(items)}
    return items


async def refresh_all() -> int:
    global LAST_REFRESH
    sem = asyncio.Semaphore(CONCURRENCY)

    async def guarded(client, feed, tab):
        async with sem:
            return await fetch_feed(client, feed, tab)

    async with httpx.AsyncClient(headers={"User-Agent": UA}) as client:
        jobs = [guarded(client, feed, tab)
                for tab, feeds in TAB_FEEDS.items()
                for feed in feeds]
        results = await asyncio.gather(*jobs)

    added = 0
    cutoff = datetime.now(timezone.utc) - timedelta(hours=RETENTION_HOURS)

    async with _lock:
        for batch in results:
            for item in batch:
                bucket = STORE[item.tab]
                existing = bucket.get(item.id)
                if existing:
                    # Keep the earliest sighting, prefer the higher-trust source.
                    if item.score > existing.score:
                        item.first_seen = existing.first_seen
                        bucket[item.id] = item
                    continue
                bucket[item.id] = item
                added += 1

        for tab, bucket in STORE.items():
            kept = [i for i in bucket.values()
                    if datetime.fromisoformat(i.published) > cutoff]
            kept.sort(key=lambda i: i.published, reverse=True)
            STORE[tab] = {i.id: i for i in kept[:MAX_PER_TAB]}

    LAST_REFRESH = datetime.now(timezone.utc)
    log.info("refresh complete: %s new items", added)

    await rag.sync_index(STORE)
    return added


async def refresh_loop():
    while True:
        try:
            await refresh_all()
        except Exception:  # noqa: BLE001
            log.exception("refresh loop error")
        await asyncio.sleep(REFRESH_SECONDS)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(refresh_loop())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="News desk", lifespan=lifespan)


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
@app.get("/api/nav")
async def nav():
    return {"nav": NAV, "refresh_seconds": REFRESH_SECONDS}


@app.get("/api/items")
async def items(
    tab: str = Query("upsc"),
    min_score: float = Query(-99.0, description="UPSC tab: 1.5 is a good strict cut"),
    tag: str | None = None,
    limit: int = Query(120, le=400),
):
    if tab not in STORE:
        return {"error": f"unknown tab '{tab}'", "items": []}

    rows = list(STORE[tab].values())
    rows = [r for r in rows if r.score >= min_score]
    if tag:
        rows = [r for r in rows if tag in r.tags]
    rows.sort(key=lambda r: (r.published, r.score), reverse=True)

    return {
        "tab": tab,
        "count": len(rows),
        "last_refresh": LAST_REFRESH.isoformat() if LAST_REFRESH else None,
        "items": [r.__dict__ for r in rows[:limit]],
    }


@app.post("/api/refresh")
async def manual_refresh():
    added = await refresh_all()
    return {"added": added, "last_refresh": LAST_REFRESH.isoformat()}


class ChatRequest(BaseModel):
    question: str
    tab: str | None = None
    history: list[dict] = []


@app.post("/api/chat")
async def api_chat(req: ChatRequest):
    sources = await rag.search(req.question, req.tab, CHAT_TOP_K)
    try:
        answer = await chat.ask(req.question, req.history, sources)
    except chat.ChatError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "answer": answer,
        "sources": [
            {"id": s.id, "title": s.title, "source": s.source,
             "link": s.link, "published": s.published}
            for s in sources
        ],
    }


@app.get("/api/sources")
async def sources():
    return {"sources": sorted(HEALTH.values(), key=lambda s: (s["tab"], s["source"]))}


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "last_refresh": LAST_REFRESH.isoformat() if LAST_REFRESH else None,
        "counts": {tab: len(bucket) for tab, bucket in STORE.items()},
        "feeds_failing": [s["source"] for s in HEALTH.values() if not s["ok"]],
    }


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")
