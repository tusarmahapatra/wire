# Wire

A personal news desk: two tabs, **Current Affairs** (UPSC-shaped) and
**Investing** (India / World / Crypto·Gold·Commodities). One Python process
polls RSS in the background, dedupes, scores and tags each story, and serves
a single-page reader — plus a Groq-backed chat you can ask about what's in
the feed.

The app lives in [`NewsDesk/`](NewsDesk/) — see
[`NewsDesk/README.md`](NewsDesk/README.md) for how it's built and how to run
it.

## Quick start

```bash
cd NewsDesk
./startup.sh   # first run creates .env — add your GROQ_API_KEY, then...
./startup.sh   # ...run it again to install deps and start Wire
```

Open http://localhost:8000. No Groq key? It still runs — only chat is
disabled. Get a free key at https://console.groq.com/keys.

## Repo layout

```
NewsDesk/          the app — fetch loop, scoring, JSON API, reader UI
PRODUCT_AUDIT.md    read-only code audit (monetization planning)
```
