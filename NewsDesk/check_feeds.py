"""Validate every feed URL in feeds.py. Run this first, and after every edit.

    python check_feeds.py

News sites change or retire RSS paths without notice, so treat the registry as
a guess until this prints OK next to each line. Anything marked DEAD should be
replaced — usually with a gnews() line for the same beat, which never breaks.
"""

from __future__ import annotations

import asyncio

import feedparser
import httpx

from feeds import TAB_FEEDS

UA = "newsdesk/1.0 (feed check)"


async def check(client: httpx.AsyncClient, tab: str, feed) -> tuple[str, str, str, int]:
    try:
        r = await client.get(feed.url, timeout=20, follow_redirects=True)
        r.raise_for_status()
        parsed = feedparser.parse(r.content)
        n = len(parsed.entries)
        return (tab, feed.source, "OK  " if n else "EMPTY", n)
    except httpx.HTTPStatusError as exc:
        return (tab, feed.source, f"HTTP {exc.response.status_code}", 0)
    except Exception as exc:  # noqa: BLE001
        return (tab, feed.source, f"DEAD {type(exc).__name__}", 0)


async def main():
    async with httpx.AsyncClient(headers={"User-Agent": UA}) as client:
        jobs = [check(client, tab, f) for tab, feeds in TAB_FEEDS.items() for f in feeds]
        results = await asyncio.gather(*jobs)

    width = max(len(r[1]) for r in results)
    bad = 0
    for tab, source, status, n in results:
        if not status.startswith("OK"):
            bad += 1
        print(f"{tab:<6} {source:<{width}}  {status:<18} {n:>3} items")

    print(f"\n{len(results) - bad}/{len(results)} feeds healthy")


if __name__ == "__main__":
    asyncio.run(main())
